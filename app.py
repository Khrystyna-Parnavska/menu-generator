import atexit
from calendar import c
from multiprocessing.util import close_all_fds_except
import re
from tkinter import CURRENT, N
from tracemalloc import start
from unicodedata import category
from unittest.mock import Base

from numpy import integer
from database.models import BaseModel
import random
import os
from gettext import install
from time import strftime
from flask import Flask, flash, jsonify, render_template, redirect, url_for, request, session
from flask_mail import Mail, Message
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta, time, timezone
from werkzeug.utils import secure_filename
from flask import make_response
from zoneinfo import ZoneInfo

UPLOAD_FOLDER = 'static/uploads'

meal_model = BaseModel('Meals')
menu_model = BaseModel('Menus')
menu_meals_model = BaseModel('Menu_meals')
users_model = BaseModel('Users') 
recipe_model = BaseModel('Recipes')
ing_model = BaseModel('Ingredients')
recipe_ingredients_model = BaseModel('Recipes_Ingredients')
favorites_recipes_model = BaseModel('User_favorite_recipes')
recipe_categories_model = BaseModel('Recipe_categories')
country_model = BaseModel('Countries')
source_model = BaseModel('Data_sources')
shopping_list_model = BaseModel('Shopping_list')
shopping_list_items_model = BaseModel('Shopping_list_ingredients')


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


app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
print(app.config['UPLOAD_FOLDER'])
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


def clean_menu_draft(user_id):
    user_tz = users_model.select_by_id(user_id)['timezone'] or 'UTC'
    current_date = local_time_to_utc_range(user_tz, return_now=True)[2].date()  # Get current local date in user's timezone
    unfinished_menu = menu_model.run_query("SELECT * FROM Menus WHERE user_id = %s AND DATE(created_at) = %s AND submitted_at IS NULL", (user_id, current_date))
    if unfinished_menu:
        menu_id = unfinished_menu[0]['id']
        menu_model.run_query("DELETE FROM Menus WHERE id = %s", (menu_id,))


def match_meal_to_recipe(meal_id:int, cols)->str:
        meal_name = meal_model.select_by_id(meal_id)['name']
        for col in cols:
            if meal_name.lower() in col.lower().replace('_', ' '):
                return col
        return None


def group_by_category(items):
    """
    Transforms a flat list of dictionaries into a grouped dictionary.
    Input: [{'name': 'Apple', 'category': 'Fruit', ...}, {'name': 'Milk', 'category': 'Dairy', ...}]
    Output: {'Fruit': [{'name': 'Apple', ...}], 'Dairy': [{'name': 'Milk', ...}]}
    """
    grouped = {}
    for item in items:
        # Use 'Other' if category is somehow missing
        cat = item.get('category') or 'Other'
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(item)
    return grouped


