from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///C:/Users/frank/Desktop/Cloud Computing/EU4SaveStats/sqlite.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class CurrentState(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String, nullable=False)
    income = db.Column(db.String, nullable=False)
    manpower = db.Column(db.Float, nullable=False)
    max_manpower = db.Column(db.Float, nullable=False)
    trade_income = db.Column(db.Float, nullable=False)

class HistoricalEvents(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String, nullable=False)
    event_type = db.Column(db.String, nullable=False)
    details = db.Column(db.String, nullable=False)

class AnnualIncome(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.String, nullable=False)
    income = db.Column(db.Float, nullable=False)

@app.route('/')
def index():
    # Verify database connection
    print("Database URI:", app.config['SQLALCHEMY_DATABASE_URI'])

    # Query all tables
    current_state = CurrentState.query.first()
    historical_events = HistoricalEvents.query.all()
    annual_income = AnnualIncome.query.order_by(AnnualIncome.year).all()

    # Debug print to verify query results
    print("Current State from Database:", current_state)
    print("Historical Events from Database:", historical_events)
    print("Annual Income from Database:", annual_income)

    return render_template(
        'index.html',
        current_state=current_state,
        historical_events=historical_events,
        annual_income=annual_income
    )

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)