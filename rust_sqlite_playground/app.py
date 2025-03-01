from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///C:/Users/frank/Desktop/Cloud Computing/EU4SaveStats/sqlite.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

with app.app_context():
    db.create_all()

class Settings(db.Model):
    settings_id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String, nullable=False)
    created_on = db.Column(db.DateTime)
    updated_on = db.Column(db.DateTime)
    done = db.Column(db.Boolean, default=False)

@app.route('/')
def index():
    settings = Settings.query.all()
    return render_template('index.html', settings=settings)

if __name__ == '__main__':
    app.run(debug=True)