def fetch_recipe_form_and_update_db(operation_type:str, recipe_id=None)->None:
    '''
    this function handles both inserting a new recipe and updating an existing one,
    depending on the operation_type parameter. It extracts all relevant data from 
    the form, processes it, and then updates the database accordingly.
    operation_type: 'INSERT' or 'UPDATE' - whether we're adding a new recipe or 
    updating an existing one
    '''

    # 1. Get main recipe data
    name = request.form.get('name').strip().title()
    meal_ids = request.form.getlist('meal_ids')

    prep_h = request.form.get('prep_hours', 0)
    prep_m = request.form.get('prep_minutes', 0)
    cook_h = request.form.get('cooking_hours', 0)
    cook_m = request.form.get('cooking_minutes', 0)
    prep_time = timedelta(hours=int(prep_h or 0), minutes=int(prep_m or 0))
    cooking_time = timedelta(hours=int(cook_h or 0), minutes=int(cook_m or 0)) 

    instructions = request.form.get('instructions')
    cat_id = request.form.get('category_id')
    try:
        n_portions = int(request.form.get('n_portions'))
    except (TypeError, ValueError):
        flash("Number of portions must be a valid integer. Defaulting to 1.", "error")
        n_portions = 1
    country_id = request.form.get('country_id')
    file = request.files.get('thumb_file')
    thumb_url = request.form.get('thumb_url')
    
    final_thumb_path = thumb_url # Default to the URL

    # 2. If a file exists and has a filename, save it
    if file and file.filename != '':
        filename = secure_filename(file.filename)
        # Ensure the directory exists
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
            
        # This is the path you will store in your Database
        final_thumb_path = f"/{UPLOAD_FOLDER}/{filename}"

    if not n_portions:
        n_portions = 1

    country_name = country_model.select_by_id(country_id)['name'] if country_id else None

    if operation_type == 'UPDATE':
        new_recipe_id = recipe_id
        # FIX 3: Removed meal_id from here because you use flags now
        recipe_query = """
            UPDATE Recipes 
            SET name=%s, country_id=%s, category_id=%s, n_portions=%s, 
                prep_time=%s, cooking_time=%s, instructions=%s, area=%s, thumb=%s
            WHERE id=%s
        """

        recipe_model.run_query(recipe_query, (name, country_id, cat_id, n_portions, 
                               prep_time, cooking_time, instructions, country_name, 
                               final_thumb_path, new_recipe_id))
        
        # FIX 2: Reset all meal flags to 0 before applying new ones
        meal_cols = [c for c in recipe_model.columns if c.startswith('if_')]
        for col in meal_cols:
            recipe_model.run_query(f"UPDATE Recipes SET {col} = 0 WHERE id = %s", (new_recipe_id,))

    elif operation_type == 'INSERT':
        recipe_query = f"""
                INSERT INTO Recipes (name, country_id, category_id, n_portions, prep_time, cooking_time, instructions, area, thumb, rating, created_by_user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 10, %s)
            """
        new_recipe_id = recipe_model.run_query(recipe_query, (name, country_id, cat_id, n_portions, prep_time, cooking_time, instructions, country_name, final_thumb_path, current_user.id))

        favorites_recipes_model.insert({
            'user_id': current_user.id,
            'recipe_id': new_recipe_id
            })
            
    else:
        raise ValueError("Invalid operation type. Must be 'INSERT' or 'UPDATE'.")

    # 3. Insert flags for meal types in the Recipes table
    for meal_id in meal_ids:
        col = match_meal_to_recipe(meal_id, recipe_model.columns)
        if col:
            recipe_model.run_query(f"UPDATE Recipes SET {col} = 1 WHERE id = %s", (new_recipe_id,))
        
    # Get ingredient lists from form
    ing_names = request.form.getlist('ing_name[]')
    ing_measures = request.form.getlist('ing_measure[]')
    ing_units = request.form.getlist('ing_unit[]')
    ing_prep_notes = request.form.getlist('ing_prep_notes[]')

    # Clear existing ingredients for this recipe
    recipe_ingredients_model.run_query("DELETE FROM Recipes_ingredients WHERE recipe_id=%s", (new_recipe_id,))

    for i in range(len(ing_names)):
        name = ing_names[i].strip().title() 
        if not name: continue

        # 1. Check if ingredient already exists
        existing = ing_model.run_query("SELECT id FROM Ingredients WHERE name = %s", (name,))
            
        if existing:
            ing_id = existing[0]['id']
        else:
            # 2. If it doesn't exist, create it
                
            ing_id = ing_model.run_query("INSERT INTO Ingredients (name, created_by_user_id) VALUES (%s, %s)", (name, current_user.id))
            
        # 3. Link the ingredient to the recipe
        recipe_ingredients_model.run_query(f"""
                INSERT INTO Recipes_ingredients (recipe_id, ingredient_id, measure, unit_id, prep_notes, order_index)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (new_recipe_id, ing_id, ing_measures[i], ing_units[i], ing_prep_notes[i], i))

def clear_drafts_at_midnight():
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=clean_menu_draft, trigger='cron', hour=0, minute=0)
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())


def local_time_to_utc_range(user_timezone= None, return_now=False)->tuple:
    '''This function takes a user's timezone as input and returns the corresponding UTC start and end datetimes for the current local day in that timezone. 
    This is useful for ensuring that all users, regardless of their location, see the same "day" when they access the app, and that any time-based logic (like meal reminders) 
    works correctly across timezones.'''
    if not user_timezone:
        user_timezone = users_model.select_by_id(current_user.id)['timezone'] or 'UTC'
    user_tz = ZoneInfo(user_timezone)
    now_local = datetime.now(user_tz)

    # 2. Calculate the exact Start and End of the local day
    # Start: 2026-04-02 00:00:00 Stockholm
    local_start = datetime.combine(now_local.date(), time.min).replace(tzinfo=user_tz)
    # End: 2026-04-02 23:59:59 Stockholm
    local_end = datetime.combine(now_local.date(), time.max).replace(tzinfo=user_tz)

    # 3. Convert those specific moments to UTC
    utc_start = local_start.astimezone(timezone.utc)
    utc_end = local_end.astimezone(timezone.utc)
    if return_now:
        return utc_start, utc_end, now_local
    return utc_start, utc_end

    
def generate_meal(meal_id, return_recipe_list=False)->list[dict]:
    '''This function generates a meal by taking a meal_id (which corresponds to a meal type like breakfast, lunch, etc.) and randomly selecting a recipe from the 
    database that matches that meal type.
    Returns a single recipe dictionary in a list if return_recipe_list is False, or a list of matching recipes if return_recipe_list is True.'''
    col = match_meal_to_recipe(meal_id, recipe_model.columns)
    list_recipes = recipe_model.run_query(f"SELECT * FROM Recipes WHERE {col} = %s", (1,))
    if return_recipe_list:
        return list_recipes
    recipe = random.choice(list_recipes)
    return [recipe]
 


def generate_menu(menu_id:int, selected_meals:list)->list[dict]: 
    '''This function generates a menu by taking a menu_id and a list of selected meal types 
    (e.g., breakfast, lunch, dinner) and creating a draft menu with randomly selected recipes for each meal type.
    Returns a list of dictionaries, where each dictionary represents a meal in the menu with its associated recipe and details.'''
    draft_menu_meals = []

    for name in selected_meals:
            
            meal = meal_model.run_query("SELECT id, default_time FROM Meals WHERE name = %s", (name,))[0]
            meal_id = meal['id']
            meal_time_default = meal['default_time']

            recipe = generate_meal(meal_id)[0]

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


def fetch_today_menu()->tuple:
    '''This function checks if the user already has a menu for today in the database. If they do, it retrieves that menu and its associated meals. 
    If not, it returns an empty list, indicating that a new menu should be generated. It also handles timezone conversion to ensure that "today" 
    is based on the user's local time.
    Returns a tuple containing the list of meals for today's menu, the menu_id if it exists, and a success message if the menu has already been submitted.'''
    user_timezone = request.form.get('user_timezone', users_model.select_by_id(current_user.id)['timezone'] or 'UTC')

    start_utc, end_utc, now_local = local_time_to_utc_range(user_timezone, return_now=True)
    print(f'local start: {start_utc}, local end: {end_utc}, now_local: {now_local}')

    query_today = """
        SELECT *, DATE(created_at) as created_date FROM Menus 
        WHERE user_id = %s
        AND created_at BETWEEN %s AND %s  
        ORDER BY created_at DESC
        LIMIT 1
    """
    latest_menu = menu_model.run_query(query_today, (current_user.id, start_utc, end_utc))

    draft_meals = []
    menu_id = None
    success_message = None # Default to None

    if latest_menu and (latest_menu[0]['created_date'] == now_local.date()):
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


def fetch_menu_by_date(user_id, menu_date):
    '''This function retrieves a menu for a specific user on a specific date. 
    If a menu exists, it returns the menu; otherwise, it returns None.'''
    query = """
        SELECT *, DATE(created_at) as created_date FROM Menus
        WHERE user_id = %s
        AND DATE(menu_date) = %s
        ORDER BY created_at DESC
        LIMIT 1
    """
    menu = menu_model.run_query(query, (user_id, menu_date))
    return menu[0] if menu else None


def fetch_favorites(user_id, return_ids_only=False):
    '''This function retrieves the favorite recipes for a specific user. If return_ids_only is True, it returns a list of recipe IDs; otherwise, 
    it returns the full recipe details.'''
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


meals_from_db = meal_model.select_all()

def send_meal_reminders():
    with app.app_context():
        with app.app_context(): # Ensure we have access to the app config
        # 1. Fetch all users from the database
            all_users = users_model.select_all() 
        
            for user in all_users:
                user_id = user['id']
                user = users_model.select_by_id(user_id)
                user_tz = user['timezone'] or 'UTC'
                
                local_now = local_time_to_utc_range(user_tz, return_now=True)[2]  # Get current local time in user's timezone
                query = """
                    SELECT mm.id, u.email, r.name as recipe_name, mm.meal_time 
                    FROM Menu_meals mm
                    JOIN Menus m ON mm.menu_id = m.id
                    JOIN Users u ON m.user_id = u.id
                    JOIN Recipes r ON mm.recipe_id = r.id
                    WHERE mm.meal_time BETWEEN %s AND DATE_ADD(%s, INTERVAL 30 MINUTE)
                    AND mm.reminder_sent = 0
                """
                upcoming_meals = recipe_model.run_query(query, (local_now, local_now))

                for meal in upcoming_meals:
                    msg = Message("🍳 Time to Cook!",
                                sender="your-email@gmail.com",
                                recipients=[meal['email']])
                    msg.body = f"Hi! It's almost time for your meal. Start preparing {meal['recipe_name']} now!"
                    mail.send(msg)
                    print(f"Sent meal reminder for {meal['recipe_name']} to {meal['email']}.")
                    # Mark as sent so we don't spam the user
                    recipe_model.run_query("UPDATE Menu_meals SET reminder_sent = 1 WHERE id = %s", (meal['id'],))


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/menu')
@login_required
def menu():
    # 1. Get all meal types for the "Include Meals" checkboxes
    all_meals = meal_model.select_all()
    
    # 2. Fetch all menus for this user that have NOT been submitted yet
    # We order by date so the oldest draft appears first
    query_drafts = """
        SELECT id, menu_date 
        FROM Menus 
        WHERE user_id = %s AND submitted_at IS NULL 
        ORDER BY menu_date ASC
    """
    db_drafts = menu_model.run_query(query_drafts, (current_user.id,))
    
    menu_drafts_formatted = []

    for draft in db_drafts:
        m_id = draft['id']
        m_date = draft['menu_date']

        # 3. Fetch the meals for this specific draft ID
        query_meals = """
            SELECT mm.*, r.name as recipe_name, m.name as meal_type 
            FROM Menu_meals mm
            JOIN Recipes r ON mm.recipe_id = r.id
            JOIN Meals m ON mm.meal_id = m.id
            WHERE mm.menu_id = %s
            ORDER BY mm.meal_time ASC
        """
        meals = menu_meals_model.run_query(query_meals, (m_id,))

        # 4. Format time (HH:MM) for the HTML time input
        for meal in meals:
            if meal['meal_time'] and hasattr(meal['meal_time'], 'total_seconds'):
                ts = int(meal['meal_time'].total_seconds())
                meal['meal_time'] = f"{ts//3600:02}:{(ts%3600)//60:02}"
            elif not meal['meal_time']:
                meal['meal_time'] = "12:00" # Default if none set

        # 5. Structure it into the {menu_id: {date: [meals]}} format expected by menu.html
        menu_drafts_formatted.append({m_id: {m_date: meals}})

    return render_template('menu.html', 
                           all_meals=all_meals, 
                           menus=menu_drafts_formatted)

@app.route('/init-plan', methods=['POST'])
@login_required
def init_plan():
    # 1. Get the list of names from the checkboxes
    selected_names = request.form.getlist('meals')
    user_time_zone = request.form.get('user_timezone', 'UTC')
    start_date = request.form.get('start_date')
    duration_days = request.form.get('duration_days')
    if not selected_names:
        error_message="Please select at least one meal!"
        return render_template('menu.html', error=error_message, all_meals=meals_from_db)

    current_date = datetime.now(ZoneInfo(user_time_zone)).date()
    last_valid_date = current_date + timedelta(days=7)
    n_menus_in_range = menu_model.run_query("""
        SELECT COUNT(*) as count FROM Menus
        WHERE user_id = %s AND menu_date > %s
    """, (current_user.id, current_date))[0]['count']
    if not start_date:
        error_message="Please select a start date!"
        return render_template('menu.html', error=error_message, all_meals=meals_from_db)
    elif datetime.strptime(start_date, '%Y-%m-%d').date() < current_date:
        error_message="Start date cannot be in the past!"
        return render_template('menu.html', error=error_message, all_meals=meals_from_db)
    elif current_date == datetime.strptime(start_date, '%Y-%m-%d').date():
        error_message="Start date cannot be today, please use the 'Regenerate' button for today's meals!"
        return render_template('menu.html', error=error_message, all_meals=meals_from_db)
    elif datetime.strptime(start_date, '%Y-%m-%d').date() > last_valid_date:
        error_message="Start date cannot be more than 7 days in the future!"
        return render_template('menu.html', error=error_message, all_meals=meals_from_db)
    elif n_menus_in_range >= 7:
        error_message="You already have 7 menus scheduled in the future. Please edit or delete existing menus before adding new ones."
        return render_template('menu.html', error=error_message, all_meals=meals_from_db)
    
    menu_drafts = []

    for day in range(int(duration_days or 1)):
        current_date = datetime.strptime(start_date, '%Y-%m-%d').date() + timedelta(days=day)
        if_draft_already_exists = menu_model.run_query("""
            SELECT id FROM Menus WHERE user_id = %s AND menu_date = %s
        """, (current_user.id, current_date))
        if if_draft_already_exists:
            error_message = f"A menu for {current_date} already exists. Please choose a different date range or edit the existing menu."
            return render_template('menu.html', error=error_message, all_meals=meals_from_db)
    
        menu_current_date = fetch_menu_by_date(current_user.id, current_date)
        if menu_current_date:
            menu_id = menu_current_date['id']
            menu_if_submitted = menu_current_date['submitted_at'] is not None
            query_meals = """
                SELECT mm.*, r.name as recipe_name, m.name as meal_type 
                FROM Menu_meals mm
                JOIN Recipes r ON mm.recipe_id = r.id
                JOIN Meals m ON mm.meal_id = m.id
                WHERE mm.menu_id = %s
            """
            menu_meals = menu_meals_model.run_query(query_meals, (menu_id,))
            flash(f"Menu for {current_date} already exists and has been loaded.", "info")

            if menu_id and menu_if_submitted:
                error_message = f"A menu for {current_date} already exists and has been submitted. You cannot create a new one."
                return render_template('menu.html', error=error_message, all_meals=meals_from_db)
            
        else:
            # 2. Create a new menu and get its ID
            menu_id = menu_model.insert({'user_id': current_user.id, 'menu_date': current_date})
            menu_meals = generate_menu(menu_id, selected_names)
            for meal in menu_meals:
                try:
                    meal['regenerated_times'] = 0
                    meal['if_picked_manually'] = 0
                    menu_meals_model.insert({
                        'menu_id': meal['menu_id'],
                        'meal_id': meal['meal_id'],
                        'recipe_id': meal['recipe_id'],
                        'meal_time': meal['meal_time'],
                        'regenerated_times': meal['regenerated_times'],
                        'if_picked_manually': meal['if_picked_manually']
                    })
                except Exception as e:
                    print(f"Error inserting meal into database: {e}")
                    error_message = f"An error occurred while saving your {meal['meal_type']} for {current_date}. Please try again."
                    return render_template('menu.html', error=error_message, all_meals=meals_from_db)
        menu_drafts.append({menu_id: {current_date: menu_meals}})
        success_message = "Your meal plan has been initialized! You can view and edit each day's meals by clicking the 'Regenerate' button for that day."

    return render_template('menu.html', 
                           menus=menu_drafts, 
                           all_meals=meals_from_db,
                           success_message=success_message)

@app.route('/regenerate_meal/<int:meal_index>', methods=['POST'])
@login_required
def regenerate_meal(meal_index):
    # Adjusting index to match meal_id in DB
    db_meal_id = meal_index + 1 
    menu_id = request.form.get('menu_id')
    
    if not menu_id:
        return redirect(url_for('menu'))

    # 1. Fetch current meal to get its existing time
    query = "SELECT meal_time, meal_id FROM Menu_meals WHERE menu_id = %s AND meal_id = %s"
    current_meal_data = menu_meals_model.run_query(query, (menu_id, db_meal_id))
    
    if not current_meal_data:
        flash("Meal not found in drafts.", "error")
        return redirect(url_for('menu'))
    
    existing_time = current_meal_data[0]['meal_time']

    # 2. Generate the new recipe
    new_recipe = generate_meal(db_meal_id)

    if new_recipe and len(new_recipe) > 0:
        try:
            # 3. Update using the existing_time we just fetched
            update_query = """
                UPDATE Menu_meals 
                SET recipe_id = %s, 
                    meal_time = %s, 
                    regenerated_times = regenerated_times + 1,
                    if_picked_manually = 0
                WHERE menu_id = %s AND meal_id = %s
            """
            menu_meals_model.run_query(update_query, (
                new_recipe[0]['id'], 
                existing_time, # Keeps the time the user may have already set
                menu_id, 
                db_meal_id
            ))
            flash(f"Regenerated to {new_recipe[0]['name']}", "success")
        except Exception as e:
            print(f"Database Error: {e}")
            flash("Failed to update database.", "error")
    else:
        flash("No alternative recipes found.", "warning")

    return redirect(url_for('menu'))

@app.route('/regenerate_full_menu/<int:menu_id>', methods=['POST'])
@login_required
def regenerate_full_menu(menu_id):
    # 1. Fetch all meal slots currently in this draft
    query = "SELECT meal_id FROM Menu_meals WHERE menu_id = %s"
    current_meals = menu_meals_model.run_query(query, (menu_id,))

    if not current_meals:
        flash("Menu not found.", "error")
        return redirect(url_for('menu'))

    # 2. Loop through every meal and update it with a new random recipe
    for meal in current_meals:
        db_meal_id = meal['meal_id']
        new_recipe = generate_meal(db_meal_id)
        
        if new_recipe:
            update_query = """
                UPDATE Menu_meals 
                SET recipe_id = %s, 
                    regenerated_times = regenerated_times + 1,
                    if_picked_manually = 0
                WHERE menu_id = %s AND meal_id = %s
            """
            menu_meals_model.run_query(update_query, (new_recipe[0]['id'], menu_id, db_meal_id))

    flash(f"Entire menu for draft #{menu_id} has been regenerated!", "success")
    return redirect(url_for('menu'))


@app.route('/submit-final-menu', methods=['POST'])  # Removed <int:meal_count>
@login_required
def submit_final_menu():
    # 1. Pull data from the form
    menu_id = request.form.get('menu_id')
    meal_count = int(request.form.get('meal_count', 0))
    
    # 2. Check if already submitted
    menu_data = menu_model.run_query("SELECT submitted_at FROM Menus WHERE id = %s", (menu_id,))
    if not menu_data:
        return redirect(url_for('menu'))
        
    submitted_at = menu_data[0]['submitted_at']

    if not submitted_at:
        # 3. Update each meal's final details (like time)
        for i in range(meal_count):
            m_id = request.form.get(f'meal_{i}_id')
            m_time = request.form.get(f'meal_time_{i}')
            
            # Use UPDATE because the row was already created in init_plan
            update_query = """
                UPDATE Menu_meals 
                SET meal_time = %s 
                WHERE menu_id = %s AND meal_id = %s
            """
            menu_meals_model.run_query(update_query, (m_time, menu_id, m_id))
            
        # 4. Finalize the menu timestamp
        menu_model.run_query(
            "UPDATE Menus SET submitted_at = %s WHERE id = %s", 
            (datetime.now(timezone.utc), menu_id)
        )
        
        session.pop('menu_draft', None)
        flash("Menu finalized and saved!", "success")

    # Fetch fresh data for the redirect/render
    all_meals = meal_model.select_all()
    return redirect(url_for('menu')) # Redirect to clear the confirmed menu from drafts

# TODO - FIX filtering
@app.route('/manual-search/<int(signed=True):meal_index>', defaults={'menu_id': 0}, methods=['GET', 'POST'])
@app.route('/manual-search/<int(signed=True):meal_index>/<int:menu_id>', methods=['GET', 'POST'])
@login_required
def manual_search(meal_index, menu_id):
    print(f"Accessing manual search for meal_index: {meal_index}, menu_id: {menu_id}")
    

    favorite_ids = fetch_favorites(current_user.id, return_ids_only=True)

    search_query = request.args.get('search', '')
    category_id = request.args.get('category')
    params = []
    query = "SELECT * FROM Recipes"
    # Initialize base query
    if meal_index == -1:
        # General "Explore" mode: show all recipes
        query += " WHERE 1=1"
        
    else:
        # Specific meal selection mode
        if meal_index >= 6:
            return redirect(url_for('menu'))
        
        meal_type_id = meals_from_db[meal_index]['id']  # Get meal_id from the meals list based on index
        col = match_meal_to_recipe(meal_type_id, recipe_model.columns)
        query += f" WHERE {col} = 1"


    # Apply filters
    if search_query:
        query += " AND name LIKE %s"
        params.append(f"%{search_query}%")
    
    if category_id:
        query += " AND category_id = %s"
        params.append(category_id)
        
    recipes = recipe_model.run_query(query, tuple(params))
    categories = recipe_categories_model.select_all()
    
    return render_template('manual_search.html', 
                           recipes=recipes, 
                           categories=categories, 
                           meal_index=meal_index,
                           search_query=search_query,
                           favorite_ids=favorite_ids,
                           menu_id=menu_id)

@app.route('/select-recipe/<int:meal_index>/<int:recipe_id>/<int:menu_id>', methods=['POST'])
@login_required
def select_recipe(meal_index, recipe_id, menu_id):
    print(f"Selecting recipe {recipe_id} for meal_index {meal_index} in menu_id {menu_id}")
    draft_menu = menu_meals_model.run_query("SELECT * FROM Menu_meals WHERE menu_id = %s AND meal_id = %s ORDER BY meal_id ASC", (menu_id, meal_index + 1))
    if draft_menu:
        draft_menu = draft_menu[0]  # Get the single meal entry for this meal_index
        # Fetch the full recipe details
        recipe = recipe_model.run_query("SELECT * FROM Recipes WHERE id = %s", (recipe_id,))[0]
        
        # Update the specific meal in the draft
        draft_menu['recipe_id'] = recipe['id']
        draft_menu['recipe_name'] = recipe['name']
        draft_menu['if_picked_manually'] = 1
        
        # Update the database with the new recipe selection
        update_query = """
            UPDATE Menu_meals 
            SET recipe_id = %s, if_picked_manually = 1
            WHERE menu_id = %s AND meal_id = %s
        """
        menu_meals_model.run_query(update_query, (recipe_id, menu_id, draft_menu['meal_id']))

    return redirect(url_for('menu'))


@app.route('/recipe/<int:recipe_id>/<int:menu_id>', methods=['GET', 'POST'])
@login_required
def recipe_details(recipe_id, menu_id):
    favorite_ids = fetch_favorites(current_user.id, return_ids_only=True)
    recipe = recipe_model.run_query("SELECT * FROM Recipes WHERE id = %s", (recipe_id,))[0]
    

    query = """
        SELECT i.name as ingredient_name, ri.measure, u.name as unit_name, ri.prep_notes 
        FROM Recipes_ingredients ri 
        JOIN Ingredients i ON ri.ingredient_id = i.id 
        JOIN Units u ON ri.unit_id = u.id
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
                           favorite_ids=favorite_ids,
                           menu_id=menu_id)


