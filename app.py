from tracemalloc import start
from urllib.parse import quote
from database.models import BaseModel

from flask import Flask, abort, flash, jsonify, render_template, redirect, url_for, request, session
from flask_mail import Mail, Message
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask import make_response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from apscheduler.schedulers.background import BackgroundScheduler
from datetime import date, datetime, timedelta, time, timezone
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from zoneinfo import ZoneInfo

from io import BytesIO
from flask import send_file
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

import atexit
import random
import re
import os
import secrets


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
units_model = BaseModel('Units')


app = Flask(__name__)

app.config['SECRET_KEY'] = os.getenv('app_key')

app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)

app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT'))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS').lower() == 'true'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')

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
    u = users_model.run_query("SELECT * FROM Users WHERE id = %s", (user_id,))
    if u:
        return User(u[0])
    return None


app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


def consolidate_by_ingredient(rows, ingredient_densities=None):
    """
    rows: List of dicts from SQL (ingredient_id, measure, units, category_id)
    ingredient_densities: Optional dict mapping ingredient_id to a specific density
    """

    unit_rows = units_model.run_query("SELECT name, category, factor FROM Units")
    unit_metadata = {row['name'].lower().strip(): {'category': row['category'], 'factor': float(row['factor'])} for row in unit_rows}
    
    consolidated = {}
    ingredient_densities = ingredient_densities or {}

    for row in rows:
        ing_id = row['ingredient_id']
        measure = float(row['measure'])
        unit_name = row['units'].lower().strip()
        cat_id = row['category_id']
        
        if ing_id not in consolidated:
            consolidated[ing_id] = {
                'total_base_mass': 0.0,    # Grams
                'total_base_volume': 0.0,  # Milliliters
                'counts': {},              # 'pcs', 'clove', etc.
                'category_id': cat_id      # Preserve category for UI grouping
            }

        # Look up unit details from units.csv
        u_info = unit_metadata.get(unit_name)
        if not u_info:
            # If unit is unknown, treat as a Count to avoid losing data
            consolidated[ing_id]['counts'][unit_name] = consolidated[ing_id]['counts'].get(unit_name, 0) + measure
            continue

        factor = float(u_info['factor'])
        category = u_info['category']

        if category == 'Mass':
            consolidated[ing_id]['total_base_mass'] += measure * factor
        elif category == 'Volume':
            consolidated[ing_id]['total_base_volume'] += measure * factor
        elif category == 'Count':
            consolidated[ing_id]['counts'][unit_name] = consolidated[ing_id]['counts'].get(unit_name, 0) + measure
        else:
            # Handle "to serve" or other subjective units
            consolidated[ing_id]['counts'][unit_name] = "As required"

    # Final conversion step
    final_shopping_list = []
    for ing_id, data in consolidated.items():
        # Get density: uses specific DB density, otherwise defaults to 1.0
        # Defaulting to 1.0 for volume-to-mass is a safe overestimate for dry goods.
        density = float(ingredient_densities.get(ing_id, 1.0))
        
        # Merge Volume into Mass: mass = volume * density
        total_grams = data['total_base_mass'] + (data['total_base_volume'] * density)

        if total_grams > 0:
            # Choose readable unit: kg if > 1000g, otherwise g
            if total_grams >= 1000:
                final_shopping_list.append({
                    'ingredient_id': ing_id,
                    'measure': round(total_grams / 1000, 2),
                    'units': 'kg',
                    'category_id': data['category_id']
                })
            else:
                final_shopping_list.append({
                    'ingredient_id': ing_id,
                    'measure': round(total_grams, 1),
                    'units': 'g',
                    'category_id': data['category_id']
                })

        # Add separate entries for items like "2 pcs" or "3 cloves"
        for unit, qty in data['counts'].items():
            final_shopping_list.append({
                'ingredient_id': ing_id,
                'measure': qty,
                'units': unit,
                'category_id': data['category_id']
            })

    return final_shopping_list


def generate_reset_token(email):
    # Use your app's secret key to sign the token
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    # This creates a string that contains the email
    return serializer.dumps(email, salt='password-reset-salt')


def verify_reset_token(token, expiration=3600):
    # 1. Initialize the serializer with your app's SECRET_KEY
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

    try:
        # 2. Attempt to "unlock" the token
        # max_age is the time in seconds (3600 = 1 hour)
        email = serializer.loads(
            token,
            salt='password-reset-salt',
            max_age=expiration
        )
    except SignatureExpired:
        # Token is valid but too old
        flash('Error resetting password. Please request a new link for password reset.', 'error')
        return None
    except BadSignature:
        # Token has been tampered with or is just gibberish
        flash('Error resetting password. Please request a new link for password reset.', 'error')
        return None

    # 3. If everything is perfect, it returns the email string
    return email


def is_password_strong(password):
    """Enforce: 8+ chars, 1 upper, 1 lower, 1 digit, 1 special."""
    if len(password) < 8: return False
    if not re.search(r"[a-z]", password): return False
    if not re.search(r"[A-Z]", password): return False
    if not re.search(r"\d", password): return False
    if not re.search(r"[@$!%*?&]", password): return False
    return True


def send_welcome_email(user_email, user_name):
    try:
        msg = Message(
            subject="Welcome to Menu Generator! 🍳",
            recipients=[user_email],
            sender=app.config['MAIL_USERNAME'],
            # This is the fallback for email clients that don't support HTML
            body=f"Welcome, {user_name}! We're excited to have you. Your account is now active."
        )

        # This makes the email look like a real app notification
        msg.html = f"""
            <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #ddd; border-radius: 10px; padding: 20px;">
                <h2 style="color: #ff66b2; text-align: center;">Welcome to Menu Generator!</h2>
                <p>Hi {user_name},</p>
                <p>Thanks for joining us! You can now start creating recipes, organizing your shopping lists, and planning your meals like a pro.</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="#" style="background-color: #ff66b2; color: white; padding: 12px 25px; text-decoration: none; border-radius: 25px; font-weight: bold;">Get Started</a>
                </div>
                <p style="font-size: 0.8em; color: #777;">If you didn't sign up for this account, you can safely ignore this email.</p>
            </div>
        """
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


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

