from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
import matplotlib.pyplot as plt
import io
import base64
import random
import subprocess
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Required for flashing messages

# Database file path
DATABASE = 'C:/Users/frank/Desktop/Cloud Computing/EU4SaveStats/sqlite.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    """Call the Rust backend to initialize the database schema."""
    try:
        result = subprocess.run(
            ['cargo', 'run', '--', '--init-db'],
            capture_output=True,
            text=True,
            check=True
        )
        print("Database schema initialized successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error initializing database schema: {e.stderr}")

# Initialize the database schema when the application starts
initialize_database()

def parse_country_colors(file_path):
    country_colors = {}
    with open(file_path, 'r') as file:
        for line in file:
            if '=' in line:
                tag, color = line.split('=')
                tag = tag.strip()
                color = tuple(map(int, color.strip().split()))
                country_colors[tag] = color
    return country_colors

# Load country colors from the generated file
COUNTRY_COLORS = parse_country_colors('country_colors.txt')

def get_country_color(country_tag):
    return COUNTRY_COLORS.get(country_tag, (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)))

@app.route('/')
def index():
    conn = get_db_connection()
    files = conn.execute('SELECT * FROM uploaded_files').fetchall()
    conn.close()
    return render_template('index.html', files=files)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('No file uploaded.')
        return redirect(url_for('index'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected.')
        return redirect(url_for('index'))
    
    if not file.filename.endswith('.eu4'):
        flash('Invalid file type. Please upload a .eu4 file.')
        return redirect(url_for('index'))
    
    # Save the file to a temporary location
    upload_folder = 'uploads'
    os.makedirs(upload_folder, exist_ok=True)
    file_path = os.path.join(upload_folder, file.filename)
    file.save(file_path)
    
    # Call the Rust backend to process the file
    try:
        result = subprocess.run(
            ['cargo', 'run', '--', file_path],
            capture_output=True,
            text=True,
            check=True
        )
        flash('File processed successfully!')
    except subprocess.CalledProcessError as e:
        flash(f'Error processing file: {e.stderr}')
    finally:
        # Clean up the uploaded file
        os.remove(file_path)
    
    return redirect(url_for('index'))

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
    
    # Generate the annual income plot
    plt.figure(figsize=(10, 6))
    for country_tag, data in countries_data.items():
        years = [int(income['year']) for income in data['annual_income']]
        incomes = [income['income'] for income in data['annual_income']]
        color = get_country_color(country_tag)
        plt.plot(years, incomes, label=country_tag, color=(color[0]/255, color[1]/255, color[2]/255))
    
    plt.xlabel('Year')
    plt.ylabel('Income')
    plt.title('Annual Income by Country')
    plt.legend()
    plt.grid(True)
    
    # Save the plot to a BytesIO object
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plot_url = base64.b64encode(buf.getvalue()).decode('utf8')
    plt.close()
    
    return render_template('file_details.html', file_info=file_info, countries_data=countries_data, plot_url=plot_url)

if __name__ == '__main__':
    app.run(debug=True)