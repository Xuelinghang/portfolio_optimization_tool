# app/routes/auth.py

from flask import Blueprint, request, jsonify, redirect, url_for, render_template, flash
from sqlalchemy import or_
from app import db, bcrypt
from app.models import User
from flask_login import login_user, logout_user, current_user, login_required

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/")
def index():
    if current_user.is_authenticated:
        # --- Modified: send admins straight to the Admin Dashboard ---
        if getattr(current_user, "is_admin", False):
            return redirect(url_for("admin_bp.admin_dashboard"))
        # --- Normal users stay on the homepage ---
        return render_template("index.html", username=current_user.username)
    # If not logged in, send to the login page
    return redirect(url_for("auth.login_page"))


@auth_bp.route("/login-page")
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for("auth.index"))
    return render_template("login.html")


@auth_bp.route("/register-page")
def register_page():
    if current_user.is_authenticated:
        return redirect(url_for("auth.index"))
    return render_template("register.html")


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    if not username or not email or not password:
        return jsonify({"error": "Username, email, and password are required"}), 400

    if User.query.filter(or_(User.username == username, User.email == email)).first():
        return jsonify({"error": "Username or email already exists"}), 400

    # Hash the password as before
    hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")
    new_user = User(username=username, email=email, password_hash=hashed_password)

    # --- Modified: auto-flag admins by checking email domain ---
    domain = email.split("@")[-1].lower()
    new_user.is_admin = (domain == "portfoliooptimizer.com")

    db.session.add(new_user)
    try:
        db.session.commit()

        # --- Modified: immediately log in the new user ---
        login_user(new_user)

        # --- Modified: choose post-registration redirect by role ---
        if new_user.is_admin:
            redirect_url = url_for("admin_bp.admin_dashboard")
        else:
            redirect_url = url_for("auth.index")

        return jsonify({
            "message": "User registered and logged in successfully",
            "redirect_url": redirect_url
        }), 201

    except Exception as e:
        db.session.rollback()
        print(f"Error during user registration: {e}")
        return jsonify({"error": "An error occurred during registration"}), 500


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    login_identifier = data.get("username")
    password = data.get("password")

    if not login_identifier or not password:
        return jsonify({"error": "Username (or email) and password are required"}), 400

    user = User.query.filter(or_(
        User.username == login_identifier,
        User.email    == login_identifier
    )).first()

    if user and bcrypt.check_password_hash(user.password_hash, password):
        # Log in via Flask-Login
        login_user(user)
        print(f"User {user.username} logged in successfully.")

        # --- Modified: send admins to Admin Dashboard, others to portfolio ---
        if getattr(user, "is_admin", False):
            redirect_url = url_for("admin_bp.admin_dashboard")
        else:
            redirect_url = url_for("auth.index")

        return jsonify({
            "message": "Login successful",
            "redirect_url": redirect_url
        }), 200

    print(f"Failed login attempt for identifier: {login_identifier}")
    return jsonify({"error": "Invalid username/email or password"}), 401


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    print("User logged out successfully.")
    return jsonify({"message": "Logged out successfully"}), 200