@app.route('/get_calendar_link/<int:meal_id>/<int:menu_id>')
def get_calendar_link(meal_id, menu_id):
    try:
        query = """SELECT r.name as recipe_name, mm.menu_id, mm.meal_time, m.menu_date
                 FROM Menu_meals mm
                 JOIN Recipes r ON mm.recipe_id = r.id
                 JOIN Menus m ON mm.menu_id = m.id
                 WHERE mm.meal_id = %s AND mm.menu_id = %s"""
        result = recipe_model.run_query(query, (meal_id, menu_id))
        if not result:
            return redirect(url_for('menu'))

        user_tz  = users_model.select_by_id(current_user.id)['timezone'] or 'UTC'
        user_tz = ZoneInfo(user_tz)
        result = result[0] or None
        if not result:
            return redirect(url_for('menu'))
        meal = result
        menu_date = meal['menu_date']
        raw_time = meal['meal_time']

        naive_start = datetime.combine(menu_date, (datetime.min + raw_time).time())

        # 3. LOCALIZE it (Tell Python: "This 18:00 is Kyiv time")
        local_start = datetime.now(user_tz).replace(year=naive_start.year, month=naive_start.month, day=naive_start.day, hour=naive_start.hour, minute=naive_start.minute, second=0, microsecond=0)

        # 4. CONVERT to UTC (This changes 18:00 Kyiv to 16:00 UTC)
        utc_start = local_start.astimezone(timezone.utc)

        # 5. Add your duration to the UTC time
        utc_end = utc_start + timedelta(minutes=30)

        # 6. Format for Google (The 'Z' now correctly refers to 16:00 UTC)
        start_fmt = utc_start.strftime('%Y%m%dT%H%M%SZ')
        end_fmt = utc_end.strftime('%Y%m%dT%H%M%SZ')

        # 4. Build the URL
        title = quote(f"🍽️ Meal: {meal['recipe_name']}")
        calendar_url = (
            f"https://www.google.com/calendar/render?action=TEMPLATE"
            f"&text={title}"
            f"&dates={start_fmt}/{end_fmt}"
            f"&details=Time+to+eat!"
        )

        return redirect(calendar_url)

    except Exception as e:
        print(f"Calendar Error: {e}")
        return redirect(url_for('menu'))


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


