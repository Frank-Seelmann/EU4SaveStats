from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.utils import get_db_connection

friends_bp = Blueprint('friends', __name__, template_folder='templates')

@friends_bp.route('/friends')
@login_required
def friends():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get friend requests
    cursor.execute('''
        SELECT u.id, u.username, uf.status 
        FROM user_friends uf
        JOIN users u ON uf.user_id = u.id
        WHERE uf.friend_id = %s AND uf.status = 'pending'
    ''', (current_user.id,))
    pending_requests = cursor.fetchall()
    
    # Get friends
    cursor.execute('''
        SELECT u.id, u.username 
        FROM user_friends uf
        JOIN users u ON (
            (uf.user_id = u.id AND uf.friend_id = %s) OR 
            (uf.friend_id = u.id AND uf.user_id = %s)
        )
        WHERE uf.status = 'accepted'
    ''', (current_user.id, current_user.id))
    friends = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('friends/friends.html', 
                         pending_requests=pending_requests, 
                         friends=friends)

@friends_bp.route('/add_friend', methods=['POST'])
@login_required
def add_friend():
    friend_username = request.form['friend_username']
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Check if user exists
    cursor.execute('SELECT id FROM users WHERE username = %s', (friend_username,))
    friend = cursor.fetchone()
    
    if not friend:
        flash('User not found', 'danger')
        return redirect(url_for('friends.friends'))
    
    friend_id = friend['id']
    
    # Check if already friends or request exists
    cursor.execute('''
        SELECT * FROM user_friends 
        WHERE (user_id = %s AND friend_id = %s) OR (user_id = %s AND friend_id = %s)
    ''', (current_user.id, friend_id, friend_id, current_user.id))
    existing = cursor.fetchone()
    
    if existing:
        flash('Friend request already exists or you are already friends', 'warning')
    else:
        cursor.execute('''
            INSERT INTO user_friends (user_id, friend_id, status) 
            VALUES (%s, %s, 'pending')
        ''', (current_user.id, friend_id))
        conn.commit()
        flash('Friend request sent', 'success')
    
    cursor.close()
    conn.close()
    return redirect(url_for('friends.friends'))

@friends_bp.route('/accept_friend/<int:friend_id>')
@login_required
def accept_friend(friend_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE user_friends 
        SET status = 'accepted' 
        WHERE user_id = %s AND friend_id = %s
    ''', (friend_id, current_user.id))
    conn.commit()
    
    cursor.close()
    conn.close()
    flash('Friend request accepted', 'success')
    return redirect(url_for('friends.friends'))