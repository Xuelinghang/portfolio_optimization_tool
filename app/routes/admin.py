from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.models import User, Transaction
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
import random
import string

# Initialize Blueprint
admin_bp = Blueprint('admin_bp', __name__)

def generate_random_password():
    """Generates a random password."""
    length = 12
    characters = string.ascii_letters + string.digits + string.punctuation
    return ''.join(random.choice(characters) for i in range(length))

@admin_bp.route('/admin', methods=['GET', 'POST'])
@login_required  # Ensure that only logged-in users with admin privileges can access this
def admin_dashboard():
    if not current_user.is_admin:
        flash('You are not authorized to view this page.', 'danger')
        return redirect(url_for('portfolio.home'))  # Redirect to home if not admin
    
    # Get all users for admin to manage
    users = User.query.all()
    transactions = Transaction.query.all()  # Get all system transactions (for analysis)

    if request.method == 'POST':
        action = request.form.get('action')  # Determine the action (e.g., disable user, reset password)
        user_id = request.form.get('user_id')  # Get the user_id from the form
        user = User.query.get(user_id)

        if not user:
            flash('User not found!', 'danger')
            return redirect(url_for('admin_bp.admin_dashboard'))

        if action == 'disable':
            user.is_active = False  # Disable user account
            db.session.commit()
            flash(f'User {user.username} has been disabled.', 'success')
            return redirect(url_for('admin_bp.admin_dashboard'))  # Redirect after action
        
        elif action == 'reset_password':
            new_password = generate_random_password()  # Generate a random password
            user.set_password(new_password)  # Hash and save the password
            db.session.commit()
            flash(f'Password for {user.username} has been reset. New password: {new_password}', 'success')
            return redirect(url_for('admin_bp.admin_dashboard'))  # Redirect after action

    return render_template('admin.html', users=users, transactions=transactions)
