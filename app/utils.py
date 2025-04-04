import mysql.connector
from app.config import Config
import subprocess
import os
import random

def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host=Config.DB_HOST,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            database=Config.DB_NAME
        )
        return conn
    except mysql.connector.Error as err:
        print(f"Error connecting to database: {err}")
        raise

def initialize_database():
    """Create the database if it doesn't exist and initialize the schema."""
    try:
        # Connect without specifying a database
        conn = mysql.connector.connect(
            host=Config.DB_HOST,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD
        )
        cursor = conn.cursor()

        # Check if the database exists
        cursor.execute(f"SHOW DATABASES LIKE '{Config.DB_NAME}'")
        result = cursor.fetchone()

        if not result:
            # Create the database if it doesn't exist
            cursor.execute(f"CREATE DATABASE {Config.DB_NAME}")
            print(f"Database {Config.DB_NAME} created successfully.")

        cursor.close()
        conn.close()

        # Call the Rust backend to initialize the schema
        result = subprocess.run(
            ['./eu4_parser', '--init-db'],
            capture_output=True,
            text=True,
            check=True
        )
        print("Database schema initialized successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error initializing database schema: {e.stderr}")
    except mysql.connector.Error as err:
        print(f"Error connecting to MySQL: {err}")

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
    return COUNTRY_COLORS.get(country_tag, 
        (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)))