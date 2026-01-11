import os
import mysql.connector
from mysql.connector import Error   
from dotenv import load_dotenv

load_dotenv()

def create_connection():
    """Create a database connection using environment variables."""
    try:
        connection = mysql.connector.connect(
            host=os.getenv('DB_HOST'),
            port=os.getenv('DB_PORT'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME')
        )
        if connection.is_connected():
            print("Connection to the database was successful.")
            return connection 
    except Error as e:
        print(f"Error: {e}")
        return None
    
if __name__ == "__main__":
    conn = create_connection()

    if conn:
        print("You can now use the connection object to interact with the database.")
        conn.close()