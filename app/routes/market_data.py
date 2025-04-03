from flask import Blueprint, request, jsonify, session
from app import db
from app.models import MarketData, Asset
from datetime import datetime

market_bp = Blueprint("market", __name__)

@market_bp.route("/", methods=["GET"])
def get_all_market_data():
    """Retrieve all market data entries."""
    # Ensure user is authenticated
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    user_id = session["user_id"]
    
    # Get user's assets
    user_assets = Asset.query.filter_by(user_id=user_id).all()
    asset_ids = [asset.id for asset in user_assets]
    
    # Get market data for user's assets
    data = MarketData.query.filter(MarketData.asset_id.in_(asset_ids)).all()
    
    results = []
    for entry in data:
        results.append({
            "id": entry.id,
            "asset_id": entry.asset_id,
            "symbol": next((a.symbol for a in user_assets if a.id == entry.asset_id), "Unknown"),
            "date": entry.date.strftime("%Y-%m-%d"),
            "price": entry.price
        })
    return jsonify(results), 200

@market_bp.route("/<int:asset_id>", methods=["GET"])
def get_market_data_by_asset(asset_id):
    """Retrieve market data for a specific asset."""
    # Ensure user is authenticated
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    user_id = session["user_id"]
    
    # Verify that the asset belongs to the user
    asset = Asset.query.filter_by(id=asset_id, user_id=user_id).first()
    if not asset:
        return jsonify({"error": "Asset not found or unauthorized"}), 404
    
    # Get market data
    data = MarketData.query.filter_by(asset_id=asset_id).all()
    
    results = []
    for entry in data:
        results.append({
            "id": entry.id,
            "asset_id": entry.asset_id,
            "symbol": asset.symbol,
            "date": entry.date.strftime("%Y-%m-%d"),
            "price": entry.price
        })
    return jsonify(results), 200

@market_bp.route("/", methods=["POST"])
def add_market_data():
    """Add a new market data entry."""
    # Ensure user is authenticated
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    user_id = session["user_id"]
    
    data = request.get_json()
    asset_id = data.get("asset_id")
    price = data.get("price")
    date_str = data.get("date")  # Optional; if provided, should be in YYYY-MM-DD format

    if not asset_id or price is None:
        return jsonify({"error": "asset_id and price are required"}), 400
    
    # Verify that the asset belongs to the user
    asset = Asset.query.filter_by(id=asset_id, user_id=user_id).first()
    if not asset:
        return jsonify({"error": "Asset not found or unauthorized"}), 404

    # If a date is provided, parse it; otherwise, use current timestamp.
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.utcnow()
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    new_entry = MarketData(asset_id=asset_id, price=price, date=date_obj)
    db.session.add(new_entry)
    db.session.commit()

    return jsonify({"message": "Market data added successfully"}), 201