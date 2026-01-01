import csv
from db_connector import create_connection


class BaseModel:
    """Base model to provide database db."""

    def __init__(self, table_name, columns):
        self.table_name = table_name
        self.columns = columns # List of column names in the table
    def run_query(self, query, params=None):
        """Run a given SQL query with optional parameters."""
        db = create_connection()
        if db:
            cursor = db.cursor(dictionary=True)
            try:
                cursor.execute(query, params or ())
                if query.strip().upper().startswith("SELECT"):
                    results = cursor.fetchall()
                else:
                    results = None
                    db.commit()
                return results
            except Exception as e:
                print(f"Query Error: {e}")
                return None
            finally:
                cursor.close()
                db.close()
        else:
            print("No database db available.")
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
        cursor = db.cursor()
        
        # We use self.columns which you mentioned you store in your model
        columns = self.columns[1:]  # Skip 'id' assuming it's auto-increment
        columns_str = ", ".join(columns)  # Skip 'id' assuming it's auto-increment
        placeholders = ", ".join(["%s"] * len(columns))
        sql = f"INSERT INTO {self.table_name} ({columns_str}) VALUES ({placeholders})"

        try:
            with open(file_path, mode='r', encoding=encoding) as f:
                # DictReader uses the first row of the CSV as keys
                reader = csv.DictReader(f, delimiter=delimiter)
                
                rows_to_insert = []
                for row in reader:
                    # Extract only the values that match our model's columns
                    values = tuple(row[col] for col in columns)
                    rows_to_insert.append(values)
                
                # executemany is MUCH faster than running a loop of single inserts
                cursor.executemany(sql, rows_to_insert)
                
                db.commit()
                print(f"✅ Successfully imported {cursor.rowcount} rows into {self.table_name}")

        except Exception as e:
            print(f"❌ CSV Import Error: {e}")
            db.rollback()
        finally:
            cursor.close()
            db.close()
    

class MealsModel(BaseModel):
    """Model for the 'Meals' table."""
    def __init__(self):
        super().__init__('Meals', ['id', 'name', 'default_time'])


class MenuModel(BaseModel):
    """Model for the 'Menu' table."""
    def __init__(self):
        super().__init__('Menu', ['id', 'user_id', 'created_at', 'submitted_at'])

class MenuMealsModel(BaseModel):
    """Model for the 'MenuMeals' table."""
    def __init__(self):
        super().__init__('MenuMeals', ['id', 
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

if __name__ == "__main__":    # Example usage
    pass