def fetch_recipe_form_and_update_db(operation_type:str, recipe_id=None, source_id=None, return_new_recipe_id=False)->None:
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
                prep_time=%s, cooking_time=%s, instructions=%s, area=%s, thumb=%s, source_id=%s
            WHERE id=%s
        """

        recipe_model.run_query(recipe_query, (name, country_id, cat_id, n_portions,
                               prep_time, cooking_time, instructions, country_name,
                               final_thumb_path, source_id, new_recipe_id))

        # FIX 2: Reset all meal flags to 0 before applying new ones
        meal_cols = [c for c in recipe_model.columns if c.startswith('if_')]
        for col in meal_cols:
            recipe_model.run_query(f"UPDATE Recipes SET {col} = 0 WHERE id = %s", (new_recipe_id,))

    elif operation_type == 'INSERT':
        recipe_query = f"""
                INSERT INTO Recipes (name, country_id, category_id, n_portions, prep_time, cooking_time, instructions, area, thumb, rating, created_by_user_id, source_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 10, %s, %s)
            """
        new_recipe_id = recipe_model.run_query(recipe_query, (name, country_id, cat_id, n_portions, prep_time, cooking_time, instructions, country_name, final_thumb_path, current_user.id, source_id))

        favorites_recipes_model.insert({
            'user_id': current_user.id,
            'recipe_id': new_recipe_id
            })
        print(f"Inserted new recipe with ID: {new_recipe_id} and added to favorites for user {current_user.id}")

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
                INSERT INTO Recipes_ingredients (recipe_id, ingredient_id, measure, unit_id, prep_notes, order_index, source_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (new_recipe_id, ing_id, ing_measures[i], ing_units[i], ing_prep_notes[i], i, source_id))
    if return_new_recipe_id:
        return new_recipe_id

def clear_drafts_at_midnight():
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=clean_menu_draft, trigger='cron', hour=0, minute=0)
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())


def local_time_to_utc_range(user_timezone= None, return_now=False)->tuple:
    '''This function takes a user's timezone as input and returns the corresponding UTC start and end datetimes for the current local day in that timezone.
    user_timezone: The timezone string (e.g., 'Europe/Stockholm') for which to calculate the local day range.
    If None, it will fetch the timezone from the database based on the current user.
    return_now: If True, also returns the current local datetime in the user's timezone for additional context.
    Returns a tuple containing the UTC start datetime, UTC end datetime, and optionally the current local datetime if return_now is True.'''
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
        draft_recipe_ids = [meal['recipe_id'] for meal in draft_menu_meals] 
        recipe = generate_meal(meal_id)[0]
  
        # TODO FIX LOOP. AVOID LIMIT
        attempts = 0
        while recipe['id'] in draft_recipe_ids and attempts < 5:
            recipe = generate_meal(meal_id)[0]
            attempts += 1

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
    print(f"Fetched {len(results)} favorite recipes for user_id {user_id}.")
    if return_ids_only:
        return [recipe['id'] for recipe in results]
    return results


meals_from_db = meal_model.select_all()


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
    print(f"Selected meal types: {selected_names}")
    user_time_zone = request.form.get('user_timezone', 'UTC')
    start_date = request.form.get('start_date')
    duration_days = request.form.get('duration_days')
    print(type(duration_days))
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
    elif current_date == datetime.strptime(start_date, '%Y-%m-%d').date() and int(duration_days) != 1:
        error_message="Start date cannot be today, please use the 'Regenerate' button for today's meals or generate a menu only for today!"
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

@app.route('/regenerate_meal/<int:meal_id>', methods=['POST'])
@login_required
def regenerate_meal(meal_id):
    menu_id = request.form.get('menu_id')

    if not menu_id:
        return redirect(url_for('menu'))

    # 1. Fetch current meal to get its existing time
    query = "SELECT meal_time, meal_id FROM Menu_meals WHERE menu_id = %s AND meal_id = %s"
    current_meal_data = menu_meals_model.run_query(query, (menu_id, meal_id))

    if not current_meal_data:
        flash("Meal not found in drafts.", "error")
        return redirect(url_for('menu'))

    existing_time = current_meal_data[0]['meal_time']

    # 2. Generate the new recipe
    new_recipe = generate_meal(meal_id)

    if new_recipe and len(new_recipe) > 0:
        try:
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
                existing_time,
                menu_id,
                meal_id
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


@app.route('/delete-menu/<int:menu_id>', methods=['GET', 'POST'])
@login_required
def delete_menu(menu_id):
    menu_meals_model.run_query("DELETE FROM Menu_meals WHERE menu_id = %s", (menu_id,))
    shopping_list_items_model.run_query("DELETE FROM Shopping_list_ingredients WHERE shop_list_id IN (SELECT id FROM Shopping_list WHERE menu_id IN (SELECT id FROM Menus WHERE user_id = %s AND submitted_at IS NULL))", (current_user.id,))
    shopping_list_model.run_query("DELETE FROM Shopping_list WHERE menu_id IN (SELECT id FROM Menus WHERE user_id = %s AND submitted_at IS NULL)", (current_user.id,))
    menu_model.run_query("DELETE FROM Menus WHERE id = %s", (menu_id,))
    return redirect(url_for('menu'))

@app.route('/delete-all_drafts', methods=['GET', 'POST'])
@login_required
def delete_all_drafts():
    current_user_id = current_user.id

    menu_meals_model.run_query("DELETE FROM Menu_meals WHERE menu_id IN (SELECT id FROM Menus WHERE user_id = %s AND submitted_at IS NULL)", (current_user_id,))
    shopping_list_items_model.run_query("DELETE FROM Shopping_list_ingredients WHERE shop_list_id IN (SELECT id FROM Shopping_list WHERE menu_id IN (SELECT id FROM Menus WHERE user_id = %s AND submitted_at IS NULL))", (current_user_id,))
    shopping_list_model.run_query("DELETE FROM Shopping_list WHERE menu_id IN (SELECT id FROM Menus WHERE user_id = %s AND submitted_at IS NULL)", (current_user_id,))
    menu_model.run_query("DELETE FROM Menus WHERE user_id = %s AND submitted_at IS NULL", (current_user_id,))

    flash("All draft menus have been deleted.", "success")
    return redirect(url_for('menu'))


@app.route('/manual-search', methods=['GET', 'POST'])
@app.route('/manual-search/<int(signed=True):meal_id>', defaults={'menu_id': 0}, methods=['GET', 'POST'])
@app.route('/manual-search/<int(signed=True):meal_id>/<int:menu_id>', methods=['GET', 'POST'])
def manual_search(meal_id=None, menu_id=None):
    if meal_id and menu_id:
        session['manual_search'] = {'meal_id': meal_id, 'menu_id': menu_id}

    favs = request.args.get('show_favorites')
    favorite_ids = []
    if favs == '1':
        if not current_user.is_authenticated:
            flash("Log in to see your favorite recipes.", "info")
            return redirect(url_for('manual_search'))
        else:
            favorite_ids = fetch_favorites(current_user.id, return_ids_only=True)

    search_query = request.args.get('search', '')
    category_id = request.args.get('category')
    params = []
    query = "SELECT * FROM Recipes WHERE"

    valid_meal_ids = {m['id'] for m in meals_from_db}
    if meal_id in valid_meal_ids:
        col = match_meal_to_recipe(meal_id, recipe_model.columns)
        query += f" {col} = 1"
    else:
        query += " 1=1"

    if search_query:
        query += " AND name LIKE %s"
        params.append(f"%{search_query}%")

    if category_id:
        query += " AND category_id = %s"
        params.append(category_id)

    if favorite_ids:
        placeholders = ', '.join(['%s'] * len(favorite_ids))
        query += f" AND id IN ({placeholders})"
        params.extend(favorite_ids)

    print(f"DEBUG QUERY: {query} with PARAMS: {params}")
    recipes = recipe_model.run_query(query, tuple(params))
    categories = recipe_categories_model.select_all()

    return render_template('manual_search.html',
                           recipes=recipes,
                           categories=categories,
                           meal_id=meal_id,
                           search_query=search_query,
                           favorite_ids=favorite_ids,
                           menu_id=menu_id,
                           user_id=current_user.id if current_user.is_authenticated else None)

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

@app.route('/recipe/<int:recipe_id>', methods=['GET', 'POST'])
@app.route('/recipe/<int:recipe_id>/<int:menu_id>', methods=['GET', 'POST'])
@login_required
def recipe_details(recipe_id, menu_id=None):
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
                "INSERT INTO Categories_ingredients (ingredient_id, category_id) VALUES (%s, %s)",
                (new_ing_id, cat_id)
            )
        return jsonify({'success': True}), 201
    except Exception as e:
        print(f"DB Error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/add-recipe', methods=['GET', 'POST'])
@login_required
def add_recipe(meals_from_db=meals_from_db):
    # 1. Get the context from session so we know which menu slot we are filling
    manual_search_data = session.get('manual_search')

    if request.method == 'POST':
        try:
            # This creates the recipe and returns the new ID
            recipe_id = fetch_recipe_form_and_update_db(operation_type='INSERT', return_new_recipe_id=True)
            flash('Recipe created and added to your menu!', 'success')

            if manual_search_data:
                meal_index = manual_search_data.get('meal_index')
                menu_id = manual_search_data.get('menu_id')

                # Get the actual meal_type_id (e.g., ID for 'Breakfast')
                meal_type_id = meals_from_db[meal_index]['id']

                # 2. UPDATE THE MENU DIRECTLY
                # We update the specific menu and meal slot with the new recipe_id
                query = """
                    UPDATE Menu_meals
                    SET recipe_id = %s, if_picked_manually = 1
                    WHERE menu_id = %s AND meal_id = %s
                """
                menu_meals_model.run_query(query, (recipe_id, menu_id, meal_type_id))

                # 3. GO BACK TO MENU
                return redirect(url_for('menu'))

            # Fallback if no session data found
            return redirect(url_for('manual_search'))

        except Exception as e:
            print(f"Error: {e}")
            flash('Failed to add recipe.', 'error')
            return redirect(url_for('add_recipe'))

    all_ingredients = recipe_model.run_query("SELECT name FROM Ingredients ORDER BY name ASC")
    ing_categories = recipe_model.run_query("SELECT * FROM Ingredient_categories WHERE name != 'Household & Cleaning'")
    categories = recipe_model.run_query("SELECT * FROM Recipe_categories")
    countries = recipe_model.run_query("SELECT * FROM Countries")
    units = recipe_model.run_query("SELECT id, name FROM Units")
    user_source_id = source_model.run_query("SELECT id FROM Data_sources WHERE name = %s", ('User_submitted',))[0]['id']
    meals_db = meal_model.select_all()
    none_country_id = recipe_model.run_query("SELECT id FROM Countries WHERE name = 'None'")[0]['id']

    return render_template('add_recipe.html',
                           categories=categories,
                           meals=meals_db,
                           countries=countries,
                           units=units,
                           all_ingredients=all_ingredients,
                           ing_categories=ing_categories,
                           user_source_id=user_source_id,
                           none_country_id=none_country_id)


@app.route('/update-menu-item', methods=['POST'])
@login_required
def update_menu_item():
    # TODO fix meal_id/meal_index bug.
    recipe_id = request.form.get('recipe_id')
    menu_id = request.form.get('menu_id')
    meal_index = int(request.form.get('meal_id'))

    meal_type_id = meals_from_db[meal_index]['id']

    query = "UPDATE Menu_meals SET recipe_id = %s, if_picked_manually = 1 WHERE menu_id = %s AND meal_id = %s"
    menu_meals_model.run_query(query, (recipe_id, menu_id, meal_type_id))

    flash("Menu updated!", "success")
    return redirect(url_for('menu'))


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
    user_source_id = source_model.run_query("SELECT id FROM Data_sources WHERE name = %s", ('User_submitted',))[0]['id']

    response = make_response(render_template('edit_recipe.html',
                           recipe=recipe,
                           ingredients=ingredients,
                           categories=categories,
                           meals=meals_db,
                           countries=countries,
                           units=units,
                           all_ingredients=all_ingredients,
                           ing_categories=ing_categories,
                           user_source_id=user_source_id))
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


@app.route('/delete-recipe/<int:recipe_id>', methods=['POST'])
@login_required
def delete_recipe(recipe_id):
    try:
        from_favorites = request.form.get('from_favorites') == '1'
        print(F'DEBUG form: {request.form.get("from_favorites")}, from_favorites: {from_favorites}')
        # First, remove from favorites if it exists there to avoid orphaned records
        # TODO - This should ideally be handled with ON DELETE CASCADE in the database to avoid this manual step and ensure data integrity
        if_favorite = favorites_recipes_model.run_query("SELECT id FROM User_favorite_recipes WHERE recipe_id = %s AND user_id = %s", (recipe_id, current_user.id))
        if if_favorite:
            favorites_recipes_model.run_query("DELETE FROM User_favorite_recipes WHERE recipe_id = %s AND user_id = %s", (recipe_id, current_user.id))
        recipe_ingredients_model.run_query("DELETE FROM Recipes_ingredients WHERE recipe_id = %s", (recipe_id,))
        recipe_model.run_query("DELETE FROM Recipes WHERE id = %s AND created_by_user_id = %s", (recipe_id, current_user.id))
        flash('Recipe deleted successfully!', 'success')
        if from_favorites:
            return redirect(url_for('favorites'))

        return redirect(url_for('manual_search'))
    except Exception as e:
        print(f"Error deleting recipe: {e}")
        flash('An error occurred while deleting the recipe. Please try again.', 'error')
        if from_favorites:
            return redirect(url_for('favorites'))
        return redirect(url_for('manual_search'))


@app.route('/favorites')
@login_required
def favorites():
    favorites = fetch_favorites(current_user.id)
    print(f"Rendering favorites page with {len(favorites)} recipes for user_id {current_user.id}.")
    return render_template('favorites.html', favorites=favorites, menu_id=0)


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


@app.route('/history', methods=['GET', 'POST'])
@login_required
def history():
    start_date = request.form.get('start_date', '')
    end_date = request.form.get('end_date', '')
    print(f"Filtering history from {start_date} to {end_date} for user_id {current_user.id}")
    if start_date and end_date:
        history_query = """SELECT id, date(created_at) as `created at`, menu_date as `menu date` FROM Menus WHERE user_id = %s AND menu_date BETWEEN %s AND %s ORDER BY id DESC;"""
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
        WHERE m.user_id = %s AND m.menu_date BETWEEN %s AND %s
        ORDER BY m.created_at DESC, mm.meal_time ASC;
        """
        history = recipe_model.run_query(history_query, (current_user.id, start_date, end_date))
        meals = recipe_model.run_query(meals_query, (current_user.id, start_date, end_date))
    else:
        history_query = """SELECT id, date(created_at) as `created at`, menu_date as `menu date` FROM Menus WHERE user_id = %s ORDER BY id DESC;"""
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
        history = recipe_model.run_query(history_query, (current_user.id,))
        meals = recipe_model.run_query(meals_query, (current_user.id,))

    for entry in history:
        entry['date'] = entry['menu date'].strftime("%B %d, %Y")
        entry['meals'] = [meal for meal in meals if meal['menu_id'] == entry['id']]
    print("Meals associated with history entries:")
    print(history)

    return render_template('history.html', history=history)


