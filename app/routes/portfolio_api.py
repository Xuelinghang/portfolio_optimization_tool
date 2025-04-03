from flask import Blueprint, request, jsonify, session, redirect, url_for
import os
import json
import pandas as pd
from app import db
from app.models import Portfolio, Asset

portfolio_bp = Blueprint("portfolio", __name__)

@portfolio_bp.route("/portfolio/manual", methods=["POST"])
def submit_manual_entry():
    # Check if user is logged in
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    user_id = session["user_id"]

    data = request.get_json()
    symbol = data.get("asset_symbol")
    quantity = data.get("quantity")
    purchase_price = data.get("purchase_price")
    asset_type = data.get("asset_type", "Stock")  # default type

    if not symbol or not quantity or not purchase_price:
        return jsonify({"error": "Missing fields"}), 400

    asset = Asset.query.filter_by(symbol=symbol, user_id=user_id).first()
    if not asset:
        asset = Asset(symbol=symbol, asset_type=asset_type, user_id=user_id)
        db.session.add(asset)
        db.session.commit()

    entry = Portfolio(user_id=user_id, asset_id=asset.id, quantity=quantity, purchase_price=purchase_price)
    db.session.add(entry)
    db.session.commit()

    return jsonify({"message": "Asset added to portfolio"}), 201

@portfolio_bp.route("/portfolio/upload", methods=["POST"])
def upload_csv():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    user_id = session["user_id"]

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    from werkzeug.utils import secure_filename
    filename = secure_filename(file.filename)
    filepath = os.path.join("uploads", filename)
    os.makedirs("uploads", exist_ok=True)
    file.save(filepath)

    try:
        df = pd.read_csv(filepath)
        required_columns = {"asset_symbol", "quantity", "purchase_price"}
        if not required_columns.issubset(df.columns):
            return jsonify({"error": "CSV must contain: asset_symbol, quantity, purchase_price"}), 400

        for _, row in df.iterrows():
            symbol = row["asset_symbol"]
            quantity = row["quantity"]
            purchase_price = row["purchase_price"]

            asset = Asset.query.filter_by(symbol=symbol, user_id=user_id).first()
            if not asset:
                asset = Asset(symbol=symbol, asset_type="Stock", user_id=user_id)
                db.session.add(asset)
                db.session.commit()

            entry = Portfolio(user_id=user_id, asset_id=asset.id, quantity=quantity, purchase_price=purchase_price)
            db.session.add(entry)

        db.session.commit()
        return jsonify({"message": "CSV uploaded and portfolio updated"}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@portfolio_bp.route("/portfolio/simulate", methods=["GET"])
def simulate_market_data():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    user_id = session["user_id"]
    portfolios = Portfolio.query.filter_by(user_id=user_id).all()
    if not portfolios:
        return jsonify({"error": "No assets found in portfolio"}), 400

    # For demo purposes, we're returning a simulated response.
    import random
    simulated = {
        "simulated_data": [
            {
                "symbol": "SIM",
                "current_price": round(random.uniform(50, 500), 2),
                "daily_change": round(random.uniform(-5, 5), 2)
            }
        ]
    }
    return jsonify(simulated), 200
