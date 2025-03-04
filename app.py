from flask import Flask, render_template, request, redirect, url_for
import sqlite3

app = Flask(__name__)

# Database file path
DATABASE = 'C:/Users/frank/Desktop/Cloud Computing/EU4SaveStats/sqlite.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    conn = get_db_connection()
    files = conn.execute('SELECT * FROM uploaded_files').fetchall()
    conn.close()
    return render_template('index.html', files=files)

@app.route('/file/<int:file_id>')
def file_details(file_id):
    conn = get_db_connection()
    file_info = conn.execute('SELECT * FROM uploaded_files WHERE id = ?', (file_id,)).fetchone()
    
    # Get current state data for all countries in this file
    current_states = conn.execute('''
        SELECT country_tag, date, income, manpower, max_manpower, trade_income 
        FROM current_state 
        WHERE file_checksum = ?
    ''', (file_info['file_checksum'],)).fetchall()
    
    # Get annual income data for all countries in this file
    annual_incomes = conn.execute('''
        SELECT country_tag, year, income 
        FROM annual_income 
        WHERE file_checksum = ?
    ''', (file_info['file_checksum'],)).fetchall()
    
    # Get historical events for all countries in this file
    historical_events = conn.execute('''
        SELECT country_tag, date, event_type, details 
        FROM historical_events 
        WHERE file_checksum = ?
    ''', (file_info['file_checksum'],)).fetchall()
    
    conn.close()
    
    # Organize data for the template
    countries_data = {}
    for state in current_states:
        country_tag = state['country_tag']
        if country_tag not in countries_data:
            countries_data[country_tag] = {
                'current_state': state,
                'annual_income': [],
                'historical_events': []
            }
    
    for income in annual_incomes:
        country_tag = income['country_tag']
        if country_tag in countries_data:
            countries_data[country_tag]['annual_income'].append(income)
    
    for event in historical_events:
        country_tag = event['country_tag']
        if country_tag in countries_data:
            countries_data[country_tag]['historical_events'].append(event)
    
    return render_template('file_details.html', file_info=file_info, countries_data=countries_data)

if __name__ == '__main__':
    app.run(debug=True)