@app.route('/shopping-list', methods=['GET', 'POST'])
@app.route('/shopping-lists/<int:shop_list_id>', methods=['GET', 'POST'])
@app.route('/shopping-list/<int:menu_id>', methods=['GET', 'POST'])
@login_required
def shopping_list(menu_id=None, shop_list_id=None):
    # 1. Handle Timezone & Persistence
    user_tz = request.form.get('user_timezone', users_model.select_by_id(current_user.id)['timezone'] or 'UTC')
    utc_start, utc_end, user_now = local_time_to_utc_range(user_tz, return_now=True)
    is_shared = request.args.get('is_shared', 'false').lower() == 'true'
    shopping_list_id = None

    if not shop_list_id:
        if menu_id:
            # 1. Check if list already exists for this menu today
            check = shopping_list_model.run_query(
                "SELECT id FROM Shopping_list WHERE menu_id = %s AND created_at BETWEEN %s AND %s LIMIT 1",
                (menu_id, utc_start, utc_end)
            )

            if check:
                # LIST EXISTS: Just grab the ID and stop. Do NOT snapshot again.
                shopping_list_id = check[0]['id']
            else:
                # NEW LIST: Create the header AND snapshot the ingredients ONCE.
                menu_date_row = menu_model.run_query("SELECT menu_date FROM Menus WHERE id = %s", (menu_id,))
                menu_date = menu_date_row[0]['menu_date']
                shopping_list_name = f"Shopping List for menu: {menu_date.strftime('%B %d, %Y')}"

                # Create the main list record
                shopping_list_id = shopping_list_model.run_query(
                    "INSERT INTO Shopping_list (name, user_id, menu_id, is_menu) VALUES (%s, %s, %s, %s)",
                    (shopping_list_name, current_user.id, menu_id, 1)
                )
                select_items_query = """
                    SELECT
                        %s as shop_list_id,
                        ri.ingredient_id,
                        SUM(ri.measure) as measure,
                        u.name as units,
                        icm.category_id
                    FROM Recipes_ingredients ri
                    JOIN Menu_meals mm ON ri.recipe_id = mm.recipe_id
                    JOIN Units u ON ri.unit_id = u.id
                    LEFT JOIN Ingredients_categories_map icm ON ri.ingredient_id = icm.ingredient_id
                    WHERE mm.menu_id = %s
                    GROUP BY ri.ingredient_id, u.name, icm.category_id"""

                select_items = recipe_model.run_query(select_items_query, (shopping_list_id, menu_id))
                final_shop_list = consolidate_by_ingredient(select_items)
                # RUN SNAPSHOT ONLY HERE (inside the 'else')
                snapshot_sql = """
                    INSERT INTO Shopping_list_ingredients (shop_list_id, ingredient_id, measure, units, category_id)
                VALUES (%s, %s, %s, %s, %s)
                """
                for item in final_shop_list:
                    shopping_list_items_model.run_query(snapshot_sql, (shopping_list_id, item['ingredient_id'], item['measure'], item['units'], item['category_id']))

        else:
            # Handle creating a completely empty list
            shopping_list_name = f"My Shopping List - {user_now.strftime('%B %d, %Y')}"
            shopping_list_id = shopping_list_model.run_query(
                "INSERT INTO Shopping_list (user_id, menu_id, name) VALUES (%s, NULL, %s)",
                (current_user.id, shopping_list_name)
            )

    else:
        shopping_list_id = shop_list_id

    # 2. Handle Saving (POST)
    if request.method == 'POST':
        names = request.form.getlist('item_names[]')
        measures = request.form.getlist('item_measures[]')
        units = request.form.getlist('item_units[]')
        prices = request.form.getlist('item_prices[]')

        checked_values = request.form.getlist('item_checked[]')
        checked_ints = [int(v) if v != '' else 0 for v in checked_values]

        cat_ids = request.form.getlist('item_category_ids[]')
        shop_list_name = request.form.get('shop_list_name', '').strip()

        if shop_list_name:
            shopping_list_model.run_query("UPDATE Shopping_list SET name = %s WHERE id = %s", (shop_list_name, shopping_list_id))

        shopping_list_items_model.run_query("DELETE FROM Shopping_list_ingredients WHERE shop_list_id = %s", (shopping_list_id,))

        for i in range(len(names)):
            name = names[i].strip().lower()
            unit = units[i].strip().lower()
            if not name: continue

            # Check if ingredient exists in DB
            ing = recipe_model.run_query("SELECT id FROM Ingredients WHERE LOWER(name) = LOWER(%s)", (name,))

            if ing:
                # Existing Ingredient: ingredient_id set, item_name left NULL (default)
                shopping_list_items_model.run_query(
                    """INSERT INTO Shopping_list_ingredients
                       (shop_list_id, ingredient_id, measure, units, price, if_checked, category_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (shopping_list_id, ing[0]['id'], measures[i], unit, prices[i], checked_ints[i], cat_ids[i])
                )
            else:
                # Custom Item: ingredient_id must be NULL to satisfy chk_ingredient_or_custom
                if not cat_ids[i] or cat_ids[i] == 'null':
                    cat_ids[i] = 0
                shopping_list_items_model.run_query(
                    """INSERT INTO Shopping_list_ingredients
                       (shop_list_id, ingredient_id, item_name, measure, units, price, if_checked, category_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (shopping_list_id, None, name, measures[i], unit, prices[i], checked_ints[i], cat_ids[i])
                )
        return redirect(url_for('shopping_list', shop_list_id=shopping_list_id, shop_list_name=shop_list_name))

    # --- GET Logic ---
    # 1. Fetch Items for the List
    db_query = """
        SELECT
            COALESCE(i.name, sli.item_name) as name,
            sli.measure, sli.units, sli.price, sli.if_checked,
            ic.name as category,
            sli.category_id
        FROM Shopping_list_ingredients sli
        LEFT JOIN Ingredients i ON sli.ingredient_id = i.id
        LEFT JOIN Ingredient_categories ic ON sli.category_id = ic.id
        WHERE sli.shop_list_id = %s
        ORDER BY category, name
    """
    items = shopping_list_items_model.run_query(db_query, (shopping_list_id,))
    shop_list_name = shopping_list_model.run_query("SELECT name FROM Shopping_list WHERE id = %s", (shopping_list_id,))[0]['name'] or "My Shopping List"

    # 2. Fetch Data for Selects and Datalists
    # Full list of categories (ID and Name)
    all_cats = recipe_model.run_query("SELECT id, name FROM Ingredient_categories ORDER BY name")

    all_units = recipe_model.run_query("SELECT name FROM Units ORDER BY name")

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
                           all_units=all_units,
                           ing_map=ing_category_map,
                           shop_list_id=shopping_list_id,
                           shop_list_name=shop_list_name,
                           is_shared=is_shared)

