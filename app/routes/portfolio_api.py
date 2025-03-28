from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from portfolio_optimization_tool.app.models import Portfolio, Asset, User  # adjust import path to your structure

portfolio_bp = Blueprint("portfolio", __name__)

@portfolio_bp.route("/portfolio/manual", methods=["POST"])
@jwt_required()
def submit_manual_entry():
    user_id = get_jwt_identity()
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
@jwt_required()
def upload_csv():
    user_id = get_jwt_identity()
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    import pandas as pd
    from werkzeug.utils import secure_filename
    import os

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
@jwt_required()
def simulate_market_data():
    user_id = get_jwt_identity()
    portfolios = Portfolio.query.filter_by(user_id=user_id).all()
    if not portfolios:
        return jsonify({"error": "No assets found in portfolio"}), 400

    import random
    simulated = {
        p.asset.symbol: {
            "current_price": round(random.uniform(50, 500), 2),
            "daily_change": round(random.uniform(-5, 5), 2)
        } for p in portfolios
    }
    return jsonify(simulated), 200
