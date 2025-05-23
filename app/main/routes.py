from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os
from app.file_service import FileService
import traceback
from app.database import Database
import json
import mysql.connector
from mysql.connector import errorcode
import io
import base64
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgb
import random

ALLOWED_EXTENSIONS = {'eu4'}

main_bp = Blueprint('main', __name__)

@main_bp.route('/file/<string:checksum>')
@login_required
def file_details(checksum):
    """Show details of a processed file"""
    db = Database()
    
    # Get basic file info from database
    file_data = db.get_file_by_checksum(checksum, current_user.id)
    
    if not file_data:
        flash('File not found or you don\'t have permission to view it', 'danger')
        return redirect(url_for('main.index'))

    plot_url = None
    try:
        # Get all country data from database
        countries = []
        annual_income_data = {}  # For storing plot data
        
        # First get all unique country tags for this file
        conn = db._get_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute("""
                SELECT DISTINCT country_tag 
                FROM current_state 
                WHERE file_checksum = %s
            """, (checksum,))
            country_tags = [row['country_tag'] for row in cursor.fetchall()]
            
            # Get data for each country
            for tag in country_tags:
                country = {
                    'country_tag': tag,
                    'current_state': db.get_current_state(checksum, tag),
                    'annual_income': db.get_annual_income(checksum, tag),
                    'historical_events': db.get_historical_events(checksum, tag)
                }
                countries.append(country)
                
                # Store annual income data for plotting
                if country['annual_income']:
                    annual_income_data[tag] = {
                        'annual_income': country['annual_income']
                    }

        finally:
            cursor.close()
            conn.close()
            
        # Generate plot if we have annual income data
        if annual_income_data:
            plt.figure(figsize=(10, 6))
            for country_tag, data in annual_income_data.items():
                try:
                    # Ensure we have valid data to plot
                    if not data['annual_income']:
                        continue
                        
                    years = []
                    incomes = []
                    for income in data['annual_income']:
                        try:
                            year = int(income['year']) if 'year' in income else None
                            income_val = float(income['income']) if 'income' in income else None
                            if year is not None and income_val is not None:
                                years.append(year)
                                incomes.append(income_val)
                        except (ValueError, TypeError):
                            continue
                    
                    if years and incomes:
                        color = get_country_color(country_tag)
                        plt.plot(years, incomes, label=country_tag, color=(color[0]/255, color[1]/255, color[2]/255))
                
                except Exception as e:
                    current_app.logger.error(f"Error plotting data for {country_tag}: {str(e)}")
                    continue
            
            if plt.gca().has_data():  # Only save if we actually plotted something
                plt.xlabel('Year')
                plt.ylabel('Income')
                plt.title('Annual Income by Country')
                plt.legend()
                plt.grid(True)
                
                buf = io.BytesIO()
                plt.savefig(buf, format='png', bbox_inches='tight')
                buf.seek(0)
                plot_url = base64.b64encode(buf.getvalue()).decode('utf8')
                plt.close()
            else:
                plot_url = None

        # Preserve the JSON file by writing the data we just fetched
        try:
            json_data = {
                'file_checksum': checksum,
                'original_filename': file_data['original_filename'],
                'processed_data': countries,
                'timestamp': file_data.get('processed_at', '')
            }
            
            with open(file_data['json_path'], 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2)
        except Exception as e:
            current_app.logger.error(f"Failed to update JSON file: {str(e)}")
            # Continue even if JSON update fails
            
        # Ensure timestamp exists for template
        if 'processed_at' in file_data and 'timestamp' not in file_data:
            file_data['timestamp'] = file_data['processed_at']
            
    except Exception as e:
        flash(f'Error loading file data: {str(e)}', 'danger')
        return redirect(url_for('main.index'))
    
    return render_template('main/file_details.html',
                         file_data=file_data,
                         countries=countries,
                         plot_url=plot_url)

@main_bp.route('/')
@login_required
def index():
    db = Database()
    files = db.get_user_files(current_user.id)
    shared_files = db.get_shared_files(current_user.id)
    
    # Ensure each file has a timestamp field
    for file in files:
        if 'processed_at' in file and 'timestamp' not in file:
            file['timestamp'] = file['processed_at']
    
    for file in shared_files:
        if 'processed_at' in file and 'timestamp' not in file:
            file['timestamp'] = file['processed_at']
    
    return render_template('main/index.html', files=files, shared_files=shared_files)