@app.route('/merge_menus_to_shopping_list', methods=['POST', 'GET'])
@login_required
def merge_menus_to_shopping_list():
    # Use getlist to pick up multiple checked boxes
    selected_ids = request.form.getlist('menu_ids')
    selected_ids = [int(id) for id in selected_ids]
    user_tz = request.form.get('user_timezone', users_model.select_by_id(current_user.id)['timezone'] or 'UTC')
    user_now = local_time_to_utc_range(user_tz, return_now=True)[2]

    date_range = []
    if not selected_ids:
        flash("Please select at least one menu.", "error")
        return redirect(url_for('manage_shopping_lists'))

    user_id = current_user.id
    if len(selected_ids) == 1:
        menu_date = menu_model.run_query("SELECT menu_date FROM Menus WHERE id = %s", (selected_ids[0],))[0]['menu_date']
        shopping_list_name =  f" Shopping List - {menu_date.strftime('%B %d, %Y')}"
    else:
        for id in [selected_ids[0], selected_ids[-1]]:
            date = menu_model.run_query("SELECT menu_date FROM Menus WHERE id = %s", (id,))
            date_range.append(date[0]['menu_date'] if date else user_now)
        shopping_list_name = f"Merged Shopping List - {date_range[0].strftime('%B %d')} to {date_range[-1].strftime('%B %d')}"
    shopping_list_id =shopping_list_model.insert({
        'user_id': user_id,
        'name': shopping_list_name,
        'menu_id': selected_ids[0] if len(selected_ids) == 1 else None
    })
    selected_ids_tuple = tuple(selected_ids)
    placeholders = ','.join(['%s'] * len(selected_ids_tuple))
    snapshot_sql = F"""
                    INSERT INTO Shopping_list_ingredients (shop_list_id, ingredient_id, measure, units, category_id)
                    SELECT
                        %s as shop_list_id,
                        ri.ingredient_id,
                        SUM(ri.measure) as measure,
                        u.name as units,
                        icm.category_id
                    FROM Recipes_ingredients ri
                    JOIN Menu_meals mm ON ri.recipe_id = mm.recipe_id
                    JOIN Units u ON ri.unit_id = u.id
                    LEFT JOIN Ingredients_categories_map icm ON ri.ingredient_id = icm.ingredient_id
                    WHERE mm.menu_id IN ({placeholders})
                    GROUP BY ri.ingredient_id, u.name, icm.category_id
                """
    params = tuple([shopping_list_id] + list(selected_ids_tuple))

    shopping_list_items_model.run_query(snapshot_sql, params)

    flash(f"Successfully merged {len(selected_ids)} menus into your shopping list!", "success")

    return redirect(url_for('shopping_list', shop_list_id=shopping_list_id))

