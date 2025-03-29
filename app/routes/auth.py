from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template
from app import db, bcrypt
from app.models import User
from sqlalchemy import or_

auth_bp = Blueprint("auth", __name__, template_folder="templates", static_folder="static")

@auth_bp.route("/")
def index():
    """
    Landing page. If the user is logged in, render the index template;
    otherwise, redirect to the login page.
    """
    if "user_id" in session:
        return render_template("index.html", username=session.get("username"))
    else:
        # Use the endpoint name "auth.login_page" since the blueprint is named "auth"
        return redirect(url_for("auth.login_page"))

@auth_bp.route("/login-page")
def login_page():
    """
    Serve the login page.
    Ensure that 'login.html' exists in the static folder of this blueprint.
    """
    return auth_bp.send_static_file("login.html")

@auth_bp.route("/register-page")
def register_page():
    """
    Serve the registration page.
    Ensure that 'register.html' exists in the static folder of this blueprint.
    """
    return auth_bp.send_static_file("register.html")

@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")
    
    if not username or not email or not password:
        return jsonify({"error": "Username, email, and password are required"}), 400
    
    # Check if a user with the same username or email already exists
    if User.query.filter(or_(User.username == username, User.email == email)).first():
        return jsonify({"error": "Username or email already exists"}), 400

    hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")
    new_user = User(username=username, email=email, password_hash=hashed_password)
    db.session.add(new_user)
    db.session.commit()
    
    return jsonify({"message": "User registered successfully"}), 201

@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    login_identifier = data.get("username")
    password = data.get("password")
    if not login_identifier or not password:
        return jsonify({"error": "Username (or email) and password are required"}), 400
    
    # Query by username or email
    user = User.query.filter(or_(User.username == login_identifier, User.email == login_identifier)).first()
    if user and bcrypt.check_password_hash(user.password_hash, password):
        session["user_id"] = user.id
        session["username"] = user.username
        return jsonify({"message": "Login successful", "user": user.username}), 200
    else:
        return jsonify({"error": "Invalid username/email or password"}), 401

@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out successfully"}), 200

@auth_bp.route("/data-entry")
def data_entry():
    if "user_id" in session:
        return render_template("data-entry.html", username=session.get("username"))
    else:
        return redirect(url_for("auth.login_page"))

@auth_bp.route("/saved-portfolios")
def saved_portfolios():
    if "user_id" not in session:
        return redirect(url_for("auth.login_page"))
    
    from app.models import Portfolio  # Import here to avoid circular dependency
    user_id = session["user_id"]
    portfolios = Portfolio.query.filter_by(user_id=user_id).order_by(Portfolio.purchase_date.desc()).all()
    
    # Prepare data for rendering; adjust as needed
    portfolios_data = []
    for p in portfolios:
        portfolios_data.append({
            "id": p.id,
            "portfolio_name": f"Portfolio {p.id}",
            "num_assets": 1,  # Adjust if you track multiple assets per portfolio
            "created_at": p.purchase_date
        })
    
    return render_template("saved-portfolios.html", username=session.get("username"), portfolios=portfolios_data)
