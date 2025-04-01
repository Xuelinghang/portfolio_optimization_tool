from flask import Blueprint, request, jsonify, session
from app import db
from app.models import MarketData
from datetime import datetime

market_bp = Blueprint("market", __name__)

@market_bp.route("/", methods=["GET"])
def get_all_market_data():
    # Optionally, if you want to restrict access:
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = MarketData.query.all()
    results = []
    for entry in data:
        results.append({
            "id": entry.id,
            "asset_id": entry.asset_id,
            "date": entry.date.strftime("%Y-%m-%d"),
            "price": entry.price
        })
    return jsonify(results), 200

@market_bp.route("/<int:asset_id>", methods=["GET"])
def get_market_data_by_asset(asset_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = MarketData.query.filter_by(asset_id=asset_id).all()
    results = []
    for entry in data:
        results.append({
            "id": entry.id,
            "asset_id": entry.asset_id,
            "date": entry.date.strftime("%Y-%m-%d"),
            "price": entry.price
        })
    return jsonify(results), 200

@market_bp.route("/", methods=["POST"])
def add_market_data():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    asset_id = data.get("asset_id")
    price = data.get("price")
    date_str = data.get("date")  # Optional; if provided, should be in YYYY-MM-DD format

    if not asset_id or price is None:
        return jsonify({"error": "asset_id and price are required"}), 400

    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.utcnow()
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    new_entry = MarketData(asset_id=asset_id, price=price, date=date_obj)
    db.session.add(new_entry)
    db.session.commit()

    return jsonify({"message": "Market data added successfully"}), 201
