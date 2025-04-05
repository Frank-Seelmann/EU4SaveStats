from flask import Blueprint, render_template

friends_bp = Blueprint('friends', __name__, template_folder='templates')

@friends_bp.route('/friends')
def friends():
    return render_template('friends/friends.html')