@app.route('/shopping-list-delete/<int:shop_list_id>')
@login_required
def delete_shopping_list(shop_list_id):
    shopping_list_items_model.run_query("DELETE FROM Shopping_list_ingredients WHERE shop_list_id = %s", (shop_list_id,))
    shopping_list_model.run_query("DELETE FROM Shopping_list WHERE id = %s", (shop_list_id,))
    return redirect(url_for('manage_shopping_lists'))


@app.route('/manage-shopping-lists', methods=['GET', 'POST'])
@login_required
def manage_shopping_lists():
    user_tz = users_model.select_by_id(current_user.id)['timezone'] or 'UTC'
    user_now = local_time_to_utc_range(user_tz, return_now=True)[2]
    shopping_lists = shopping_list_model.run_query("SELECT *, DATE(created_at) as date_created FROM Shopping_list WHERE user_id = %s ORDER BY date_created DESC", 
                                                   (current_user.id,))
    if isinstance(shopping_lists, list):
        for sh_list in shopping_lists:
            sh_list['date_created'] = local_time_to_utc_range(user_tz, sh_list['created_at'])[2].strftime("%B %d, %Y")
            sh_list['shared_times'] = shopping_list_model.run_query("SELECT COUNT(*) as count FROM Shopping_list_shares WHERE shopping_list_id = %s", (sh_list['id'],))[0]['count']
    else:
        shopping_lists = []

    shared_lists = shopping_list_model.run_query("""
        SELECT sl.id, sl.name as name, u.user_name as owner_name, sls.shared_at as shared_at
        FROM Shopping_list_shares sls
        JOIN Shopping_list sl ON sls.shopping_list_id = sl.id
        JOIN Users u ON sl.user_id = u.id
        WHERE sls.user_id = %s
    """, (current_user.id,))

    if isinstance(shared_lists, list):
        for sh_list in shared_lists:
            sh_list['shared_at'] = local_time_to_utc_range(user_tz, sh_list['shared_at'])[2].strftime("%B %d, %Y")
    else:
        shared_lists = []

    menus = menu_model.run_query("SELECT id, menu_date FROM Menus WHERE user_id = %s AND menu_date >= %s", (current_user.id, user_now.date(),))

    return render_template('manage_shopping_lists.html', 
                           shopping_lists=shopping_lists, 
                           shared_lists=shared_lists, 
                           menus=menus)


@app.route('/shopping-list/<int:shop_list_id>/delete_shared_list', methods=['POST'])
@login_required
def delete_shared_list(shop_list_id):
    shopping_list_model.run_query("DELETE FROM Shopping_list_shares WHERE shopping_list_id = %s AND user_id = %s", (shop_list_id, current_user.id))
    return redirect(url_for('manage_shopping_lists'))


@app.route('/shopping-list/<int:list_id>/share-link', methods=['POST'])
@login_required
def create_share_link(list_id):
    token = secrets.token_urlsafe(24)
    expires_at = datetime.utcnow() + timedelta(hours=24)

    recipe_model.run_query(
        "INSERT INTO Shopping_list_invites (shopping_list_id, token, created_by, expires_at) VALUES (%s, %s, %s, %s)",
        (list_id, token, current_user.id, expires_at))
    share_url = url_for('join_shopping_list', token=token, _external=True)
    return jsonify({"share_url": share_url})


@app.route('/shopping-list/join/<token>')
@login_required
def join_shopping_list(token):
    invite = recipe_model.run_query(
        "SELECT * FROM Shopping_list_invites WHERE token = %s", (token,)
    )
    if not invite:
        abort(404)
    invite = invite[0]

    if invite['expires_at'] < datetime.utcnow():
        abort(410)  # gone/expired

    return redirect(url_for('shopping_list', shop_list_id=invite['shopping_list_id'], is_shared=True))

@app.route('/save-shared-list/<int:shopping_list_id>', methods=['POST'])
@login_required
def save_shared_list(shopping_list_id):
    user_id = current_user.id
    # Check if the user already has access
    existing_share = recipe_model.run_query(
        "SELECT * FROM Shopping_list_shares WHERE shopping_list_id = %s AND user_id = %s",
        (shopping_list_id, user_id)
    )
    if existing_share:
        flash('You already have access to this shopping list.', 'info')
        return redirect(url_for('shopping_list', shop_list_id=shopping_list_id, is_shared=True))

    recipe_model.run_query(
        "INSERT INTO Shopping_list_shares (shopping_list_id, user_id) VALUES (%s, %s)",
        (shopping_list_id, user_id)
    )
    flash('Shopping list saved to your account.', 'success')
    return redirect(url_for('shopping_list', shop_list_id=shopping_list_id))


@app.route('/shopping-lists/<int:shop_list_id>/pdf')
@login_required
def save_pdf(shop_list_id):
    # 1. Verify the user has access (owner OR shared collaborator)
    list_row = shopping_list_model.run_query(
        "SELECT * FROM Shopping_list WHERE id = %s", (shop_list_id,)
    )
    if not list_row:
        abort(404)
    list_row = list_row[0]

    is_owner = list_row['user_id'] == current_user.id
    is_shared = shopping_list_model.run_query(
        "SELECT 1 FROM Shopping_list_shares WHERE shopping_list_id = %s AND user_id = %s",
        (shop_list_id, current_user.id)
    )
    if not is_owner and not is_shared:
        abort(403)

    # 2. Fetch items (same query pattern as the GET view)
    db_query = """
        SELECT
            COALESCE(i.name, sli.item_name) as name,
            sli.measure, sli.units, sli.price, sli.if_checked,
            ic.name as category,
            sli.category_id
        FROM Shopping_list_ingredients sli
        LEFT JOIN Ingredients i ON sli.ingredient_id = i.id
        LEFT JOIN Ingredient_categories ic ON sli.category_id = ic.id
        WHERE sli.shop_list_id = %s
        ORDER BY category, name
    """
    items = shopping_list_items_model.run_query(db_query, (shop_list_id,))
    grouped_items = group_by_category(items)
    list_name = list_row['name'] or "My Shopping List"

    # 3. Build the PDF in memory
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
        leftMargin=0.7 * inch, rightMargin=0.7 * inch
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('ListTitle', parent=styles['Title'], fontSize=20, spaceAfter=6)
    category_style = ParagraphStyle('Category', parent=styles['Heading2'], spaceBefore=16, spaceAfter=6,
                                     textColor=colors.HexColor('#7b2ff7'))

    story = [Paragraph(list_name, title_style), Spacer(1, 12)]

    for category, cat_items in grouped_items.items():
        story.append(Paragraph(category or "Other", category_style))

        table_data = [["", "Item", "Qty", "Unit", "Price"]]
        for item in cat_items:
            checkbox = "[x]" if item['if_checked'] else "[ ]"
            table_data.append([
                checkbox,
                item['name'],
                str(item['measure']) if item['measure'] not in (None, '') else '',
                item['units'] or '',
                f"${item['price']:.2f}" if item['price'] is not None else ""
            ])

        table = Table(table_data, colWidths=[0.4 * inch, 3.6 * inch, 0.8 * inch, 1 * inch, 0.8 * inch])
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
            ('TOPPADDING', (0, 1), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ]))
        story.append(table)

    doc.build(story)
    buffer.seek(0)

    safe_name = "".join(c if c.isalnum() or c in " -_" else "" for c in list_name).strip() or "shopping-list"
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"{safe_name}.pdf"
    )

