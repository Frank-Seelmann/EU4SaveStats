from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from app.utils import get_db_connection, get_country_color
import matplotlib.pyplot as plt
import io
import base64
from werkzeug.utils import secure_filename
import os
import hashlib
from datetime import datetime
import subprocess

main_bp = Blueprint('main', __name__, template_folder='templates')
basedir = os.path.abspath(os.path.dirname(__file__))

@main_bp.route('/')
@login_required
def index():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get files where user is owner or has shared access
    cursor.execute('''
        SELECT uf.id, uf.file_name, uf.upload_time
        FROM uploaded_files uf
        JOIN user_file_permissions ufp ON uf.id = ufp.file_id
        WHERE ufp.user_id = %s
        ORDER BY uf.upload_time DESC
    ''', (current_user.id,))
    
    files = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return render_template('main/index.html', files=files)

def allowed_file(filename):
    """Check if the file has an allowed extension"""
    ALLOWED_EXTENSIONS = {'eu4', 'zip'}  # Add other allowed extensions if needed
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
    
    if file and allowed_file(file.filename):
        conn = None
        cursor = None
        existing_file = None  # Initialize variable here
        temp_path = None
        
        try:
            filename = secure_filename(file.filename)
            file_content = file.read()
            file_checksum = hashlib.sha256(file_content).hexdigest()
            
            # Create temp directory if it doesn't exist
            temp_dir = os.path.join(current_app.instance_path, 'temp')
            os.makedirs(temp_dir, exist_ok=True)
            
            # Save file with full path
            temp_path = os.path.join(temp_dir, filename)
            with open(temp_path, 'wb') as f:
                f.write(file_content)
            
            # Verify file was written
            if not os.path.exists(temp_path):
                raise Exception(f"Failed to create temp file at {temp_path}")
            
            current_app.logger.debug(f"Temp file created at {temp_path}")
            
            # Database operations
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            # Check if file already exists
            cursor.execute('SELECT id FROM uploaded_files WHERE file_checksum = %s', (file_checksum,))
            existing_file = cursor.fetchone()
            
            if existing_file:
                # File exists, just add permission if not already exists
                cursor.execute('''
                    INSERT IGNORE INTO user_file_permissions
                    (file_id, user_id, permission_type)
                    VALUES (%s, %s, 'owner')
                ''', (existing_file['id'], current_user.id))
                file_id = existing_file['id']
            else:
                # New file - insert metadata
                cursor.execute('''
                    INSERT INTO uploaded_files 
                    (file_name, file_checksum) 
                    VALUES (%s, %s)
                ''', (filename, file_checksum))
                file_id = cursor.lastrowid
                
                # Add owner permission
                cursor.execute('''
                    INSERT INTO user_file_permissions
                    (file_id, user_id, permission_type)
                    VALUES (%s, %s, 'owner')
                ''', (file_id, current_user.id))
            
            conn.commit()
            
            # Process file with Rust backend (only if new file)
            if not existing_file:
                try:
                    abs_path = os.path.abspath(temp_path)
                    current_app.logger.debug(f"Processing file at {abs_path}")
                    
                    # DEBUG: Verify file exists before processing
                    if not os.path.exists(abs_path):
                        raise Exception(f"Temp file missing at {abs_path} before processing")
                    
                    # Add delay for debugging
                    import time
                    time.sleep(2)  # Give time to verify file exists
                    
                    result = subprocess.run(
                        ['./eu4_parser', '--local', abs_path, str(current_user.id)],
                        capture_output=True,
                        text=True
                    )

                    for line in result.stdout.splitlines():
                        current_app.logger.debug(f"[RUST] {line}")
                    
                    if result.returncode != 0:
                        raise Exception(f"Processing failed: {result.stderr}")
                    if result.stderr:
                        for line in result.stderr.splitlines():
                            current_app.logger.error(f"[RUST-ERR] {line}")
                    
                    # DEBUG: Keep file for inspection if in development
                    if current_app.config['ENV'] == 'development':
                        debug_path = os.path.join(temp_dir, f"debug_{filename}")
                        os.rename(temp_path, debug_path)
                        current_app.logger.debug(f"Saved debug file at {debug_path}")
                except Exception as e:
                    if conn and cursor and 'file_id' in locals():
                        try:
                            # First delete permissions, then the file entry
                            cursor.execute('DELETE FROM user_file_permissions WHERE file_id = %s', (file_id,))
                            cursor.execute('DELETE FROM uploaded_files WHERE id = %s', (file_id,))
                            conn.commit()
                        except Exception as db_error:
                            conn.rollback()
                            current_app.logger.error(f"Cleanup failed: {str(db_error)}")
                    raise
                finally:
                    # Only clean up if not in debug mode
                    if not current_app.config.get('DEBUG', False) and temp_path and os.path.exists(temp_path):
                        os.remove(temp_path)
            
            flash('File uploaded successfully!', 'success')
            return redirect(url_for('main.index'))
            
        except Exception as e:
            if conn:
                conn.rollback()
            current_app.logger.error(f"Upload failed: {str(e)}")
            flash(f'File processing failed: {str(e)}', 'error')
            return redirect(url_for('main.index'))
            
        finally:
            # Clean up resources
            if cursor:
                cursor.close()
            if conn:
                conn.close()
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception as e:
                    current_app.logger.error(f"Failed to remove temp file: {str(e)}")
    
    flash('Allowed file types are: .eu4, .zip', 'error')
    return redirect(url_for('main.index'))

