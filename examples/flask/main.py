from flask import Flask
from flask_cors import CORS


app = Flask(__name__)
CORS(app)

@app.route('/')
def index():
    return "Welcome to the Flask app!"

@app.route('/hello')
def hello():
    return "Hello, World!"