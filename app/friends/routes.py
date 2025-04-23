from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.database import Database

friends_bp = Blueprint('friends', __name__, template_folder='templates')
db = Database()

@friends_bp.route('/friends')
@login_required  # Use Flask-Login's decorator
def friends():
    return render_template('friends/friends.html',
                         pending_requests=db.get_pending_requests(current_user.id),
                         friends=db.get_friends_list(current_user.id))

@friends_bp.route('/add_friend', methods=['POST'])
@login_required  # Use Flask-Login's decorator
def add_friend():
    friend_username = request.form.get('friend_username')
    
    # Get friend user ID
    friend = db.get_user_by_username(friend_username)
    if not friend:
        flash('User not found')
        return redirect(url_for('friends.friends'))
    
    if friend['id'] == current_user.id:
        flash("You can't add yourself as a friend")
        return redirect(url_for('friends.friends'))
    
    try:
        if db.create_friend_request(current_user.id, friend['id']):
            flash('Friend request sent!')
        else:
            flash('Friend relationship already exists')
    except Exception as e:
        flash('Error sending friend request')
        # Log the error here
    
    return redirect(url_for('friends.friends'))

@friends_bp.route('/accept_friend/<int:friend_id>')
@login_required  # Use Flask-Login's decorator
def accept_friend(friend_id):
    try:
        if db.accept_friend_request(current_user.id, friend_id):
            flash('Friend request accepted!')
        else:
            flash('No pending friend request found')
    except Exception as e:
        flash('Error accepting friend request')
        # Log the error here
    
    return redirect(url_for('friends.friends'))