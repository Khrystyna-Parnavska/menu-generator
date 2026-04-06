from apscheduler.schedulers.background import BackgroundScheduler
import atexit
from app import send_meal_reminders

scheduler = BackgroundScheduler()
scheduler.add_job(func=send_meal_reminders, trigger="interval", minutes=5)
scheduler.start()

atexit.register(lambda: scheduler.shutdown())
