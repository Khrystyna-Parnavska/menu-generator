import atexit
import database.models as m
import random
import os
from gettext import install
from time import strftime
from flask import Flask, flash, render_template, redirect, url_for, request, session
from flask_scss import Scss
from flask_mail import Mail, Message
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta, date, timezone
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'static/uploads'

meal_model = m.MealsModel()
menu_model = m.MenuModel()
menu_meals_model = m.MenuMealsModel()
users_model = m.UsersModel()
recipe_model = m.RecipesModel()
ing_model = m.IngredientsModel()
recipe_ingredients_model = m.RecipesIngredientsModel()
favorites_recipes_model = m.FavoritesRecipesModel()


app = Flask(__name__)

app.secret_key = os.getenv('app_key')

app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT'))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS').lower() == 'true'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD') # Not your regular password!

mail = Mail(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'signin' # Where to send users if they aren't logged in

# This class connects your DB data to Flask-Login
class User(UserMixin):
    def __init__(self, user_details):
        self.id = user_details['id']
        self.username = user_details['user_name']
        self.email = user_details['email']
        self.role_id = user_details['role_id']

@login_manager.user_loader
def load_user(user_id):
    u = recipe_model.run_query("SELECT * FROM Users WHERE id = %s", (user_id,))
    if u:
        return User(u[0])
    return None

Scss(app, static_dir='static', asset_dir='assets')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
print(app.config['UPLOAD_FOLDER'])
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def generate_meal(meal_id):
    list_recipes = recipe_model.run_query("SELECT * FROM Recipes WHERE meal_id = %s", (meal_id,))
    recipe = random.choice(list_recipes)
    return recipe


def generate_menu(menu_id:int, selected_meals:list): 
    draft_menu_meals = []

    for name in selected_meals:
            
            meal = meal_model.run_query("SELECT id, default_time FROM Meals WHERE name = %s", (name,))[0]
            meal_id = meal['id']
            meal_time_default = meal['default_time']

            recipe = generate_meal(meal_id)

            draft_meal = {
                            'menu_id': menu_id,
                            'meal_id': meal_id,
                            'recipe_id': recipe['id'],
                            'meal_time': meal_time_default,

                            'is_leftover_plan': 0,
                            'regenerated_times': 0,
                            'if_picked_manually': 0
            }
            draft_meal['recipe_name'] = recipe['name']
            draft_meal['meal_type'] = name
            draft_menu_meals.append(draft_meal)

        # Final formatting loop for Jinja2
    for meal in draft_menu_meals:
        if isinstance(meal['meal_time'], timedelta):
            # Calculate hours and minutes from total seconds
            total_seconds = int(meal['meal_time'].total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
            # Format as "HH:MM" (e.g., 07:00)
        meal['meal_time'] = f"{hours:02}:{minutes:02}"
    return draft_menu_meals


def fetch_today_menu(user_id):
    today_date = date.today()
    query_today = """
        SELECT *, DATE(created_at) as created_date FROM Menus 
        WHERE user_id = %s  
        ORDER BY created_at DESC
        LIMIT 1
    """
    latest_menu = menu_model.run_query(query_today, (user_id,))

    draft_meals = []
    menu_id = None
    success_message = None # Default to None

    if latest_menu and (latest_menu[0]['created_date'] == today_date):
        menu_id = latest_menu[0]['id']
        
        # If submitted_at is not equal to None, set success_message
        if latest_menu[0].get('submitted_at'):
            success_message = "You have already submitted today's menu."
    
        # Fetch associated meals regardless, so they show up on the page
        query_meals = """
            SELECT mm.*, r.name as recipe_name, m.name as meal_type 
            FROM Menu_meals mm
            JOIN Recipes r ON mm.recipe_id = r.id
            JOIN Meals m ON mm.meal_id = m.id
            WHERE mm.menu_id = %s
        """
        draft_meals = menu_meals_model.run_query(query_meals, (menu_id,))
            
    return draft_meals, menu_id, success_message


def fetch_favorites(user_id, return_ids_only=False):
    query = """
        SELECT r.*
        FROM Recipes r
        JOIN User_favorite_recipes f ON r.id = f.recipe_id
        WHERE f.user_id = %s
    """
    results = favorites_recipes_model.run_query(query, (user_id,))
    if return_ids_only:
        return [recipe['id'] for recipe in results]
    return results


# TODO function for this lil
meals_from_db = meal_model.get_all()

def send_meal_reminders():
    with app.app_context():
        # Find meals starting in the next 30 minutes
        # We assume your Menu_meals table has a 'meal_time' column
        query = """
            SELECT mm.id, i.email, r.name as recipe_name, mm.meal_time 
            FROM Menu_meals mm
            JOIN Users u ON mm.user_id = u.id
            JOIN Recipes r ON mm.recipe_id = r.id
            WHERE mm.meal_time BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL 30 MINUTE)
            AND mm.reminder_sent = 0
        """
        upcoming_meals = recipe_model.run_query(query)

        for meal in upcoming_meals:
            msg = Message("🍳 Time to Cook!",
                          sender="your-email@gmail.com",
                          recipients=[meal['email']])
            msg.body = f"Hi! It's almost time for your meal. Start preparing {meal['recipe_name']} now!"
            mail.send(msg)

            # Mark as sent so we don't spam the user
            recipe_model.run_query("UPDATE Menu_meals SET reminder_sent = 1 WHERE id = %s", (meal['id'],))


@app.route('/')
def home():
    return render_template('index.html')


# route for menu page
@app.route('/menu')
@login_required
def menu():
    session_draft = session.get('menu_draft', [])
    for meal in session_draft:
        print(f'session meal: {meal}')
    all_meals = meal_model.get_all()
    draft_meals = session.get('menu_draft', [])
    
    # Initialize variables
    menu_id = None
    success_message = None 

    # If nothing in session, check the database
    if not draft_meals:
        draft_meals, menu_id, success_message = fetch_today_menu(user_id=current_user.id)
    else:
        print(draft_meals)
        menu_id = draft_meals[0]['menu_id']

    # Formatting time for the template
    for meal in draft_meals:
        if hasattr(meal['meal_time'], 'total_seconds'):
            ts = int(meal['meal_time'].total_seconds())
            meal['meal_time'] = f"{ts//3600:02}:{(ts%3600)//60:02}"
        
    return render_template('menu.html', 
                           all_meals=all_meals, 
                           menu_meals=draft_meals,
                           menu_id=menu_id, 
                           success_message=success_message)


@app.route('/init-plan', methods=['POST'])
@login_required
def init_plan():
    # 1. Get the list of names from the checkboxes
    selected_names = request.form.getlist('meals')
    if not selected_names:
        error_message="Please select at least one meal!"

    menu_meals = []

    # Check if a menu already exists for today
    menu_meals, menu_id, success_message = fetch_today_menu(user_id=current_user.id)
    error_message = None

    if menu_id:
        error_message = "A menu for today already exists. You cannot create a new one."
        
    else:
        # 2. Create a new menu and get its ID
        menu_id = menu_model.insert({'user_id': current_user.id})

        menu_meals = generate_menu(menu_id, selected_names)

    session['menu_draft'] = menu_meals
    return render_template('menu.html', 
                           menu_meals=menu_meals, 
                           all_meals=meals_from_db,
                           error=error_message,
                           menu_id=menu_id,
                           success_message=success_message)

# TODO - Add error handling for edge cases (e.g., no meals selected, database errors); 
#      - add if_picked_manually flag reset to the regenerate_meal function;

@app.route('/regenerate-meal/<int:meal_id>', methods=['POST'])
@login_required
def regenerate_meal(meal_id):
    draft = session.get('menu_draft')
    is_leftover = request.form.get('is_leftover_plan')
    print(f'is_leftover: {is_leftover}')

    if not draft:
        return redirect(url_for('menu'))

    # Update the item at that specific position in the list
    meal_to_change = draft[meal_id]
    new_recipe = generate_meal(meal_to_change['meal_id'])

    meal_to_change['recipe_id'] = new_recipe['id']
    meal_to_change['recipe_name'] = new_recipe['name']
    meal_to_change['regenerated_times'] += 1
    
    session['menu_draft'] = draft
    return redirect(url_for('menu'))


@app.route('/submit-final-menu/<int:meal_count>', methods=['POST'])
@login_required
def submit_final_menu(meal_count):
    menu_id = request.form.get('menu_id')
    
    # We use a counter to loop through the indexed form fields
    for i in range(meal_count):
        # Check if the next indexed meal exists in the form
        meal_id = request.form.get(f'meal_{i}_id')
        
        # If we don't find the next index, we've reached the end of the list
        if meal_id is None:
            break
            
        # Pull all other data using the same index 'i'
        r_id = request.form.get(f'recipe_{i}_id')
        regen_count = request.form.get(f'regenerated_times_{i}')
        if_manual = request.form.get(f'if_picked_manually_{i}')
        m_time = request.form.get(f'meal_time_{i}')
        
        # Look for the leftover checkbox
        # Note: Your HTML still uses leftover_{{ meal_entry['meal_id'] }}
        # So we keep that logic here:
        is_leftover = 1 if request.form.get(f'leftover_{meal_id}') else 0

        # INSERT into Menu_meals table
        menu_meals_model.insert({
            'menu_id': menu_id,
            'meal_id': meal_id,
            'recipe_id': r_id,
            'meal_time': m_time,
            'is_leftover_plan': is_leftover,
            'regenerated_times': regen_count,
            'if_picked_manually': if_manual
        })
        
    # Finalize the menu timestamp
    menu_model.update(menu_id, {
        'submitted_at': datetime.now(timezone.utc)
    })
    
    session.pop('menu_draft', None)

    # Note: Ensure 'meals_from_db' is defined or fetched here
    return render_template('menu.html', 
                           all_meals=meals_from_db, 
                           success_message="Menu finalized and saved!")

# TODO - FIX filtering
# TODO - Add error handling for edge cases (e.g., invalid search query, database errors)
@app.route('/manual-search/<int(signed=True):meal_index>')
@login_required
def manual_search(meal_index):
    favorite_ids = fetch_favorites(current_user.id, return_ids_only=True)
    search_query = request.args.get('search', '')
    category_id = request.args.get('category')
    draft = session.get('menu_draft', [])

    # Initialize base query
    if meal_index == -1:
        # General "Explore" mode: show all recipes
        query = "SELECT * FROM Recipes WHERE 1=1"
        params = []
    else:
        # Specific meal selection mode
        if not draft or meal_index >= len(draft):
            return redirect(url_for('menu'))
        
        meal_type_id = draft[meal_index]['meal_id']
        query = "SELECT * FROM Recipes WHERE meal_id = %s"
        params = [meal_type_id]

    # Apply filters
    if search_query:
        query += " AND name LIKE %s"
        params.append(f"%{search_query}%")
    
    if category_id:
        query += " AND category_id = %s"
        params.append(category_id)
        
    recipes = recipe_model.run_query(query, tuple(params))
    categories = recipe_model.run_query("SELECT * FROM Categories")
    
    return render_template('manual_search.html', 
                           recipes=recipes, 
                           categories=categories, 
                           meal_index=meal_index,
                           search_query=search_query,
                           favorite_ids=favorite_ids)

@app.route('/select-recipe/<int:meal_index>/<int:recipe_id>', methods=['POST'])
@login_required
def select_recipe(meal_index, recipe_id):
    draft = session.get('menu_draft')
    if draft:
        # Fetch the full recipe details
        recipe = recipe_model.run_query("SELECT * FROM Recipes WHERE id = %s", (recipe_id,))[0]
        
        # Update the specific meal in the draft
        draft[meal_index]['recipe_id'] = recipe['id']
        draft[meal_index]['recipe_name'] = recipe['name']
        draft[meal_index]['if_picked_manually'] = 1
        
        session['menu_draft'] = draft
    return redirect(url_for('menu'))


@app.route('/recipe/<int:recipe_id>')
@login_required
def recipe_details(recipe_id):
    favorite_ids = fetch_favorites(current_user.id, return_ids_only=True)
    recipe = recipe_model.run_query("SELECT * FROM Recipes WHERE id = %s", (recipe_id,))[0]
    

    query = """
        SELECT i.name, ri.measure, ri.units 
        FROM Recipes_ingredients ri 
        JOIN Ingredients i ON ri.ingredient_id = i.id 
        WHERE ri.recipe_id = %s 
        ORDER BY ri.order_index ASC
    """
    ingredients = recipe_model.run_query(query, (recipe_id,))
    meal_index = request.args.get('meal_index', -1, type=int)

    return render_template('recipe_details.html',
                           user_id=current_user.id, 
                           recipe=recipe, 
                           ingredients=ingredients, 
                           meal_index=meal_index,
                           favorite_ids=favorite_ids)

# TODO -fix and finish add_recipe route
# TODO - fix the fact that if you add a new recipe, it doesn't show up in the manual search until you regenerate the menu (because the new recipe is not in the session draft)
# TODO - Add error handling for edge cases (e.g., empty ingredient name, database errors)
@app.route('/add-recipe', methods=['GET', 'POST'])
@login_required
def add_recipe():
    if request.method == 'POST':
        # 1. Get main recipe data
        name = request.form.get('name')
        meal_id = request.form.get('meal_id')
        prep = request.form.get('prep_time')
        cook = request.form.get('cooking_time')
        description = request.form.get('description')
        cat_id = request.form.get('category_id')
        try:
            n_portions = int(request.form.get('n_portions'))
        except (TypeError):
            print("n_portions is not a valid integer. Defaulting to 1.")
            flash("Number of portions must be a valid integer. Defaulting to 1.", "error")
            n_portions = 1
        country_id = request.form.get('country_id')
        file = request.files.get('thumb_file')
        thumb_url = request.form.get('thumb_url')
    
        final_thumb_path = thumb_url # Default to the URL
        print(file)

        # 2. If a file exists and has a filename, save it
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            # Ensure the directory exists
           
            print(f"Saving uploaded file to: {os.path.join(app.config['UPLOAD_FOLDER'], filename)}")
            
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            # This is the path you will store in your Database
            final_thumb_path = f"/{UPLOAD_FOLDER}/{filename}"

        if not n_portions:
            n_portions = 1
        print(f"Final thumbnail path to save: {final_thumb_path}")
        # 2. Insert into Recipes table
        recipe_query = """
            INSERT INTO Recipes (name, country_id, meal_id, category_id, n_portions, prep_time, cooking_time, description, thumb, rating, created_by_user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 10, %s)
        """
        
        # Execute the query and get the new recipe ID
        new_recipe_id = recipe_model.run_query(recipe_query, (name, country_id, meal_id, cat_id, n_portions, prep, cook, description, final_thumb_path, current_user.id))
        
        favorites_recipes_model.insert({
            'user_id': current_user.id,
            'recipe_id': new_recipe_id
        })
        
        # Get ingredient lists from form
        ing_names = request.form.getlist('ing_name[]')
        ing_measures = request.form.getlist('ing_measure[]')
        ing_units = request.form.getlist('ing_unit[]')

        for i in range(len(ing_names)):
            name = ing_names[i].strip().title() 
            if not name: continue

            # 1. Check if ingredient already exists
            existing = ing_model.run_query("SELECT id FROM Ingredients WHERE name = %s", (name,))
            
            if existing:
                ing_id = existing[0]['id']
                print(f"Found existing ingredient '{name}' with ID {ing_id}")
            else:
                # 2. If it doesn't exist, create it
                
                ing_id = ing_model.run_query("INSERT INTO Ingredients (name, created_by_user_id) VALUES (%s, %s)", (name, current_user.id))
                print(f"Created new ingredient '{name}' with ID {ing_id}")
            
            # 3. Link the ingredient to the recipe
            recipe_ingredients_model.run_query(f"""
                INSERT INTO Recipes_ingredients (recipe_id, ingredient_id, measure, units, order_index)
                VALUES (%s, %s, %s, %s, %s)
            """, (new_recipe_id, ing_id, ing_measures[i], ing_units[i], i))

        return redirect(url_for('manual_search', meal_index=-1))

    # GET logic
    categories = recipe_model.run_query("SELECT * FROM Categories")
    meals = recipe_model.run_query("SELECT * FROM Meals")
    countries = recipe_model.run_query("SELECT * FROM Countries")
    # Fetch all ingredients to populate the datalist
    all_ingredients = recipe_model.run_query("SELECT name FROM Ingredients ORDER BY name ASC")
    
    return render_template('add_recipe.html', 
                           categories=categories, 
                           meals=meals,
                           countries=countries,
                           all_ingredients=all_ingredients)


@app.route('/edit-recipe/<int:recipe_id>', methods=['GET'])
@login_required
def edit_recipe(recipe_id):
    recipe = recipe_model.get_by_id(recipe_id)
    ingredients = recipe_ingredients_model.run_query("""
        SELECT ri.*, i.name as name
        FROM Recipes_ingredients ri
        JOIN Ingredients i ON ri.ingredient_id = i.id
        WHERE ri.recipe_id = %s
        ORDER BY ri.order_index ASC
    """, (recipe_id,))

# TODO COMBINE WITH THE BACKWARD CONVERSION AND MAKE GLOBAL
    def format_td(td):
        if td is None:
            return "00:00"
        # total_seconds handles cases where the duration is > 24 hours
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours:02}:{minutes:02}"
    
    recipe['prep_time'] = format_td(recipe['prep_time'])
    recipe['cooking_time'] = format_td(recipe['cooking_time'])

    categories = recipe_model.run_query("SELECT * FROM Categories")
    meals = recipe_model.run_query("SELECT * FROM Meals")
    countries = recipe_model.run_query("SELECT * FROM Countries")
    return render_template('edit_recipe.html', 
                           recipe=recipe, 
                           ingredients=ingredients, 
                           categories=categories, 
                           meals=meals, 
                           countries=countries)


@app.route('/save-changes/<int:recipe_id>', methods=['POST'])
@login_required
def save_changes(recipe_id):
    # Get form data
    name = request.form.get('name')
    country_id = request.form.get('country_id')
    meal_id = request.form.get('meal_id')
    cat_id = request.form.get('category_id')
    n_portions = request.form.get('n_portions')
    prep = request.form.get('prep_time')
    cook = request.form.get('cooking_time')
    description = request.form.get('description')
    file = request.files.get('thumb_file')
    thumb_url = request.form.get('thumb_url')


    if file and file.filename != '':
            filename = secure_filename(file.filename)
            # Ensure the directory exists
           
            print(f"Saving uploaded file to: {os.path.join(app.config['UPLOAD_FOLDER'], filename)}")
            
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            # This is the path you will store in your Database
            thumb_url = f"/{UPLOAD_FOLDER}/{filename}"
    print(f"Final thumbnail path to save: {thumb_url}")
    # Update the recipe in the database
    query = """
        UPDATE Recipes 
        SET name=%s, country_id=%s, meal_id=%s, category_id=%s, n_portions=%s, prep_time=%s, cooking_time=%s, description=%s, thumb=%s
        WHERE id=%s
    """
    recipe_model.run_query(query, (name, country_id, meal_id, cat_id, n_portions, prep, cook, description, thumb_url, recipe_id))

    # Update ingredients for this recipe
    ing_names = request.form.getlist('ing_name[]')
    ing_measures = request.form.getlist('ing_measure[]')
    ing_units = request.form.getlist('ing_unit[]')

    # Clear existing ingredients for this recipe
    recipe_ingredients_model.run_query("DELETE FROM Recipes_ingredients WHERE recipe_id=%s", (recipe_id,))
    
    for i in range(len(ing_names)):
        name = ing_names[i].strip().title() 
        if not name: continue

        # Check if ingredient already exists
        existing = ing_model.run_query("SELECT id FROM Ingredients WHERE name = %s", (name,))
        
        if existing:
            ing_id = existing[0]['id']
            print(f"Found existing ingredient '{name}' with ID {ing_id}")
        else:
            # Create new ingredient if it doesn't exist
            ing_id = ing_model.run_query("INSERT INTO Ingredients (name, created_by_user_id) VALUES (%s, %s)", (name, current_user.id))
            print(f"Created new ingredient '{name}' with ID {ing_id}")
        
        # Link the ingredient to the recipe
        recipe_ingredients_model.run_query("""
            INSERT INTO Recipes_ingredients (recipe_id, ingredient_id, measure, units, order_index)
            VALUES (%s, %s, %s, %s, %s)
        """, (recipe_id, ing_id, ing_measures[i], ing_units[i], i))

    return redirect(url_for('manual_search', meal_index=-1))


@app.route('/favorites')
@login_required
def favorites():
    favorites = fetch_favorites(current_user.id)
    return render_template('favorites.html', favorites=favorites)


@app.route('/add-favorite/<int:recipe_id>', methods=['POST'])
@login_required
def add_favorite(recipe_id):
    # In a real app, you would check if the user is logged in and get their user_id

    # Insert into User_favorite_recipes table
    query = """
        INSERT INTO User_favorite_recipes (user_id, recipe_id)
        VALUES (%s, %s)
    """
    favorites_recipes_model.run_query(query, (current_user.id, recipe_id))
    
    return redirect(request.referrer or url_for('manual_search', meal_index=-1))


@app.route('/remove-favorite/<int:recipe_id>', methods=['POST'])
@login_required
def remove_favorite(recipe_id):
    # In a real app, you would check if the user is logged in and get their user_id

    # Remove from User_favorite_recipes table
    query = """
        DELETE FROM User_favorite_recipes
        WHERE user_id = %s AND recipe_id = %s
    """
    favorites_recipes_model.run_query(query, (current_user.id, recipe_id))
    
    return redirect(request.referrer or url_for('manual_search', meal_index=-1))


@app.route('/history')
@login_required
def history():
    meals_query = """
        SELECT mm.menu_id,
               mm.meal_id,
               mm.meal_time,
               ms.`name` as meal_type,
               r.`name` as recipe_name,
               mm.recipe_id

        FROM Menu_meals mm
        JOIN Menus m ON mm.menu_id = m.id
        JOIN Recipes r ON mm.recipe_id = r.id
        JOIN Meals ms ON mm.meal_id = ms.id
        WHERE m.user_id = %s
        ORDER BY m.created_at DESC, mm.meal_time ASC;
    """
    history_query = """SELECT id, date(created_at) as `date` FROM Menus WHERE user_id = %s;"""

    history = recipe_model.run_query(history_query, (current_user.id,))
    meals = recipe_model.run_query(meals_query, (current_user.id,))
    print(history)

    for entry in history:
        entry['date'] = entry['date'].strftime("%B %d, %Y")
        entry['meals'] = [meal for meal in meals if meal['menu_id'] == entry['id']]
    print("Meals associated with history entries:")
    print(history)

    return render_template('history.html', history=history)



@app.route('/shopping-list/<int:menu_id>', methods=['GET', 'POST'])
@login_required
def shopping_list(menu_id):
    today = datetime.now(timezone.utc).date()

    # 1. CHECK IF A LIST ALREADY EXISTS FOR TODAY
    # This prevents creating 100 rows if the user refreshes 100 times
    check_query = "SELECT id, created_at FROM Shopping_list WHERE menu_id = %s AND DATE(created_at) = %s LIMIT 1"
    existing_list = recipe_model.run_query(check_query, (menu_id, today))

    if existing_list:
        shopping_list_id = existing_list[0]['id']
    else:
        # Create it only if it doesn't exist
        create_query = "INSERT INTO Shopping_list (menu_id) VALUES (%s)"
        shopping_list_id = recipe_model.run_query(create_query, (menu_id,))

    # 2. GET INITIAL ITEMS (Aggregated from Menu)
    db_query = """SELECT i.`name`, SUM(ri.measure) AS measure, ri.units
                  FROM Recipes_ingredients ri
                  JOIN Menu_meals mm on ri.recipe_id = mm.recipe_id
                  JOIN Ingredients i on i.id = ri.ingredient_id 
                  WHERE mm.menu_id = %s GROUP BY 1, 3 ORDER BY 1"""
    shopping_list_items = recipe_model.run_query(db_query, (menu_id,))

    # 3. HANDLE POST (SAVING)
    if request.method == 'POST':
        names = request.form.getlist('item_names[]')
        measures = request.form.getlist('item_measures[]')
        units = request.form.getlist('item_units[]')
        checked_statuses = request.form.getlist('item_checked[]')

        # Clear old ingredients for this specific list to avoid duplicates on re-save
        recipe_model.run_query("DELETE FROM Shopping_list_ingredients WHERE shop_list_id = %s", (shopping_list_id,))

        for i in range(len(names)):
            name = names[i].strip().title()
            
            # Find or Create Ingredient
            ing_res = recipe_model.run_query("SELECT id FROM Ingredients WHERE name = %s", (name,))
            if ing_res:
                ing_id = ing_res[0]['id']
            else:
                ing_id = recipe_model.run_query("INSERT INTO Ingredients (name, created_by_user_id) VALUES (%s, %s)", (name, current_user.id))

            # INSERT into Shopping_list_ingredients
            insert_query = """INSERT INTO Shopping_list_ingredients (shop_list_id, ingredient_id, measure, units, if_checked) 
                              VALUES (%s, %s, %s, %s, %s)"""
            recipe_model.run_query(insert_query, (shopping_list_id, ing_id, measures[i], units[i], checked_statuses[i]))

        # Update view to show what was just saved
        return redirect(url_for('shopping_list', menu_id=menu_id))

    return render_template('shopping_list.html', items=shopping_list_items, menu_id=menu_id)


@app.route('/signin', methods=['GET', 'POST'])
def signin():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        
        user_data = recipe_model.run_query("SELECT * FROM Users WHERE email = %s", (email,))
        
        if user_data and check_password_hash(user_data[0]['password_hash'], password):
            user_obj = User(user_data[0])
            login_user(user_obj)
            return redirect(url_for('menu'))
        else:
            # Send a message to the next page
            flash('Invalid email or password. Please try again or sign up!', 'error')
            return redirect(url_for('signin')) # Refresh the page to show the error
    
    return render_template('signin.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password') # <--- Check this name!
        confirm_password = request.form.get('confirm_password')

        role_id = recipe_model.run_query("SELECT id FROM User_roles WHERE name = %s", ('user',))[0]['id']
        print(role_id)

        # This must be INSIDE the if block
        if password and password == confirm_password: 
            hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
            
            # Use your model to save
            query = "INSERT INTO Users (user_name, email, role_id, password_hash) VALUES (%s, %s, %s, %s)"
            recipe_model.run_query(query, (username, email, role_id, hashed_pw))
            
            return redirect(url_for('signin'))
        else:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('signup'))

    # This handles the GET request
    return render_template('signup.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("You have been successfully logged out. See you next time!", "info")
    return redirect(url_for('signin'))


@app.route('/preferences')
@login_required
def preferences():
    return render_template('preferences.html')


@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html')


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500


if __name__ == '__main__':
    app.run(debug=True)

    scheduler = BackgroundScheduler()
    scheduler.add_job(func=send_meal_reminders, trigger="interval", minutes=5)
    scheduler.start()

    # Shut down the scheduler when the app exits
    atexit.register(lambda: scheduler.shutdown())
        