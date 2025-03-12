from flask import Flask, render_template, request, redirect, url_for, flash
import matplotlib.pyplot as plt
import io
import base64
import random
import subprocess
import os
import mysql.connector
import boto3
from botocore.exceptions import NoCredentialsError
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Access environment variables
db_host = os.getenv("DB_HOST")
db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_name = os.getenv("DB_NAME")

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Required for flashing messages

def upload_to_s3(file, bucket_name, key):
    s3 = boto3.client('s3')
    try:
        s3.upload_fileobj(file, bucket_name, key)
        return True
    except NoCredentialsError:
        return False

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

    # Upload the file to S3
    s3_bucket = 'eusavestats-bucket'
    s3_key = f"uploads/{file.filename}"
    if upload_to_s3(file, s3_bucket, s3_key):
        flash('File uploaded to S3 successfully!')
    else:
        flash('Failed to upload file to S3.')
        return redirect(url_for('index'))

    # Call the Rust backend to process the file
    try:
        result = subprocess.run(
            ['./eu4_parser', s3_key],  # Use the eu4_parser executable directly
            capture_output=True,
            text=True,
            check=True
        )
        flash('File processed successfully!')
    except subprocess.CalledProcessError as e:
        flash(f'Error processing file: {e.stderr}')

    return redirect(url_for('index'))

def get_db_connection():
    try:
        print("Connecting to database...")
        conn = mysql.connector.connect(
            host=db_host,
            user=db_user,
            password=db_password,
            database=db_name
        )
        print("Database connection successful.")
        return conn
    except mysql.connector.Error as err:
        print(f"Error connecting to database: {err}")
        raise

def initialize_database():
    """Create the database if it doesn't exist and initialize the schema."""
    try:
        print("Connecting to MySQL...")
        conn = mysql.connector.connect(
            host=db_host,
            user=db_user,
            password=db_password
        )
        print("Connected to MySQL.")
        cursor = conn.cursor()

        # Check if the database exists
        print("Checking if database 'save_stats' exists...")
        cursor.execute("SHOW DATABASES LIKE 'save_stats'")
        result = cursor.fetchone()

        if not result:
            # Create the database if it doesn't exist
            print("Database 'save_stats' does not exist. Creating it...")
            cursor.execute("CREATE DATABASE save_stats")
            print("Database 'save_stats' created successfully.")

        cursor.close()
        conn.close()

        # Call the Rust backend to initialize the schema
        print("Initializing database schema...")
        result = subprocess.run(
            ['./eu4_parser', '--init-db'],  # Use the eu4_parser executable directly
            capture_output=True,
            text=True,
            check=True
        )
        print("Database schema initialized successfully.")
        print(result.stdout)  # Print the output of the Rust backend
    except subprocess.CalledProcessError as e:
        print(f"Error initializing database schema: {e.stderr}")
    except mysql.connector.Error as err:
        print(f"Error connecting to MySQL: {err}")

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
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM uploaded_files')
    files = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('index.html', files=files)

@app.route('/file/<int:file_id>')
def file_details(file_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM uploaded_files WHERE id = %s', (file_id,))
    file_info = cursor.fetchone()
    
    # Fetch current state data
    cursor.execute('''
        SELECT country_tag, date, income, manpower, max_manpower, trade_income 
        FROM current_state 
        WHERE file_checksum = %s
    ''', (file_info['file_checksum'],))
    current_states = cursor.fetchall()
    
    # Fetch annual income data
    cursor.execute('''
        SELECT country_tag, year, income 
        FROM annual_income 
        WHERE file_checksum = %s
    ''', (file_info['file_checksum'],))
    annual_incomes = cursor.fetchall()
    
    # Fetch historical events
    cursor.execute('''
        SELECT country_tag, date, event_type, details 
        FROM historical_events 
        WHERE file_checksum = %s
    ''', (file_info['file_checksum'],))
    historical_events = cursor.fetchall()
    
    cursor.close()
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
    print("Starting the application...")
    app.run(host='0.0.0.0', port=5000, debug=True)
    print("Application stopped.")