@app.route('/signin', methods=['GET', 'POST'])
def signin():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user_timezone = request.form.get('user_timezone', 'UTC')
        user_data = recipe_model.run_query("SELECT * FROM Users WHERE email = %s", (email,))

        if user_data and check_password_hash(user_data[0]['password_hash'], password):
            user = User(user_data[0]) # Assuming your User class
            users_model.update(user.id, {'timezone': user_timezone})
            # CHECK VERIFICATION STATUS
            if not user_data[0]['is_verified']:
                session['unverified_email'] = email
                flash('Please verify your email before logging in.', 'info')
                return redirect(url_for('verify_email'))

            login_user(user, remember=True, duration=timedelta(days=30))
            return redirect(url_for('menu'))

        flash('Invalid email or password.', 'error')
    return render_template('signin.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        # 1. Basic Validation
        if not all([username, email, password]):
            flash('All fields are required.', 'error')
            return redirect(url_for('signup'))

        # 2. Password Strength Check
        if not is_password_strong(password):
            flash('Password must be 8+ chars with uppercase, lowercase, number, and special char.', 'error')
            return redirect(url_for('signup'))

        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('signup'))

        try:
            # 3. Check if user already exists
            existing_user = recipe_model.run_query("SELECT id FROM Users WHERE email = %s OR user_name = %s", (email, username))
            if existing_user:
                flash('Email or Username already registered.', 'error')
                return redirect(url_for('signup'))

            # 4. Get Role ID safely
            roles = recipe_model.run_query("SELECT id FROM User_roles WHERE name = 'user'")
            role_id = roles[0]['id'] if roles else 1 # Fallback to ID 1 if roles table is empty

            # 5. Prepare Security Data
            hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
            verification_code = str(random.randint(100000, 999999))

            # 6. SINGLE DATABASE INSERT
            # We save the user as unverified (False) with their code immediately
            query = """INSERT INTO Users (user_name, email, role_id, password_hash, email_verification_code, is_verified)
                       VALUES (%s, %s, %s, %s, %s, %s)"""
            recipe_model.run_query(query, (username, email, role_id, hashed_pw, verification_code, False))

            # 7. Attempt to Send Email
            try:
                msg = Message('Your Verification Code', recipients=[email], sender=app.config['MAIL_USERNAME'])
                msg.body = f"Welcome to Menu Generator! Your verification code is: {verification_code}"
                mail.send(msg)

                session['unverified_email'] = email
                print(f"Verification code {verification_code} sent to {email}")
                flash("A verification code has been sent to your email.", "info")
                return redirect(url_for('verify_email'))

            except Exception as e:
                # If email fails, you might want to delete the user or allow them to "resend" later
                print(f"Mail Error: {e}")
                flash("Account created, but we couldn't send the code. Please try signing in to resend.", "warning")
                return redirect(url_for('signin'))

        except Exception as e:
            print(f"Signup Database Error: {e}")
            flash('An internal error occurred. Please try again.', 'error')
            return redirect(url_for('signup'))

    return render_template('signup.html')


@app.route('/verify_email', methods=['GET', 'POST'])
def verify_email():
    email = session.get('unverified_email')
    if not email:
        return redirect(url_for('signup'))

    if request.method == 'POST':
        user_code = request.form.get('code')

        # Fetch the real code from DB
        user = recipe_model.run_query("SELECT user_name, email_verification_code FROM Users WHERE email = %s", (email,))

        if user and user[0]['email_verification_code'] == user_code:
            send_welcome_email(email, user[0]['user_name'])
            # SUCCESS: Mark as verified
            recipe_model.run_query("UPDATE Users SET is_verified = %s WHERE email = %s", (True, email))
            session.pop('unverified_email', None)
            flash('Email verified! You can now log in.', 'success')
            return redirect(url_for('signin'))
        else:
            flash('Invalid code. Please check your email.', 'error')

    return render_template('verify_email.html', email=email)

@app.route('/resend_code')
def resend_code():
    email = session.get('unverified_email')
    if not email:
        flash('Session expired. Please sign in to resend code.', 'error')
        return redirect(url_for('signin'))

    new_code = str(random.randint(100000, 999999))
    recipe_model.run_query("UPDATE Users SET email_verification_code = %s WHERE email = %s", (new_code, email))

    # Send the email again
    msg = Message('Your New Verification Code', recipients=[email], sender=app.config['MAIL_USERNAME'])
    msg.body = f"Your new code is: {new_code}"
    mail.send(msg)

    flash('A new code has been sent.', 'info')
    return redirect(url_for('verify_email'))

