from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template
from app import db, bcrypt
from app.models import User, Portfolio
from sqlalchemy import or_
import json

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/")
def index():
    if "user_id" in session:
        return render_template("index.html", username=session.get("username"))
    else:
        return redirect(url_for("auth.login_page"))

@auth_bp.route("/login-page")
def login_page():
    return render_template("login.html")

@auth_bp.route("/register-page")
def register_page():
    return render_template("register.html")

@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()
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
    db.session.commit()

    return jsonify({"message": "User registered successfully"}), 201

@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    login_identifier = data.get("username")
    password = data.get("password")
    if not login_identifier or not password:
        return jsonify({"error": "Username (or email) and password are required"}), 400

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
        portfolio_id = request.args.get("portfolio_id")
        portfolio = None
        if portfolio_id:
            portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=session["user_id"]).first()
        return render_template("data-entry.html", username=session.get("username"), portfolio=portfolio)
    else:
        return redirect(url_for("auth.login_page"))

@auth_bp.route("/saved-portfolios")
def saved_portfolios():
    if "user_id" not in session:
        return redirect(url_for("auth.login_page"))

    user_id = session["user_id"]
    portfolios = Portfolio.query.filter_by(user_id=user_id).order_by(Portfolio.purchase_date.desc()).all()

    portfolios_data = []
    for p in portfolios:
        try:
            portfolio_entries = json.loads(p.portfolio_data) if p.portfolio_data else []
        except Exception as e:
            print(f"Error parsing portfolio data for portfolio {p.id}: {e}")
            portfolio_entries = []
        valid_entries = [entry for entry in portfolio_entries if entry.get("ticker")]
        portfolios_data.append({
            "id": p.id,
            "portfolio_name": p.portfolio_name,
            "num_assets": len(valid_entries),
            "created_at": p.purchase_date
        })

    return render_template("saved-portfolios.html", username=session.get("username"), portfolios=portfolios_data)

@auth_bp.route("/save-portfolio", methods=["POST"])
def save_portfolio():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json() or {}
    portfolio_name = data.get("portfolioName")
    portfolio_data = data.get("portfolioData")
    if not portfolio_name or portfolio_data is None:
        return jsonify({"error": "Portfolio name and data are required"}), 400

    if not isinstance(portfolio_data, str):
        portfolio_data = json.dumps(portfolio_data)

    new_portfolio = Portfolio(
        user_id=session["user_id"],
        portfolio_name=portfolio_name,
        portfolio_data=portfolio_data
    )
    db.session.add(new_portfolio)
    db.session.commit()

    return jsonify({"message": "Portfolio saved successfully"}), 201

@auth_bp.route("/update-portfolio/<int:portfolio_id>", methods=["POST"])
def update_portfolio(portfolio_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    new_name = data.get("portfolioName")
    new_data = data.get("portfolioData")

    if not new_name or new_data is None:
        return jsonify({"error": "Missing portfolio name or data"}), 400

    portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=session["user_id"]).first()
    if not portfolio:
        return jsonify({"error": "Portfolio not found"}), 404

    portfolio.portfolio_name = new_name
    portfolio.portfolio_data = json.dumps(new_data)
    db.session.commit()

    return jsonify({"message": "Portfolio updated successfully"}), 200

@auth_bp.route("/portfolio/delete/<int:portfolio_id>", methods=["POST"])
def delete_portfolio(portfolio_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 403

    portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=session["user_id"]).first()
    if not portfolio:
        return jsonify({"error": "Portfolio not found"}), 404

    db.session.delete(portfolio)
    db.session.commit()
    return jsonify({"message": "Portfolio deleted successfully"}), 200