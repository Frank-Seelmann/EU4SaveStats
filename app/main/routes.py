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

main_bp = Blueprint('main', __name__)

@main_bp.route('/file/<string:checksum>')
@login_required
def file_details(checksum):
    """Show details of a processed file"""
    db = Database()
    file_data = db.get_file_by_checksum(checksum, current_user.id)
    
    if not file_data:
        flash('File not found or you don\'t have permission to view it', 'error')
        return redirect(url_for('main.index'))
    
    try:
        with open(file_data['json_path'], 'r', encoding='utf-8') as f:
            processed_data = json.load(f)
            
        # Ensure timestamp exists
        if 'processed_at' in file_data and 'timestamp' not in file_data:
            file_data['timestamp'] = file_data['processed_at']
            
        # Get all country data from database
        countries = []
        country_tags = {c['country_tag'] for c in processed_data.get('processed_data', [])}
        
        for tag in country_tags:
            country = {
                'country_tag': tag,
                'current_state': db.get_current_state(checksum, tag),
                'annual_income': db.get_annual_income(checksum, tag),
                'historical_events': db.get_historical_events(checksum, tag)
            }
            countries.append(country)
            
    except FileNotFoundError:
        flash('Processed data file not found', 'error')
        return redirect(url_for('main.index'))
    except json.JSONDecodeError:
        flash('Invalid data format', 'error')
        return redirect(url_for('main.index'))
    except Exception as e:
        flash(f'Error loading file data: {str(e)}', 'error')
        return redirect(url_for('main.index'))
    
    return render_template('main/file_details.html',
                         file_data=file_data,
                         countries=countries)

@main_bp.route('/')
@login_required
def index():
    db = Database()
    files = db.get_user_files(current_user.id)
    
    # Ensure each file has a timestamp field
    for file in files:
        if 'processed_at' in file and 'timestamp' not in file:
            file['timestamp'] = file['processed_at']
    
    return render_template('main/index.html', files=files)

@main_bp.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('main.index'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'error')
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
            
            # Clean up
            os.remove(temp_path)
            
            flash('File processed successfully!', 'success')
            return redirect(url_for('main.file_details', checksum=result['checksum']))
        
        except Exception as e:
            # Get full traceback as a string
            error_traceback = traceback.format_exc()
            flash(f'Processing failed: {str(e)}\n\nTraceback:\n{error_traceback}', 'error')
            return redirect(url_for('main.index'))
        
@main_bp.route('/share_file/<string:checksum>', methods=['POST'])
@login_required
def share_file(checksum):
    """Share a file with another user"""
    db = Database()
    
    # 1. Verify the file exists and belongs to current user
    file_data = db.get_file_by_checksum(checksum, current_user.id)
    if not file_data:
        flash('File not found or you don\'t have permission to share it', 'error')
        return redirect(url_for('main.index'))
    
    # 2. Get friend username from form
    friend_username = request.form.get('friend_username')
    if not friend_username:
        flash('Please enter a username to share with', 'error')
        return redirect(url_for('main.file_details', checksum=checksum))
    
    # 3. Look up friend user
    friend = db.get_user_by_username(friend_username)
    if not friend:
        flash('User not found', 'error')
        return redirect(url_for('main.file_details', checksum=checksum))
    
    # 4. Check if trying to share with self
    if friend['id'] == current_user.id:
        flash('You cannot share a file with yourself', 'error')
        return redirect(url_for('main.file_details', checksum=checksum))
    
    try:
        # 5. Share the file
        db.share_file(file_data['id'], friend['id'])
        flash(f'File successfully shared with {friend_username}!', 'success')
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_DUP_ENTRY:
            flash(f'This file is already shared with {friend_username}', 'warning')
        else:
            flash(f'Error sharing file: {str(err)}', 'error')
    except Exception as e:
        flash(f'Error sharing file: {str(e)}', 'error')
    
    return redirect(url_for('main.file_details', checksum=checksum))

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