@app.route('/reset_password_request', methods=['GET', 'POST'])
def reset_password_request():
    if request.method == 'POST':
        email = request.form.get('user_email')
        user = recipe_model.run_query("SELECT id FROM Users WHERE email = %s", (email,))
        if user:
            flash('If that email is registered, you will receive reset instructions.', 'info')

            # 2. If user exists, generate token and send email
            token = generate_reset_token(email)
            # Create the full link: https://yourname.pythonanywhere.com/reset_password/TOKEN
            reset_link = url_for('reset_password', token=token, _external=True)
            # Send the email with the reset link here
            msg = Message('Password Reset Request', recipients=[email], sender=app.config['MAIL_USERNAME'])
            msg.body = f"To reset your password, click the following link: {reset_link}"
            mail.send(msg)
        else:
            flash('If that email is registered, you will receive reset instructions.', 'info')
    return render_template('forgot_password.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    # In a real app, you'd verify the token against the DB or a timestamp
    if request.method == 'POST':
        new_password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if new_password == confirm_password:
            # Update user password in DB here
            new_password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
            email = verify_reset_token(token)  # This should return the email if token is valid
            if email:
                recipe_model.run_query("UPDATE Users SET password_hash = %s WHERE email = %s", (new_password_hash, email))
                flash('Your password has been reset!', 'success')
                return redirect(url_for('signin'))
            else:
                flash('Error resetting password. Please request a new link for password reset.', 'error')
        else:
            flash('Passwords do not match.', 'error')

    return render_template('reset_password.html', token=token)


@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    return render_template('forgot_password.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("You have been successfully logged out. See you next time!", "info")
    return redirect(url_for('signin'))


@app.route('/journal')
@login_required
def journal():
    user_current_time = local_time_to_utc_range(users_model.select_by_id(current_user.id)['timezone'] or 'UTC', return_now=True)[2]
    meals_from_db = meal_model.select_all()
    query_history = """
        SELECT 
            j.*, 
            COALESCE(m_direct.name, m_menu.name) as meal_type_display,
            COALESCE(r_direct.name, r_menu.name) as recipe_display_name,
            COALESCE(j.time_fact, mm.meal_time) as time_display
        FROM Journal j
        -- Joins for scheduled meals
        LEFT JOIN Menu_meals mm ON j.menu_meal_id = mm.id
        LEFT JOIN Recipes r_menu ON mm.recipe_id = r_menu.id
        LEFT JOIN Meals m_menu ON mm.meal_id = m_menu.id
        -- Joins for manual entries
        LEFT JOIN Meals m_direct ON j.meal_id = m_direct.id
        LEFT JOIN Recipes r_direct ON j.recipe_id = r_direct.id
        WHERE j.user_id = %s AND j.submitted_at IS NOT NULL
        ORDER BY j.created_at DESC
        LIMIT 20
    """
    history = recipe_model.run_query(query_history, (current_user.id,))
    print(f"Fetched {len(history)} journal entries for user_id {current_user.id}.")
    # Ensure 'Other' is available for the dropdown
    if meals_from_db is not None:
        meals_from_db.append({'id': 0, 'name': 'Other'})
        
    all_recipes = recipe_model.run_query("SELECT id, name FROM Recipes")
    journal_entries = recipe_model.run_query("""SELECT j.*,
                                                m.name as meal_type,
                                                r.name as recipe_name,
                                                mm.meal_time as time_display
                                                FROM Journal j
                                                LEFT JOIN Menu_meals mm ON j.menu_meal_id = mm.id
                                                LEFT JOIN Meals m ON (mm.meal_id = m.id OR j.meal_id = m.id)
                                                LEFT JOIN Recipes r ON (mm.recipe_id = r.id OR j.recipe_id = r.id)
                                                WHERE user_id = %s AND submitted_at IS NULL AND meal_as_planned = 1 ORDER BY created_at""", (current_user.id,))

    if journal_entries:
        for entry in journal_entries:
            entry['date'] = entry['created_at'].strftime("%B %d, %Y")
    return render_template('journal.html', journal_entries=journal_entries, meals=meals_from_db, all_recipes=all_recipes, history=history)


@app.route('/update_journal/<int:journal_id>', methods=['POST'])
@login_required
def update_journal(journal_id):
    try:
        # 1. Capture and cast form data
        # We cast to int to ensure database compatibility for the BOOLEAN/TINYINT field
        meal_as_planned = int(request.form.get('meal_as_planned', 1))
        
        # 2. Logic: If they ate as planned, we should wipe any previous 'meal_fact' 
        # to keep the data clean. If not, we take the new fact.
        meal_fact = request.form.get('meal_fact') if meal_as_planned == 0 else None
        
        mood = request.form.get('mood')
        thoughts = request.form.get('thoughts')

        # 3. Update the entry
        # We include current_user.id for security to ensure users can only update their own logs
        query = """
            UPDATE Journal 
            SET meal_as_planned = %s, 
                meal_fact = %s, 
                mood = %s, 
                thoughts = %s, 
                submitted_at = CURRENT_TIMESTAMP 
            WHERE id = %s AND user_id = %s
        """
        recipe_model.run_query(query, (meal_as_planned, meal_fact, mood, thoughts, journal_id, current_user.id))

        flash('Reflection saved!', 'success')
    except Exception as e:
        print(f"Error updating journal {journal_id}: {e}")
        flash('An error occurred. Please try again.', 'error')
        
    return redirect(url_for('journal'))


@app.route('/create-journal-entry', methods=['GET', 'POST'])
@login_required
def create_journal_entry():
    meals_from_db = meal_model.select_all()
    meals_from_db.append({'id': 0, 'name': 'Other'}) if meals_from_db else None
    user_time_now = local_time_to_utc_range(users_model.select_by_id(current_user.id)['timezone'] or 'UTC', return_now=True)[2]

    menus_today = menu_model.run_query("SELECT id FROM Menus WHERE user_id = %s AND menu_date = %s", (current_user.id, user_time_now.date()))

    menus_today.append({'id': 0, 'name': 'None'}) if not menus_today else None

    if request.method == 'POST':
        meal_id = request.form.get('meal_type')
        meal_fact = request.form.get('meal_fact')
        print(f"Received form data - Meal ID: {meal_id}, Meal Fact: {meal_fact}")
        recipe_id = request.form.get('recipe_id')
        time_fact = request.form.get('time_fact')
        mood = request.form.get('mood')
        thoughts = request.form.get('thoughts')
        try:
            if not meal_fact:
                menu_meal_id = menu_meals_model.run_query("SELECT id FROM Menu_meals WHERE menu_id = %s AND meal_id = %s", (menus_today[0]['id'], meal_id))[0]['id'] if menus_today and menus_today[0]['id'] != 0 else None
                recipe_model.run_query(
                        "INSERT INTO Journal (user_id, menu_meal_id, mood, thoughts, submitted_at) VALUES (%s, %s, %s, %s, %s)",
                        (current_user.id, menu_meal_id, mood, thoughts, datetime.now(timezone.utc))
                    )
                flash('Journal entry created successfully!', 'success')
                
            elif meal_fact:
                menu_meal_id = menu_meals_model.run_query("SELECT id FROM Menu_meals WHERE menu_id = %s AND meal_id = %s", (menus_today[0]['id'], meal_id))[0]['id'] if menus_today and menus_today[0]['id'] != 0 else None 
                recipe_model.run_query(
                        "INSERT INTO Journal (user_id, menu_meal_id, meal_as_planned, meal_fact, recipe_id, time_fact, mood, thoughts, submitted_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (current_user.id, menu_meal_id, 0, meal_fact, recipe_id or None, time_fact, mood, thoughts, datetime.now(timezone.utc))
                    )
                flash('Journal entry created successfully!', 'success')
            else:
                flash('Please select how the meal went.', 'error')
        except Exception as e:
                    print(f"Error creating journal entry: {e}")
                    flash('An error occurred while creating the journal entry. Please try again.', 'error')
        
        return redirect(url_for('journal'))
    

    return redirect(url_for('journal'))

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

@app.errorhandler(410)
def gone(e):
    return render_template('410.html'), 410

if __name__ == '__main__':
    app.run(debug=True)