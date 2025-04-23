# app/routes/auth.py

from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template, flash
from sqlalchemy import or_
from app import db, bcrypt
from app.models import User
from flask_login import login_user, logout_user, current_user, login_required 

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/")
def index():
    # Check if the current_user is authenticated (logged in) using Flask-Login
    if current_user.is_authenticated:
        # Access username via current_user if authenticated
        return render_template("index.html", username=current_user.username)
    # If not authenticated, redirect to the login page
    return redirect(url_for("auth.login_page"))

@auth_bp.route("/login-page")
def login_page():
    # If the user is already authenticated, redirect them away from the login page
    if current_user.is_authenticated: 
        return redirect(url_for("auth.index")) # Redirect to a logged-in page

    return render_template("login.html")

@auth_bp.route("/register-page")
def register_page():
    # If the user is already authenticated, redirect them away from the registration page
    if current_user.is_authenticated:
        return redirect(url_for("auth.index")) # Redirect to a logged-in page

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

    hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")
    new_user = User(username=username, email=email, password_hash=hashed_password)
    db.session.add(new_user)
    try:
        db.session.commit()
        return jsonify({"message": "User registered successfully"}), 201
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

    user = User.query.filter(or_(User.username == login_identifier,
                                 User.email    == login_identifier)).first()

    if user and bcrypt.check_password_hash(user.password_hash, password):
        # --- Use Flask-Login's login_user function ---
        login_user(user)
        print(f"User {user.username} logged in successfully.") # Log successful login

        return jsonify({"message": "Login successful", "user": user.username}), 200 # Return success message and username

    # If user not found or password incorrect
    print(f"Failed login attempt for identifier: {login_identifier}") # Log failed attempt
    return jsonify({"error": "Invalid username/email or password"}), 401

@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    # --- Use Flask-Login's logout_user function ---
    logout_user() # 
    print("User logged out successfully.") # Log successful logout

    # Flask-Login removes the user ID from the session

    return jsonify({"message": "Logged out successfully"}), 200