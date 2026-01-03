from flask import Flask
from flask_scss import Scss


app = Flask(__name__)
Scss(app, static_dir='static', asset_dir='assets')

@app.route('/')
def home():
    return 'Welcome to the Flask SCSS Example!'


if __name__ == '__main__':
    app.run(debug=True)