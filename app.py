from flask import Flask, render_template, redirect, request
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
    # 1. Get the list of names from the checkboxes
    selected_names = request.form.getlist('meals')

    # get user_id(test)
    user_id = users_model.run_query("SELECT id FROM Users WHERE user_name = %s", ('test_user',))[0]['id']
    
    if not selected_names:
        return render_template('menu.html', all_meals=meals_from_db, error="Please select at least one meal!")
    
    # 2. Create a new menu and get its ID
    menu_id = menu_model.insert({'user_id': user_id})
    '''menu_id = menu_model.run_query("SELECT LAST_INSERT_ID() as id")[0]['id']'''
    print('*'*50)
    print('*'*50)
    print("Created Menu ID:", menu_id)
    print('*'*50)
    print('*'*50)

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

        draft_menu_meals.append(menu_meals_model.get_by_id(last_id))
    
    # Final formatting loop for Jinja2
    for meal in draft_menu_meals:
        if isinstance(meal['meal_time'], datetime.timedelta):
            # Calculate hours and minutes from total seconds
            total_seconds = int(meal['meal_time'].total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            # Format as "HH:MM" (e.g., 07:00)
            meal['meal_time'] = f"{hours:02}:{minutes:02}"
    
    print("Draft Menu Meals:")
    for item in draft_menu_meals:
        print(item)

    return render_template('menu.html', menu_meals=draft_menu_meals, all_meals=meals_from_db)




if __name__ == '__main__':
    app.run(debug=True)
    
    