@main_bp.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        flash('No file selected', 'danger')
        return redirect(url_for('main.index'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'danger')
        return redirect(url_for('main.index'))
    
    if not ('.' in file.filename and file.filename.rsplit('.', 1)[1].lower() == 'eu4'):
        flash('Only .eu4 save files are allowed!', 'danger')
        return redirect(url_for('main.index'))

    if file:
        try:
            # Save to temp location
            temp_dir = os.path.join(current_app.instance_path, 'temp')
            os.makedirs(temp_dir, exist_ok=True)
            filename = secure_filename(file.filename)
            temp_path = os.path.join(temp_dir, filename)
            file.save(temp_path)
            
            # Process file
            result = FileService.process_file(temp_path, current_user.id)
            
            # Check if user wants to share with friends
            share_with_friends = request.form.get('share_with_friends') == 'on'
            if share_with_friends:
                db = Database()
                file_data = db.get_file_by_checksum(result['checksum'], current_user.id)
                if file_data:
                    db.share_file_with_all_friends(file_data['id'], current_user.id)
            
            # Clean up
            os.remove(temp_path)
            
            flash('File processed successfully!', 'success')
            return redirect(url_for('main.file_details', checksum=result['checksum']))
        
        except Exception as e:
            flash(f'{str(e)}', 'danger')
            return redirect(url_for('main.index'))
        
@main_bp.route('/share_file/<string:checksum>', methods=['POST'])
@login_required
def share_file(checksum):
    """Share a file with another user"""
    db = Database()
    
    # 1. Verify the file exists and belongs to current user
    file_data = db.get_file_by_checksum(checksum, current_user.id)
    if not file_data:
        flash('File not found or you don\'t have permission to share it', 'danger')
        return redirect(url_for('main.index'))
    
    # 2. Get friend username from form
    friend_username = request.form.get('friend_username')
    if not friend_username:
        flash('Please enter a username to share with', 'danger')
        return redirect(url_for('main.file_details', checksum=checksum))
    
    # 3. Look up friend user
    friend = db.get_user_by_username(friend_username)
    if not friend:
        flash('User not found', 'danger')
        return redirect(url_for('main.file_details', checksum=checksum))
    
    # 4. Check if trying to share with self
    if friend['id'] == current_user.id:
        flash('You cannot share a file with yourself', 'danger')
        return redirect(url_for('main.file_details', checksum=checksum))
    
    try:
        # 5. Share the file
        db.share_file(file_data['id'], friend['id'])
        flash(f'File successfully shared with {friend_username}!', 'success')
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_DUP_ENTRY:
            flash(f'This file is already shared with {friend_username}', 'warning')
        else:
            flash(f'Error sharing file: {str(err)}', 'danger')
    except Exception as e:
        flash(f'Error sharing file: {str(e)}', 'danger')
    
    return redirect(url_for('main.file_details', checksum=checksum))

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

@main_bp.route('/delete_file/<string:checksum>', methods=['POST'])
@login_required
def delete_file(checksum):
    """Delete a file and all its associated data"""
    db = Database()

    try:
        # Get file info to verify ownership
        file_data = db.get_file_by_checksum(checksum, current_user.id)

        if not file_data or file_data['user_id'] != current_user.id:
            flash('File not found or you don\'t have permission to delete it', 'danger')
            return redirect(url_for('main.index'))

        # Attempt to delete the file
        success = db.delete_file(file_data['id'], current_user.id)

        # Also delete the local JSON file, if it exists
        try:
            if success and os.path.exists(file_data['json_path']):
                os.remove(file_data['json_path'])
        except Exception as e:
            current_app.logger.error(f"Error deleting JSON file: {str(e)}")

        if success:
            flash('File deleted successfully', 'success')
        else:
            flash('Failed to delete file', 'danger')

    except Exception as e:
        flash(f'Error deleting file: {str(e)}', 'danger')
        current_app.logger.error(f"Error deleting file {checksum}: {str(e)}")

    return redirect(url_for('main.index'))

@main_bp.route('/test-console')
def test_console():
    """Route to test console output"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Console Test</title>
        <script>
            console.log("This should appear in console");
            document.addEventListener('DOMContentLoaded', function() {
                console.log("DOMContentLoaded fired");
            });
        </script>
    </head>
    <body>
        <h1>Check your browser console</h1>
    </body>
    </html>
    """