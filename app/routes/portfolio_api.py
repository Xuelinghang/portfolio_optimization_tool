import os
import sqlite3
import pandas as pd
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
import random

app = Flask(__name__)

# Configuration
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"csv"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DB_FILE = "portfolio.db"

# Initialize database
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_symbol TEXT NOT NULL,
                quantity REAL NOT NULL,
                purchase_price REAL NOT NULL
            )
        """)
        conn.commit()

# Helper function to check allowed file type
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/submit_manual", methods=["POST"])
def submit_manual_entry():
    """Accept manually entered portfolio data."""
    data = request.get_json()
    asset_symbol = data.get("asset_symbol")
    quantity = data.get("quantity")
    purchase_price = data.get("purchase_price")

    if not asset_symbol or not quantity or not purchase_price:
        return jsonify({"error": "All fields (asset_symbol, quantity, purchase_price) are required"}), 400

    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO portfolio (asset_symbol, quantity, purchase_price) VALUES (?, ?, ?)",
                           (asset_symbol, quantity, purchase_price))
            conn.commit()
        return jsonify({"message": "Asset added to portfolio"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/upload_csv", methods=["POST"])
def upload_csv():
    """Accept a CSV file and parse portfolio data."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        try:
            df = pd.read_csv(filepath)
            required_columns = {"asset_symbol", "quantity", "purchase_price"}
            if not required_columns.issubset(df.columns):
                return jsonify({"error": f"CSV must contain columns: {required_columns}"}), 400

            with sqlite3.connect(DB_FILE) as conn:
                cursor = conn.cursor()
                for _, row in df.iterrows():
                    cursor.execute("INSERT INTO portfolio (asset_symbol, quantity, purchase_price) VALUES (?, ?, ?)",
                                   (row["asset_symbol"], row["quantity"], row["purchase_price"]))
                conn.commit()
            
            return jsonify({"message": "CSV uploaded and portfolio updated"}), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        return jsonify({"error": "Invalid file format. Only CSV files are allowed."}), 400

@app.route("/simulate_market_data", methods=["GET"])
def simulate_market_data():
    """Simulate fetching market data for portfolio assets."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT asset_symbol FROM portfolio")
            assets = [row[0] for row in cursor.fetchall()]

        if not assets:
            return jsonify({"error": "No assets in portfolio to fetch data for"}), 400

        simulated_data = {}
        for asset in assets:
            simulated_data[asset] = {
                "current_price": round(random.uniform(50, 500), 2),
                "daily_change": round(random.uniform(-5, 5), 2)
            }

        return jsonify(simulated_data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
