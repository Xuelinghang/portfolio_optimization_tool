# app/routes/admin.py

import os
import json
import traceback
import string
import random
from functools import wraps # Import wraps

from flask import Blueprint, render_template, redirect, url_for, flash, jsonify, request
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash

from app import db
from app.models import User, Transaction

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# Helper decorator to restrict access to admin users
def admin_required(f):
    @wraps(f) # Use functools.wraps to preserve original function metadata
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for("main.index"))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route("/")
@admin_required
def admin_dashboard():
    total_users = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()
    disabled_users = total_users - active_users
    system_transactions_count = Transaction.query.filter_by(is_system=True).count()
    total_transactions = Transaction.query.count()

    return render_template("admin/dashboard.html",
                           total_users=total_users,
                           active_users=active_users,
                           disabled_users=disabled_users,
                           system_transactions_count=system_transactions_count,
                           total_transactions=total_transactions)

@admin_bp.route("/users")
@admin_required
def manage_users():
    users = User.query.all()
    return render_template("admin/users.html", users=users)

@admin_bp.route("/users/<int:user_id>/toggle_status", methods=["POST"])
@admin_required
def toggle_user_status(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin and user.id == current_user.id:
         flash("You cannot disable your own admin account.", "warning")
    else:
        user.is_active = not user.is_active
        db.session.commit()
        flash(f"User '{user.username}' account status toggled.", "success")
    return redirect(url_for("admin.manage_users"))

@admin_bp.route("/users/<int:user_id>/reset_password", methods=["POST"])
@admin_required
def reset_user_password(user_id):
    user = User.query.get_or_404(user_id)

    temp_password = ''.join(random.choices(string.ascii_letters + string.digits + string.punctuation, k=12))

    user.set_password(temp_password)
    user.password_reset_required = True
    db.session.commit()

    flash(f"Password for user '{user.username}' reset to: {temp_password}. They will be required to change it on next login.", "warning")

    return redirect(url_for("admin.manage_users"))

@admin_bp.route("/transactions/system")
@admin_required
def view_system_transactions():
    system_transactions = Transaction.query.filter_by(is_system=True).all()
    return render_template("admin/system_transactions.html", transactions=system_transactions)