@main_bp.route('/file/<int:file_id>')
@login_required
def file_details(file_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)

        current_app.logger.debug(f"Requesting file_id: {file_id}")
        
        # Check if user has permission to view this file and get owner info
        cursor.execute('''
            SELECT uf.*, 
                (SELECT user_id FROM user_file_permissions 
                    WHERE file_id = uf.id AND permission_type = 'owner' LIMIT 1) as owner_id
            FROM uploaded_files uf
            JOIN user_file_permissions ufp ON uf.id = ufp.file_id
            WHERE uf.id = %s AND ufp.user_id = %s
        ''', (file_id, current_user.id))
        
        file_info = cursor.fetchone()
        
        if not file_info:
            flash('You do not have permission to view this file', 'danger')
            return redirect(url_for('main.index'))
        
        current_app.logger.debug(f"File checksum: {file_info['file_checksum']}")

        cursor.execute('SELECT * FROM uploaded_files WHERE id = %s', (file_id,))

        # Fetch current state data
        cursor.execute('''
            SELECT country_tag, date, income, manpower, max_manpower, trade_income 
            FROM current_state 
            WHERE file_checksum = %s
        ''', (file_info['file_checksum'],))
        current_states = cursor.fetchall()
        current_app.logger.debug(f"Found {len(current_states)} current states")
        
        # Fetch annual income data
        cursor.execute('''
            SELECT country_tag, year, income 
            FROM annual_income 
            WHERE file_checksum = %s
        ''', (file_info['file_checksum'],))
        annual_incomes = cursor.fetchall()
        current_app.logger.debug(f"Found {len(annual_incomes)} annual income records")
        
        # Fetch historical events
        cursor.execute('''
            SELECT country_tag, date, event_type, details 
            FROM historical_events 
            WHERE file_checksum = %s
        ''', (file_info['file_checksum'],))
        historical_events = cursor.fetchall()
        current_app.logger.debug(f"Found {len(historical_events)} historical events")
        
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
            plt.plot(years, incomes, label=country_tag, 
                    color=(color[0]/255, color[1]/255, color[2]/255))
        
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
        
        return render_template('main/file_details.html', 
                            file_info=file_info, 
                            countries_data=countries_data, 
                            plot_url=plot_url)
    
    except Exception as e:
        current_app.logger.error(f"Error in file_details: {str(e)}")
        flash('An error occurred while loading the file details', 'error')
        return redirect(url_for('main.index'))
        
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@main_bp.route('/share_file/<int:file_id>', methods=['POST'])
@login_required
def share_file(file_id):
    friend_username = request.form['friend_username']
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Verify the current user owns the file
    cursor.execute('''
        SELECT 1 FROM user_file_permissions 
        WHERE file_id = %s AND user_id = %s AND permission_type = 'owner'
    ''', (file_id, current_user.id))
    owns_file = cursor.fetchone()
    
    if not owns_file:
        flash('You do not own this file', 'danger')
        return redirect(url_for('main.file_details', file_id=file_id))
    
    # Check if friend exists
    cursor.execute('SELECT id FROM users WHERE username = %s', (friend_username,))
    friend = cursor.fetchone()
    
    if not friend:
        flash('User not found', 'danger')
        return redirect(url_for('main.file_details', file_id=file_id))
    
    friend_id = friend['id']
    
    # Check if already shared
    cursor.execute('''
        SELECT 1 FROM user_file_permissions 
        WHERE file_id = %s AND user_id = %s
    ''', (file_id, friend_id))
    already_shared = cursor.fetchone()
    
    if already_shared:
        flash('File is already shared with this user', 'warning')
    else:
        cursor.execute('''
            INSERT INTO user_file_permissions (file_id, user_id, permission_type) 
            VALUES (%s, %s, 'shared')
        ''', (file_id, friend_id))
        conn.commit()
        flash('File shared successfully', 'success')
    
    cursor.close()
    conn.close()
    return redirect(url_for('main.file_details', file_id=file_id))