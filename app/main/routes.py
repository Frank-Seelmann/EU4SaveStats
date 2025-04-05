from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os
from app.file_service import FileService
import traceback
from app.database import Database
import json

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
            
        # Ensure the timestamp field exists
        if 'processed_at' in file_data and 'timestamp' not in file_data:
            file_data['timestamp'] = file_data['processed_at']
            
    except FileNotFoundError:
        flash('Processed data file not found', 'error')
        return redirect(url_for('main.index'))
    except json.JSONDecodeError:
        flash('Invalid data format', 'error')
        return redirect(url_for('main.index'))
    
    return render_template('main/file_details.html',
                         file_data=file_data,
                         data=processed_data)

@main_bp.route('/')
@login_required
def index():
    files = FileService.get_user_files(current_user.id)
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