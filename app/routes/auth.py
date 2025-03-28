from flask import Flask, request, jsonify, session, redirect, url_for, render_template
import sqlite3
import bcrypt
import os
import json  # for JSON conversion if needed

app = Flask(__name__, static_folder="static", static_url_path="")

# Set a strong secret key for session management
app.secret_key = "your_super_secret_key"  # Replace with a secure key in production

DB_FILE = "users.db"

def init_db():
    """Initialize the database with users and portfolios tables if they don't exist."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        # Create the users table (if it doesn't exist)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        """)
        # Create the portfolios table (if it doesn't exist)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                portfolio_name TEXT NOT NULL,
                portfolio_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.commit()

def hash_password(password):
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(password, hashed_password):
    """Verify a password against its hashed version."""
    return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))

@app.route("/register", methods=["POST"])
def register():
    """Register a new user with username, email, and hashed password storage."""
    data = request.get_json()
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")
    
    if not username or not email or not password:
        return jsonify({"error": "Username, email, and password are required"}), 400

    hashed_password = hash_password(password)
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                (username, email, hashed_password)
            )
            conn.commit()
        return jsonify({"message": "User registered successfully"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username or email already exists"}), 400

@app.route("/login", methods=["POST"])
def login():
    """Validate user credentials (username or email) and set a session."""
    data = request.get_json()
    login_identifier = data.get("username")
    password = data.get("password")
    if not login_identifier or not password:
        return jsonify({"error": "Username (or email) and password are required"}), 400

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, password_hash, username FROM users WHERE username = ? OR email = ?",
            (login_identifier, login_identifier)
        )
        result = cursor.fetchone()

    if result and verify_password(password, result[1]):
        session["user_id"] = result[0]
        session["username"] = result[2]
        return jsonify({"message": "Login successful", "user": result[2]}), 200
    else:
        return jsonify({"error": "Invalid username/email or password"}), 401

@app.route("/logout", methods=["POST"])
def logout():
    """Clear the session on logout."""
    session.clear()
    return jsonify({"message": "Logged out successfully"}), 200

@app.route("/")
def index():
    if "user_id" in session:
        return render_template("index.html", username=session["username"])
    else:
        return redirect(url_for("login_page"))

@app.route("/login-page")
def login_page():
    """Serve the login page."""
    return app.send_static_file("login.html")

@app.route("/register-page")
def register_page():
    """Serve the register page."""
    return app.send_static_file("register.html")

@app.route("/data-entry")
def data_entry():
    if "user_id" in session:
        return render_template("data-entry.html", username=session["username"])
    else:
        return redirect(url_for("login_page"))

@app.route("/saved-portfolios")
def saved_portfolios():
    """Render the Saved Portfolios page for the logged-in user."""
    if "user_id" not in session:
        return redirect(url_for("login_page"))
    
    user_id = session["user_id"]
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, portfolio_name, portfolio_data, created_at
            FROM portfolios
            WHERE user_id = ?
            ORDER BY created_at DESC
        """, (user_id,))
        rows = cursor.fetchall()
    
    portfolios = []
    for row in rows:
        # Assuming portfolio_data is stored as a JSON string representing an array of assets
        try:
            assets = json.loads(row[2]) if row[2] else []
        except Exception:
            assets = []
        portfolios.append({
            "id": row[0],
            "portfolio_name": row[1],
            "num_assets": len(assets),
            "created_at": row[3]
        })
    
    return render_template("saved-portfolios.html", username=session["username"], portfolios=portfolios)

@app.route("/save-portfolio", methods=["POST"])
def save_portfolio():
    """Save a portfolio for the logged-in user."""
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json() or {}
    portfolio_name = data.get("portfolioName")
    portfolio_data = data.get("portfolioData")  # Expected to be a JSON string or similar

    if not portfolio_name or portfolio_data is None:
        return jsonify({"error": "Portfolio name and data are required"}), 400

    user_id = session["user_id"]

    try:
        # If portfolio_data is not a string, convert it using json.dumps()
        if not isinstance(portfolio_data, str):
            portfolio_data = json.dumps(portfolio_data)
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO portfolios (user_id, portfolio_name, portfolio_data)
                VALUES (?, ?, ?)
            """, (user_id, portfolio_name, portfolio_data))
            conn.commit()
        return jsonify({"message": "Portfolio saved successfully"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    init_db()  # Ensure the database is set up
    app.run(debug=True)
