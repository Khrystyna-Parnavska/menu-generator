import os
from database.db_connector import create_connection
from database.models import MealsModel, RecipesModel

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


def populate_meals():
    meals_model = MealsModel()

    for meal in meals_dict:
        if list(meal.keys()) == meals_model.columns[1:]:
            try:
                meals_model.insert(meal)
                print(f"Inserted meal: {meal['name']}")
            except Exception as e:
                print(f"Error inserting meal {meal['name']}: {e}")
    print('-'*10)
    print('meals insertion attempt finished')


recipes_path = os.path.join('data', 'recipes_test.csv')


def populate_basic_recipes(path:str=recipes_path):
    recipes_model = RecipesModel()
    recipes_model.populate_from_csv(path, delimiter=';', encoding='utf-8-sig')


if __name__ == "__main__":
    run_schema()
    populate_meals()
    populate_basic_recipes()
    
