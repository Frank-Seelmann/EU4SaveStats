from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.database import Database
from datetime import datetime

forum_bp = Blueprint('forum', __name__)

@forum_bp.route('/forum')
@login_required
def forum():
    db = Database()
    topics = db.get_all_topics()
    return render_template('forum/forum.html', topics=topics)

@forum_bp.route('/forum/create_topic', methods=['GET', 'POST'])
@login_required
def create_topic():
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        
        if not title or not content:
            flash('Title and content are required', 'danger')
            return redirect(url_for('forum.create_topic'))
        
        db = Database()
        db.create_topic(title, content, current_user.id)
        flash('Topic created successfully!', 'success')
        return redirect(url_for('forum.forum'))
    
    return render_template('forum/create_topic.html')

@forum_bp.route('/forum/topic/<int:topic_id>')
@login_required
def view_topic(topic_id):
    db = Database()
    topic = db.get_topic_by_id(topic_id)
    posts = db.get_posts_for_topic(topic_id)
    return render_template('forum/topic.html', topic=topic, posts=posts)

@forum_bp.route('/forum/topic/<int:topic_id>/add_post', methods=['POST'])
@login_required
def add_post(topic_id):
    content = request.form.get('content')
    if not content:
        flash('Post content cannot be empty', 'danger')
        return redirect(url_for('forum.view_topic', topic_id=topic_id))
    
    db = Database()
    db.add_post(content, current_user.id, topic_id)
    flash('Post added successfully!', 'success')
    return redirect(url_for('forum.view_topic', topic_id=topic_id))

@forum_bp.route('/forum/topic/<int:topic_id>/delete', methods=['POST'])
@login_required
def delete_topic(topic_id):
    db = Database()
    success = db.delete_topic(topic_id, current_user.id)

    if success:
        flash('Topic deleted successfully', 'success')
    else:
        flash('You can only delete topics you created', 'danger')

    return redirect(url_for('forum.forum'))

@forum_bp.route('/forum/post/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id):
    db = Database()

    # First get the topic_id for redirection
    topic = db.get_post_topic(post_id)
    if not topic:
        flash('Post not found', 'danger')
        return redirect(url_for('forum.forum'))

    success = db.delete_post(post_id, current_user.id)

    if success:
        flash('Post deleted successfully', 'success')
    else:
        flash('You can only delete posts you created', 'danger')

    return redirect(url_for('forum.view_topic', topic_id=topic['topic_id']))