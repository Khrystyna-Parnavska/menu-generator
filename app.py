from flask import Flask, render_template, redirect, request, url_for
from flask_scss import Scss
import database.models as m
import random
import datetime

meal_model = m.MealsModel()
menu_model = m.MenuModel()
menu_meals_model = m.MenuMealsModel()
users_model = m.UsersModel()
recipe_model = m.RecipesModel()

meals_from_db = meal_model.get_all()

app = Flask(__name__)
Scss(app, static_dir='static', asset_dir='assets')

@app.route('/')
def home():
    return render_template('index.html')


# route for menu page
@app.route('/menu')
def menu():
    return render_template('menu.html', all_meals=meals_from_db)


@app.route('/init-plan', methods=['POST'])
def init_plan():
    # TODO CHECK IF THERE'S A MENU ALREADY FOR THIS USER TODAY AND HANDLE IT
    # 1. Get the list of names from the checkboxes
    selected_names = request.form.getlist('meals')

    # get user_id(test)
    user_id = users_model.run_query("SELECT id FROM Users WHERE user_name = %s", ('test_user',))[0]['id']
    
    if not selected_names:
        return render_template('menu.html', all_meals=meals_from_db, error="Please select at least one meal!")
    
    # 2. Create a new menu and get its ID
    menu_id = menu_model.insert({'user_id': user_id})

    # 3. For each selected meal name, get its ID and associate it with the menu
    draft_menu_meals = []

    for name in selected_names:

        meal = meal_model.run_query("SELECT id, default_time FROM Meals WHERE name = %s", (name,))[0]
        meal_id = meal['id']
        meal_time = meal['default_time']

        list_recipes = recipe_model.run_query("SELECT * FROM Recipes WHERE meal_id = %s", (meal_id,))
        recipe = random.choice(list_recipes)

        cols = menu_meals_model.columns 
        last_id = menu_meals_model.insert({cols[1]: menu_id, cols[2]: meal_id, cols[3]: recipe['id'], cols[4]: meal_time, cols[5]: 0, cols[6]: 0})
        draft_meal = menu_meals_model.get_by_id(last_id)
        draft_meal['recipe_name'] = recipe['name']
        draft_meal['meal_type'] = name
        draft_menu_meals.append(draft_meal)
        print(draft_meal)

    # Final formatting loop for Jinja2
    for meal in draft_menu_meals:
        if isinstance(meal['meal_time'], datetime.timedelta):
            # Calculate hours and minutes from total seconds
            total_seconds = int(meal['meal_time'].total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            # Format as "HH:MM" (e.g., 07:00)
            meal['meal_time'] = f"{hours:02}:{minutes:02}"    

    return render_template('menu.html', menu_meals=draft_menu_meals, all_meals=meals_from_db)


@app.route('/regenerate-meal/<int:meal_id>', methods=['POST'])
def regenerate_meal(meal_id):
    # 1. Find the current meal entry
    current_menu_meal = menu_meals_model.get_by_id(meal_id)
    
    # 2. Get a new random recipe for the same meal_id category
    recipes = recipe_model.run_query("SELECT id FROM Recipes WHERE meal_id = %s", (current_menu_meal['meal_id'],))
    new_recipe = random.choice(recipes)
    
    # 3. Update only this specific row
    menu_meals_model.update(meal_id, {
        'recipe_id': new_recipe['id'],
        'regenerated_times': current_menu_meal['regenerated_times'] + 1,
        'subbitted_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })
    
    # 4. Redirect back to the menu page to show the update
    return redirect(url_for('menu'))


@app.route('/submit-final-menu', methods=['POST'])
def submit_final_menu():
    # 1. Get the list of IDs from the hidden inputs
    meal_ids = request.form.getlist('meal_ids[]')
    menu_id = request.form.get('menu_id')

    for m_id in meal_ids:
        # 2. Grab the specific time for THIS meal ID
        # If the user changed it in the browser, request.form.get will have the NEW value.
        new_time = request.form.get(f'meal_time_{m_id}')
        
        # 3. Grab the leftover status
        is_leftover = 1 if request.form.get(f'leftover_{m_id}') else 0
        
        # 4. Update the database
        # This saves the final time, even if it wasn't changed (it just saves the same value back)
        menu_meals_model.update(m_id, {
            'meal_time': new_time,
            'is_leftover_plan': is_leftover, # Using your specific column
        })
        menu_model.update(menu_id, {
            'submitted_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        selected_names = request.form.getlist('meals')

    
    return render_template('menu.html', 
                           all_meals=selected_names, 
                           success_message="Menu finalized and times saved!")

if __name__ == '__main__':
    app.run(debug=True)
    
    