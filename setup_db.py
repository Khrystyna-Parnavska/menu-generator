import os
from database.db_connector import create_connection
from database.models import MealsModel, RecipesModel, CategoriesModel, UsersModel, UserRolesModel
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


def populate_meals(meals_model: MealsModel):
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


def add_test_category(categories_model: CategoriesModel):
    """Add a test category to the Categories table.
    Args:
        categories_model: The CategoriesModel instance.
    """
    categories_model.insert({'name': 'test'})
    print("Inserted test category.")

#TODO: MAKE THIS FUNCTION MORE GENERIC
def populate_basic_recipes(recipes_model: RecipesModel, meals_model: MealsModel, categories_model: CategoriesModel, path: str):
    """Populate the Recipes table from a CSV file.
    Args:
        recipes_model: The RecipesModel instance.
        meals_model: The MealsModel instance.
        categories_model: The CategoriesModel instance.
        path: Path to the CSV file containing recipe data.
    """
    test_recipes = pd.read_csv(path, delimiter=';', encoding='utf-8-sig')

    meals = []
    meals_data = meals_model.get_all()
    if meals_data is None or not isinstance(meals_data, list):
        print("Warning: No meals data retrieved from database.")
        return
    for meal in meals_data:
        id = meal['id']
        name = meal['name']
        meals.append((id, name))


    def get_meal_id(meal_name):
        for meal in meals:
            if meal[1] == meal_name:
                return meal[0]
        return None
    

    test_recipes['meal_id'] = test_recipes['meal_name'].apply(get_meal_id)
    
    test_id = None
    for category in categories_model.get_all():
        if category['name'] == 'test':
            test_id = category['id']
            break
    test_recipes['category_id'] = test_id

    test_recipes.drop(columns=['meal_name'], inplace=True)
    test_recipes.to_csv('data/recipes_test_processed.csv', index=False, sep=',', encoding='utf-8-sig')

    recipes_model.populate_from_csv('data/recipes_test_processed.csv', delimiter=',', encoding='utf-8-sig')
    print("Inserted test recipes.")

        

recipes_path = os.path.join('data', 'recipes_test.csv')


if __name__ == "__main__":

    run_schema()
    meals_model = MealsModel()
    recipes_model = RecipesModel()
    categories_model = CategoriesModel()
    users_model = UsersModel()
    user_roles_model = UserRolesModel()

    populate_meals(meals_model)
    add_test_category(categories_model)
    populate_basic_recipes(recipes_model, meals_model, categories_model, recipes_path)

    #test user
    user_roles_model.insert({'name': 'test_role', 'description': 'Test role'})
    test_role_id = user_roles_model.run_query("SELECT id FROM User_roles WHERE name = %s", ('test_role',))[0]['id']
    test_user['role_id'] = test_role_id
    users_model.insert(test_user)
    