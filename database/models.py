import csv
from .db_connector import create_connection


class BaseModel:
    """Base model to provide database db."""

    def __init__(self, table_name, columns):
        self.table_name = table_name
        self.columns = columns # List of column names in the table
    def run_query(self, query, params:tuple = ()):
        """
        Run a given SQL query with optional parameters.
        Args:
            query (str): The SQL query to execute.
            params (tuple, optional): Parameters for the SQL query. Defaults to None.
        Returns: The result of the query, if inserting, returns last inserted ID."""
        db = create_connection()
        if db:
            cursor = db.cursor(dictionary=True)
            try:
                cursor.execute(query, params or ())
                if query.strip().upper().startswith("SELECT"):
                    results = cursor.fetchall()
                else:
                    # COMMIT the changes so they are visible to other queries
                    db.commit()
                    # RETURN the last inserted ID for Foreign Key use
                    results = cursor.lastrowid # int
                return results
            except Exception as e:
                print(f"Query Error: {e}")
                return None
            finally:
                print(f"query executed: {query}")
                print(f"with params: {params}")
                print('Closing connection')
                print('-'*20)
                cursor.close()
                db.close()
        else:
            print("No database available.")
            return None
        
    def delete_all(self):
        """Delete all records from the table."""
        query = f"DELETE FROM {self.table_name}"
        return self.run_query(query)
    
    def delete(self, record_id):
        """Delete a record by its ID."""
        query = f"DELETE FROM {self.table_name} WHERE id = %s"
        return self.run_query(query, (record_id,))
    
    def insert(self, data: dict):
        """Insert a new record into the table."""
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['%s'] * len(data))
        values = tuple(data.values())
        query = f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})"
        return self.run_query(query, values)
    
    def update(self, record_id, data: dict):
        """Update a record by its ID."""
        set_clause = ', '.join([f"{key} = %s" for key in data.keys()])
        values = tuple(data.values()) + (record_id,)
        query = f"UPDATE {self.table_name} SET {set_clause} WHERE id = %s"
        return self.run_query(query, values)
    
    def get_by_id(self, record_id):
        """Retrieve a record by its ID."""
        query = f"SELECT * FROM {self.table_name} WHERE id = %s"
        results = self.run_query(query, (record_id,))
        return results[0] if results else None
    
    def get_all(self):
        """Retrieve all records from the table."""
        query = f"SELECT * FROM {self.table_name}"
        return self.run_query(query)
    
    def filter_by(self, **conditions):
        """Retrieve records matching given conditions."""
        where_clause = ' AND '.join([f"{key} = %s" for key in conditions.keys()])
        values = tuple(conditions.values())
        query = f"SELECT * FROM {self.table_name} WHERE {where_clause}"
        return self.run_query(query, values)
    
    def populate_from_csv(self, file_path, delimiter=',', encoding='utf-8'):
        """
        Reads a CSV and inserts data based on the columns 
        defined in the child class (e.g., self.columns).
        """
        db = create_connection()
        if db:
            cursor = db.cursor()

        try:
            with open(file_path, mode='r', encoding=encoding) as f:
                reader = csv.DictReader(f, delimiter=delimiter)
                # Clean headers to avoid hidden space issues
                csv_headers = [name.strip() for name in reader.fieldnames]
                reader.fieldnames = csv_headers

                # 1. FIND THE INTERSECTION
                # We only use columns that are both in your Model AND in the CSV
                # (Excluding 'id' because it's auto-increment)
                cols_to_use = [col for col in self.columns if col in csv_headers and col != 'id']
                    
                if not cols_to_use:
                    print(f"❌ Error: No matching columns found between Model and CSV.")
                    return 

                # 2. DYNAMICALLY BUILD THE SQL
                columns_str = ", ".join(cols_to_use)
                placeholders = ", ".join(["%s"] * len(cols_to_use))
                sql = f"INSERT INTO {self.table_name} ({columns_str}) VALUES ({placeholders})"

                rows_to_insert = []
                for row in reader:
                    # 3. EXTRACT ONLY THE NEEDED DATA
                    # row.get(col) handles cases where a row might be missing a value
                    values = tuple(row.get(col).strip() if row.get(col) else None for col in cols_to_use)
                    rows_to_insert.append(values)
                    
                if rows_to_insert:
                    cursor.executemany(sql, rows_to_insert)
                    db.commit()
                    print(f"✅ Successfully imported {len(rows_to_insert)} rows into {self.table_name}")
                    print(f"Columns used: {cols_to_use}")

        except Exception as e:
            print(f"❌ CSV Import Error: {e}")
            db.rollback()
        finally:
            cursor.close()
            db.close()
    
# TODO: AUTOMATE COLUMNS NAME FETCHING FROM THE DB SCHEMA
class MealsModel(BaseModel):
    """Model for the 'Meals' table."""
    def __init__(self):
        super().__init__('Meals', ['id', 'name', 'default_time'])


class MenuModel(BaseModel):
    """Model for the 'Menus' table."""
    def __init__(self):
        super().__init__('Menus', ['id', 'user_id', 'created_at', 'submitted_at'])


class MenuMealsModel(BaseModel):
    """Model for the 'Menu_meals' table."""
    def __init__(self):
        super().__init__('Menu_meals', ['id', 
                                       'menu_id', 
                                       'meal_id', 
                                       'recipe_id', 
                                       'meal_time', 
                                       'regenerated_times', 
                                       'if_picked_manually', 
                                       'submitted_at'])


class RecipesModel(BaseModel):
    """Model for the 'Recipes' table."""
    def __init__(self):
        super().__init__('Recipes', ['id', 
                                     'name', 
                                     'external_id', 
                                     'country_id', 
                                     'meal_id', 
                                     'category_id', 
                                     'n_portions', 
                                     'prep_time', 
                                     'cooking_time', 
                                     'area', 
                                     'thumb', 
                                     'source_url', 
                                     'youtube', 
                                     'rating', 
                                     'created_at'])
        
class CategoriesModel(BaseModel):
    """Model for the 'Categories' table."""
    def __init__(self):
        super().__init__('Categories', ['id', 'name'])

class CountriesModel(BaseModel):
    """Model for the 'Countries' table."""
    def __init__(self):
        super().__init__('Countries', ['id', 'name'])


class IngredientsModel(BaseModel):
    """Model for the 'Ingredients' table."""
    def __init__(self):
        super().__init__('Ingredients', ['id', 'name'])


class UsersModel(BaseModel):
    """Model for the 'Users' table."""
    def __init__(self):
        super().__init__('Users', ['id', 
                                   'username', 
                                   'email', 
                                   'role_id', 
                                   'password_hash', 
                                   'created_at', 
                                   'is_active', 
                                   'country_id', 
                                   'age_full_years', 
                                   'birth_date',])

class UserRolesModel(BaseModel):
    """Model for the 'User_roles' table."""
    def __init__(self):
        super().__init__('User_roles', ['id', 'name', 'description'])


class FavoritesRecipesModel(BaseModel):
    """Model for the 'User_favorite_recipes' table."""
    def __init__(self):
        super().__init__('User_favorite_recipes', ['id', 'user_id', 'recipe_id', 'added_at'])
# TODO : Add other models as needed

if __name__ == "__main__":    # Example usage
    pass