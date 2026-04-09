import sys
import os
from datetime import datetime

# 1. Path Setup: Replace with your actual PythonAnywhere username/folder
project_home = u'/home/khrystyna/menu_generator'
if project_home not in sys.path:
    sys.path.append(project_home)

# 2. Import the necessary components from your main app file
# Assuming your main file is 'main.py' or 'app.py'
from app import app, mail, recipe_model, users_model, local_time_to_utc_range
from flask_mail import Message

def send_meal_reminders():
    # We use 'with app.app_context()' so Flask knows our MAIL_SERVER settings
    with app.app_context():
        print(f"[{datetime.now()}] Running meal reminder job...")
        
        all_users = users_model.select_all()

        for user_data in all_users:
            user_id = user_data['id']
            # Re-fetch or use existing data to get timezone
            user_tz = user_data.get('timezone') or 'UTC'

            # Get user's local 'now'
            _, _, local_now = local_time_to_utc_range(user_tz, return_now=True)
            
            query = """
                SELECT mm.id, m.menu_date, u.email, r.name as recipe_name, mm.meal_time
                FROM Menu_meals mm
                JOIN Menus m ON mm.menu_id = m.id
                JOIN Users u ON m.user_id = u.id
                JOIN Recipes r ON mm.recipe_id = r.id
                WHERE mm.meal_time BETWEEN %s AND DATE_ADD(%s, INTERVAL 1 HOUR)
                AND m.user_id = %s 
                AND m.submitted_at IS NOT NULL
                AND m.menu_date = %s
                AND mm.reminder_sent = 0
            """
            
            # Note: We use local_now.time() for the range check
            upcoming_meals = recipe_model.run_query(query, (
                local_now.time(), 
                local_now.time(), 
                user_id, 
                local_now.date()
            ))

            if not upcoming_meals:
                continue

            for meal in upcoming_meals:
                try:
                    msg = Message("🍳 Time to Cook!",
                                  sender=app.config['MAIL_USERNAME'],
                                  recipients=[meal['email']])

                    menu_url = "https://yourusername.pythonanywhere.com/menu"

                    msg.html = f"""
                    <div style="font-family: sans-serif; max-width: 400px; margin: auto; border: 1px solid #5d3f9b; padding: 20px; border-radius: 15px; text-align: center; background-color: #f9f9f9;">
                        <h2 style="color: #ff66b2;">Kitchen Time!</h2>
                        <p>It's almost time for your <strong>{meal['recipe_name']}</strong>.</p>
                        <p>Scheduled for: <strong>{meal['meal_time']}</strong></p>
                        <a href="{menu_url}" style="background-color: #5d3f9b; color: white; padding: 10px 20px; text-decoration: none; border-radius: 25px; display: inline-block;">View Recipe</a>
                    </div>
                    """
                    
                    mail.send(msg)
                    
                    # Mark as sent immediately
                    recipe_model.run_query("UPDATE Menu_meals SET reminder_sent = 1 WHERE id = %s", (meal['id'],))
                    print(f"Success: Reminder sent to {meal['email']} for {meal['recipe_name']}")
                    
                except Exception as e:
                    print(f"Failed to send email for meal {meal['id']}: {e}")

if __name__ == "__main__":
    send_meal_reminders()