@app.route('/api/check-ingredient', methods=['GET'])
def check_ingredient():
    name = request.args.get('name', '').strip().lower()
    if not name:
        return jsonify({'exists': True}) # Don't show button for empty strings
    
    # Check your Ingredients table
    result = recipe_model.run_query("SELECT id FROM Ingredients WHERE LOWER(name) = %s", (name,))
    
    return jsonify({'exists': len(result) > 0})


@app.route('/api/add-ingredient', methods=['POST'])
@login_required
def api_add_ingredient():
    data = request.get_json()
    name = data.get('name', '').strip().title()
    density = data.get('density')
    description = data.get('description', '')
    category_ids = data.get('category_ids', [])
    
    if not name or not category_ids or not density:
        return jsonify({'error': 'Missing data'}), 400
    
    source_id = source_model.run_query("SELECT id FROM Data_sources WHERE name = %s", ('User_submitted',))[0]['id']

    try:
        # Check if exists first
        exists = recipe_model.run_query("SELECT id FROM Ingredients WHERE name = %s", (name,))
        if exists:
            return jsonify({'error': 'Already exists'}), 409

        # Insert new ingredient
        new_ing_id=recipe_model.run_query(
            "INSERT INTO Ingredients (name, source_id, description, density) VALUES (%s, %s, %s, %s)",
            (name, source_id, description, density)
        )
        for cat_id in category_ids:
            recipe_model.run_query(
                "INSERT INTO Ingredient_categories_ingredients (ingredient_id, category_id) VALUES (%s, %s)",
                (new_ing_id, cat_id)
            )
        return jsonify({'success': True}), 201
    except Exception as e:
        print(f"DB Error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/add-recipe', methods=['GET', 'POST'])
@login_required
def add_recipe():
    if request.method == 'POST':
        try:
            fetch_recipe_form_and_update_db(operation_type='INSERT')
            flash('Recipe added successfully!', 'success')
            return redirect(url_for('manual_search', meal_index=-1))
        except Exception as e:
            print(f"Error adding recipe: {e}")
            flash('An error occurred while adding the recipe. Please try again.', 'error')
            return redirect(url_for('add_recipe'))

    # GET logic
    categories = recipe_model.run_query("SELECT * FROM Recipe_categories")
    ing_categories = recipe_model.run_query("SELECT * FROM Ingredient_categories WHERE name != 'Household & Cleaning'")
    meals = recipe_model.run_query("SELECT * FROM Meals")
    countries = recipe_model.run_query("SELECT * FROM Countries")
    # Fetch all ingredients to populate the datalist
    all_ingredients = recipe_model.run_query("SELECT name FROM Ingredients ORDER BY name ASC")
    units = recipe_model.run_query("SELECT id, name FROM Units")

    return render_template('add_recipe.html', 
                           categories=categories, 
                           ing_categories=ing_categories,
                           meals=meals,
                           countries=countries,
                           all_ingredients=all_ingredients,
                           units=units)


@app.route('/edit-recipe/<int:recipe_id>', methods=['GET'])
@login_required
def edit_recipe(recipe_id):
    recipe = recipe_model.select_by_id(recipe_id)
    meals_db = meal_model.select_all()
    active_columns = [col.lower() for col, value in recipe.items() if value == 1]

    for meal_ in meals_db:
        # 1. Get the name and strip the 's' if it exists for a looser match
        name = meal_.get('name', '').lower().strip()
        is_match = False
        for col in active_columns:
            norm_col = col.replace('if_', '').replace('_', ' ');
            print(f"Comparing meal name '{name}' with column '{norm_col}'")
            # 2. Check if the meal name is in the column OR the column name is in the meal name
            if name in norm_col or norm_col in name:
                is_match = True
                break
        meal_['checked'] = is_match
    for meal in meals_db:
        print(f"Meal: {meal['name']}, Checked: {meal['checked']}")

    ingredients = recipe_ingredients_model.run_query("""
        SELECT ri.*, i.name as name
        FROM Recipes_ingredients ri
        JOIN Ingredients i ON ri.ingredient_id = i.id
        WHERE ri.recipe_id = %s
        ORDER BY ri.order_index ASC
    """, (recipe_id,))

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

    prep_split = recipe['prep_time'].split(':')
    recipe['prep_hrs'] = prep_split[0]
    recipe['prep_mins'] = prep_split[1]

    cook_split = recipe['cooking_time'].split(':')
    recipe['cook_hrs'] = cook_split[0]
    recipe['cook_mins'] = cook_split[1]

    all_ingredients = recipe_model.run_query("SELECT name FROM Ingredients ORDER BY name ASC")
    ing_categories = recipe_model.run_query("SELECT * FROM Ingredient_categories WHERE name != 'Household & Cleaning'")
    categories = recipe_model.run_query("SELECT * FROM Recipe_categories")
    countries = recipe_model.run_query("SELECT * FROM Countries")
    units = recipe_model.run_query("SELECT id, name FROM Units")
    response = make_response(render_template('edit_recipe.html', 
                           recipe=recipe, 
                           ingredients=ingredients, 
                           categories=categories, 
                           meals=meals_db, 
                           countries=countries,
                           units=units,
                           all_ingredients=all_ingredients,
                           ing_categories=ing_categories))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


@app.route('/save-changes/<int:recipe_id>', methods=['POST'])
@login_required
def save_changes(recipe_id):
    # Get form data and update the recipe in the database
    try:
        fetch_recipe_form_and_update_db(operation_type='UPDATE', recipe_id=recipe_id)
        flash('Recipe updated successfully!', 'success')
        return redirect(url_for('recipe_details', recipe_id=recipe_id))
    except Exception as e:
        print(f"Error updating recipe: {e}")
        flash('An error occurred while updating the recipe. Please try again.', 'error')
        return redirect(url_for('edit_recipe', recipe_id=recipe_id))


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
    history_query = """SELECT id, date(created_at) as `created at`, menu_date as `menu date` FROM Menus WHERE user_id = %s ORDER BY id DESC;"""

    history = recipe_model.run_query(history_query, (current_user.id,))
    meals = recipe_model.run_query(meals_query, (current_user.id,))
    print(history)

    for entry in history:
        entry['date'] = entry['menu date'].strftime("%B %d, %Y")
        entry['meals'] = [meal for meal in meals if meal['menu_id'] == entry['id']]
    print("Meals associated with history entries:")
    print(history)

    return render_template('history.html', history=history)


@app.route('/shopping-list/<int:menu_id>', methods=['GET', 'POST'])
@login_required
def shopping_list(menu_id):
    # 1. Handle Timezone & Persistence
    user_tz = request.form.get('user_timezone', users_model.select_by_id(current_user.id)['timezone'] or 'UTC')
    utc_start, utc_end = local_time_to_utc_range(user_tz)
    print(f"Checking for shopping list with menu_id {menu_id} between {utc_start} and {utc_end} (UTC) for user timezone {user_tz}")

    # Check if list exists for today
    check = shopping_list_model.run_query("SELECT id FROM Shopping_list WHERE menu_id = %s AND created_at BETWEEN %s AND %s LIMIT 1", (menu_id, utc_start, utc_end))
    
    if check:
        shopping_list_id = check[0]['id']
    else:
        # Initial Creation: Snapshot ingredients from Menu into the Shopping List Table
        shopping_list_id = shopping_list_model.run_query("INSERT INTO Shopping_list (menu_id) VALUES (%s)", (menu_id,))
        snapshot_sql = """
                        INSERT INTO Shopping_list_ingredients (shop_list_id, ingredient_id, measure, units, category_id)
                        SELECT %s, ri.ingredient_id, SUM(ri.measure), u.name, icm.category_id
                        FROM Recipes_ingredients ri
                        JOIN Menu_meals mm ON ri.recipe_id = mm.recipe_id
                        JOIN Ingredients i ON i.id = ri.ingredient_id
                        JOIN Units u ON ri.unit_id = u.id
                        LEFT JOIN Ingredients_categories_map icm ON i.id = icm.ingredient_id
                        WHERE mm.menu_id = %s
                        GROUP BY ri.ingredient_id, u.name, icm.category_id
                    """
        shopping_list_items_model.run_query(snapshot_sql, (shopping_list_id, menu_id))

    # 2. Handle Saving (POST)
    if request.method == 'POST':
        names = request.form.getlist('item_names[]')
        measures = request.form.getlist('item_measures[]')
        units = request.form.getlist('item_units[]')
        checks = request.form.getlist('item_checked[]')
        cat_ids = request.form.getlist('item_category_ids[]') 

        shopping_list_items_model.run_query("DELETE FROM Shopping_list_ingredients WHERE shop_list_id = %s", (shopping_list_id,))

        for i in range(len(names)):
            name = names[i].strip()
            if not name: continue
            
            # Check if ingredient exists in DB
            ing = recipe_model.run_query("SELECT id FROM Ingredients WHERE LOWER(name) = LOWER(%s)", (name,))
            
            if ing:
                # Existing Ingredient: use its ID (Schema requires ingredient_id NOT NULL usually, 
                # but if your schema allows NULL for custom items, update your SQL accordingly)
                shopping_list_items_model.run_query(
                    """INSERT INTO Shopping_list_ingredients 
                       (shop_list_id, ingredient_id, measure, units, if_checked, category_id) 
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (shopping_list_id, ing[0]['id'], measures[i], units[i], checks[i], cat_ids[i])
                )
            else:
                # Custom Item: Set ingredient_id to a dummy value (like 0) or update schema to allow NULL
                # Since your schema says NOT NULL for ingredient_id, ensure you handle that or ALTER TABLE to allow NULL
                shopping_list_items_model.run_query(
                    """INSERT INTO Shopping_list_ingredients 
                       (shop_list_id, ingredient_id, item_name, measure, units, if_checked, category_id) 
                       VALUES (%s, 0, %s, %s, %s, %s, %s)""",
                    (shopping_list_id, name, measures[i], units[i], checks[i], cat_ids[i])
                )
        return redirect(url_for('shopping_list', menu_id=menu_id))

    # --- GET Logic ---
    # 1. Fetch Items for the List
    db_query = """
        SELECT 
            COALESCE(i.name, sli.item_name) as name, 
            sli.measure, sli.units, sli.if_checked,
            ic.name as category,
            sli.category_id
        FROM Shopping_list_ingredients sli
        LEFT JOIN Ingredients i ON sli.ingredient_id = i.id
        LEFT JOIN Ingredient_categories ic ON sli.category_id = ic.id
        WHERE sli.shop_list_id = %s
        ORDER BY category, name
    """
    items = shopping_list_items_model.run_query(db_query, (shopping_list_id,))
    
    # 2. Fetch Data for Selects and Datalists
    # Full list of categories (ID and Name)
    all_cats = recipe_model.run_query("SELECT id, name FROM Ingredient_categories ORDER BY name")
    
    # Full list of ingredients for the datalist search
    all_ingredients = recipe_model.run_query("SELECT name FROM Ingredients ORDER BY name ASC")

    # Map for Javascript Auto-Select (Name -> Category ID)
    raw_ing_data = recipe_model.run_query("""
        SELECT LOWER(i.name) as name, icm.category_id 
        FROM Ingredients i
        JOIN Ingredients_categories_map icm ON i.id = icm.ingredient_id
    """)
    ing_category_map = {row['name']: row['category_id'] for row in raw_ing_data}

    return render_template('shopping_list.html', 
                           grouped_items=group_by_category(items), 
                           menu_id=menu_id, 
                           all_ingredients=all_ingredients,
                           all_cats_full=all_cats,
                           ing_map=ing_category_map)


@app.route('/signin', methods=['GET', 'POST'])
def signin():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user_timezone = request.form.get('user_timezone', 'UTC')
        

        user_data = recipe_model.run_query("SELECT * FROM Users WHERE email = %s", (email,))
        
        if user_data and check_password_hash(user_data[0]['password_hash'], password):
            
            user_obj = User(user_data[0])
            login_user(user_obj)
            users_model.update(current_user.id, {'timezone': user_timezone})
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

scheduler = BackgroundScheduler()
scheduler.add_job(func=send_meal_reminders, trigger="interval", minutes=5)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

if __name__ == '__main__':
    app.run(debug=True)
    

    scheduler = BackgroundScheduler()
    scheduler.add_job(func=send_meal_reminders, trigger="interval", minutes=5)
    scheduler.start()

    # Shut down the scheduler when the app exits
    atexit.register(lambda: scheduler.shutdown())