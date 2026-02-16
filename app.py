from flask import Flask, render_template, redirect, url_for, request, session
from flask_scss import Scss
import database.models as m
import random
from datetime import datetime, timedelta, date, timezone

meal_model = m.MealsModel()
menu_model = m.MenuModel()
menu_meals_model = m.MenuMealsModel()
users_model = m.UsersModel()
recipe_model = m.RecipesModel()
ing_model = m.IngredientsModel()

meals_from_db = meal_model.get_all()

app = Flask(__name__)
app.secret_key = 'your_super_secret_random_string_here'

Scss(app, static_dir='static', asset_dir='assets')


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

def fetch_user(user_name):
    """Fetch user_id by user_name."""
    query = "SELECT id FROM Users WHERE user_name = %s"
    users = users_model.run_query(query, (user_name,))
    return users[0]['id'] if users else None


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


user_id = fetch_user('test_user')


@app.route('/')
def home():
    return render_template('index.html')


# route for menu page
@app.route('/menu')
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
        draft_meals, menu_id, success_message = fetch_today_menu(user_id=user_id)
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
def init_plan():
    # 1. Get the list of names from the checkboxes
    selected_names = request.form.getlist('meals')
    if not selected_names:
        error_message="Please select at least one meal!"

    menu_meals = []

    # Check if a menu already exists for today
    menu_meals, menu_id, success_message = fetch_today_menu(user_id=user_id)
    error_message = None

    if menu_id:
        error_message = "A menu for today already exists. You cannot create a new one."
        
    else:
        # 2. Create a new menu and get its ID
        menu_id = menu_model.insert({'user_id': user_id})

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


@app.route('/submit-final-menu', methods=['POST'])
def submit_final_menu():
    menu_id = request.form.get('menu_id')
    meal_ids = request.form.getlist('meal_id[]')
    recipe_ids = request.form.getlist('recipe_id[]')
    regen_counts = request.form.getlist('regenerated_times[]')
    if_manually_flags = request.form.getlist('if_picked_manually[]')
    meal_time = request.form.getlist('meal_time[]')

    # Loop through the lists by index
    for i in range(len(meal_ids)):
        m_id = meal_ids[i]
        
        # Pull specific values using the unique meal_id key
        time = meal_time[i]
        is_leftover = 1 if request.form.get(f'leftover_{m_id}') else 0
        
        # INSERT into Menu_meals table
        menu_meals_model.insert({
            'menu_id': menu_id,
            'meal_id': m_id,
            'recipe_id': recipe_ids[i],
            'meal_time': time,
            'is_leftover_plan': is_leftover,
            'regenerated_times': regen_counts[i],
            'if_picked_manually': if_manually_flags[i]
        })

    # Finalize the menu timestamp
    menu_model.update(menu_id, {
        'submitted_at': datetime.now(timezone.utc)
    })
    
    session.pop('menu_draft', None)

    return render_template('menu.html', 
                           all_meals=meals_from_db, # Use the global list
                           success_message="Menu finalized and saved!")


@app.route('/manual-search/<int(signed=True):meal_index>')
def manual_search(meal_index):
    print('**'*20)
    print(f'meal_index: {meal_index}')
    print('**'*20)
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
                           search_query=search_query)

@app.route('/select-recipe/<int:meal_index>/<int:recipe_id>', methods=['POST'])
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
def recipe_details(recipe_id):
    recipe = recipe_model.run_query("SELECT * FROM Recipes WHERE id = %s", (recipe_id,))[0]
    
    # Ensure the triple quotes are closed correctly
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
                           recipe=recipe, 
                           ingredients=ingredients, 
                           meal_index=meal_index)

# TODO -fix and finish add_recipe route
# TODO - fix the fact that if you add a new recipe, it doesn't show up in the manual search until you regenerate the menu (because the new recipe is not in the session draft)
# TODO - Add error handling for edge cases (e.g., empty ingredient name, database errors)
@app.route('/add-recipe', methods=['GET', 'POST'])
def add_recipe():
    if request.method == 'POST':
        # 1. Get main recipe data
        name = request.form.get('name')
        thumb = request.form.get('thumb')
        meal_id = request.form.get('meal_id')
        prep = request.form.get('prep_time')
        cook = request.form.get('cooking_time')
        cat_id = request.form.get('category_id')
        country_id = request.form.get('country_id')
        area = request.form.get('area')
          
        # 2. Insert into Recipes table
        recipe_query = """
            INSERT INTO Recipes (name, country_id, meal_id, category_id, n_portions, prep_time, cooking_time, area, thumb, rating, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 5, NOW())
        """
        recipe_model.run_query(recipe_query, (name, country_id, meal_id, cat_id, 1, prep, cook, area, thumb,))
        
        # Get the ID of the recipe we just created
        new_recipe_id = recipe_model.run_query("SELECT LAST_INSERT_ID() as id")[0]['id']
        
        # Get ingredient lists from form
        ing_names = request.form.getlist('ing_name[]')
        ing_measures = request.form.getlist('ing_measure[]')
        ing_units = request.form.getlist('ing_unit[]')

        for i in range(len(ing_names)):
            name = ing_names[i].strip()
            if not name: continue

            # 1. Check if ingredient already exists
            existing = ing_model.run_query("SELECT id FROM Ingredients WHERE name = %s", (name,))
            
            if existing:
                ing_id = existing[0]['id']
            else:
                # 2. If it doesn't exist, create it
                ing_model.run_query("INSERT INTO Ingredients (name) VALUES (%s)", (name,))
                ing_id = ing_model.run_query("SELECT LAST_INSERT_ID() as id")[0]['id']
            
            # TODO FIX THIS, WRONG MODEL
            # 3. Link the ingredient to the recipe
            recipe_model.run_query("""
                INSERT INTO Recipes_ingredients (recipe_id, ingredient_id, measure, units, order_index)
                VALUES (%s, %s, %s, %s, %s)
            """, (new_recipe_id, ing_id, ing_measures[i], ing_units[i], i))

        return redirect(url_for('manual_search', meal_index=-1))

    # GET logic
    categories = recipe_model.run_query("SELECT * FROM Categories")
    meals = recipe_model.run_query("SELECT * FROM Meals")
    # Fetch all ingredients to populate the datalist
    all_ingredients = recipe_model.run_query("SELECT name FROM Ingredients ORDER BY name ASC")
    
    return render_template('add_recipe.html', 
                           categories=categories, 
                           meals=meals, 
                           all_ingredients=all_ingredients)

@app.route('/signin')
def signin():
    return render_template('signin.html')


@app.route('/signup')
def signup():
    return render_template('signup.html')


@app.route('/preferences')
def preferences():
    return render_template('preferences.html')


@app.route('/profile')
def profile():
    return render_template('profile.html')


if __name__ == '__main__':
    app.run(debug=True)
    
    