import os
from app import menu
from database.db_connector import create_connection
from database.models import BaseModel
import pandas as pd

def run_schema( path='database', schema_file_name='schema.sql'):
    # 1. Path to your schema file
    schema_path = os.path.join(path, schema_file_name)
    
    # 2. Connect to the DB
    db = create_connection()
    if not db:
        print("Could not connect to database. Is Docker running?")
        return

    cursor = db.cursor()

    try:
        # 3. Read the SQL file
        with open(schema_path, 'r') as f:
            # We split by ';' to execute one command at a time
            sql_commands = f.read().split(';')
        
        db.start_transaction()
        # 4. Execute each command
        for command in sql_commands:
            if command.strip():
                print(f"Executing: {command[:40]}...")
                cursor.execute(command)
        
        db.commit()
        print("\n✅ Success: All tables created successfully!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        db.rollback()
    finally:
        cursor.close()
        db.close()


def populate_meals(meals_model: BaseModel):
    '''
    Populate the Meals table with predefined meal data.
    Args:
        meals_model: The MealsModel instance.
    '''
    print('Populating Meals table...')
    for meal in meals_dict:
        if list(meal.keys()) == meals_model.columns[1:]:
            try:
                meals_model.insert(meal)
                print(f"Inserted meal: {meal['name']}")
            except Exception as e:
                print(f"Error inserting meal {meal['name']}: {e}")
    print('-'*10)
    print('meals insertion attempt finished')


meals_dict = [
    {'name': 'Breakfast', 'default_time': '07:00:00'},
    {'name': 'Morning Snack', 'default_time': '10:00:00'},
    {'name': 'Lunch', 'default_time': '12:30:00'},
    {'name': 'Afternoon Snack', 'default_time': '16:00:00'},
    {'name': 'Dinner', 'default_time': '19:00:00'},
    {'name': 'Evening Snack', 'default_time': '21:00:00'}
]

test_user = {'user_name': 'test_user', 
             'email': 'test@example.com', 
             'role_id': None, 
             'password_hash': 123456789, 
             'is_active': True, 
             'country_id': None, 
             'age_full_years': None, 
             'birth_date': None}

sources_dict = [
    {
        'name': 'Menu_Generator',
        'description': 'A custom menu generator for testing and development purposes.'
    },
    {
        'name': 'User_submitted',
        'description': 'Recipes and ingredients submitted by users of the menu generator application. These recipes are added for testing and development purposes and may not be suitable for commercial use.'
    },
    {
        'name': 'AllRecipes',
        'description': 'A popular recipe website that offers a wide variety of recipes with detailed information, including ingredients, instructions, and images. It is free for non-commercial use with some limitations, making it suitable for testing and development.'
    },
    {
        'name': 'TheMealDB',
        'description': 'Not free for commercial use, but free for personal use. Provides a wide variety of meals and recipes with detailed information, including ingredients, instructions, and images. It is a great source for testing and development purposes.'
    },
    {
        'name': 'Spoonacular',
        'description': 'Offers a comprehensive API with access to a vast database of recipes, ingredients, and nutritional information. It is free for non-commercial use with some limitations, making it suitable for testing and development.'
    },
    {
        'name': 'Edamam',
        'description': 'Provides a rich API with access to a large database of recipes, ingredients, and nutritional information. It is free for non-commercial use with some limitations, making it a good choice for testing and development.'
    },
    {
        'name': 'OpenFoodAPI',
        'description': 'A free and open API that provides access to a large database of food products, including ingredients and nutritional information. It is a great resource for testing and development purposes.'
    },
    {
        'name': 'FoodData Central',
        'description': 'A free API provided by the USDA that offers access to a comprehensive database of food products, including ingredients and nutritional information. It is an excellent source for testing and development.'
    },
    {
        'name': 'Recipe Puppy',
        'description': 'A simple and free API that provides access to a database of recipes based on ingredients. It is a good option for testing and development purposes, especially for basic recipe retrieval.'
    },
    {
        'name': 'Yummly',
        'description': 'Offers a comprehensive API with access to a vast database of recipes, ingredients, and nutritional information. It is free for non-commercial use with some limitations, making it suitable for testing and development.'
    }
    ]


recipes_path = os.path.join('data', 'recipes_db_the_meal_db.csv')


if __name__ == "__main__":

    run_schema()
    meals_model = BaseModel('Meals')
    recipe_categories_model = BaseModel('Recipe_categories')
    recipes_model = BaseModel('Recipes')
    users_model = BaseModel('Users')
    user_roles_model = BaseModel('User_roles')
    countries_model = BaseModel('Countries')
    favorites_recipes_model = BaseModel('User_favorite_recipes')
    recipe_ingredients_model = BaseModel('Recipes_ingredients')
    units_model = BaseModel('Units')
    ingredients_model = BaseModel('Ingredients')


    populate_meals(meals_model)

    #populate countries
    countries_model.populate_from_csv(os.path.join('data', 'countries_db.csv'), 'Countries', delimiter=',')

    #user roles
    user_roles = [
        {'name': 'admin', 'description': 'Admin role with full permissions'},
        {'name': 'user', 'description': 'Regular user role with limited permissions'},
    ]
    user_roles_model.insert_many(user_roles)


    # sources
    source_model = BaseModel('Data_sources')
    print('Inserting data sources...')
    source_model.insert_many(sources_dict)

    themealdb_id = source_model.run_query("SELECT id FROM Data_sources WHERE name = %s", ('TheMealDB',))[0]['id']
    menu_generator_id = source_model.run_query("SELECT id FROM Data_sources WHERE name = %s", ('Menu_Generator',))[0]['id']

    #ingredients_the_meal_db
    recipes_model.populate_from_csv(os.path.join('data', 'ingredient_categories.csv'), 'Ingredient_categories', delimiter=',')
    others_id = recipes_model.run_query("SELECT id FROM Ingredient_categories WHERE name = %s", ('Other',))[0]['id']
    recipes_model.populate_from_csv(os.path.join('data', 'ingredients_db_the_meal_db.csv'), 'Ingredients', delimiter=',')
    ingredients_model.run_query("UPDATE Ingredients SET source_id = %s", (themealdb_id,))


    #ingredient categories map
    ing_cat_map_model = BaseModel('Ingredients_categories_map')
    ingredients_data = ingredients_model.select_all()
    if ingredients_data is not None and isinstance(ingredients_data, list):
        for ingredient in ingredients_data:
            ing_cat_map_model.insert({'ingredient_id': ingredient['id'], 'category_id': others_id, 'source_id': menu_generator_id})
    

    #units
    units_model.populate_from_csv(os.path.join('data', 'units.csv'), 'Units', delimiter=',')
    units_model.run_query("UPDATE Units SET source_id = %s", (menu_generator_id,))

    #recipe_categories
    recipe_categories_model.populate_from_csv(os.path.join('data', 'recipe_categories_the_meal_db.csv'), 'Recipe_categories', delimiter=',')
    recipe_categories_model.run_query("UPDATE Recipe_categories SET source_id = %s", (themealdb_id,))

    #recipes
    recipes_model.populate_from_csv(recipes_path, 'Recipes', delimiter=',')
    recipes_model.run_query("UPDATE Recipes SET source_id = %s", (themealdb_id,))

    #recipe_ingredients
    recipe_ingredients_model.populate_from_csv(os.path.join('data', 'recipe_ingredients_db_the_meal_db.csv'), 'Recipes_ingredients', delimiter=',')
    recipe_ingredients_model.run_query("UPDATE Recipes_ingredients SET source_id = %s", (themealdb_id,))