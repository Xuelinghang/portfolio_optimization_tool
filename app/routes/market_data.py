# app/routes/market_data.py

import os
import json 
import pandas as pd
import numpy as np 
from datetime import datetime, timedelta, date, UTC
import requests
from flask_login import login_required, current_user
from flask import Blueprint, request, jsonify, abort, render_template, send_file, flash, current_app
from werkzeug.utils import secure_filename 
import traceback
import time 
from io import StringIO 

from app import db
from app.models import User, Portfolio, Asset, MarketData, PortfolioAsset, Transaction, CalculationResult
from .market_fetcher import (
    fetch_yahoo_data,
    fetch_alpha_vantage_data,
    _get_coingecko_id_map,
    fetch_coingecko_simple_price,
)


ALPHA_VANTAGE_API_KEY = os.environ.get('ALPHA_VANTAGE_API_KEY', '')

market_bp = Blueprint("market", __name__)

@market_bp.route("/", methods=["GET"])
@login_required # Require login for this route
def get_all_market_data():
    """Retrieve all market data entries for the logged-in user's assets."""
    user_id = current_user.id

    # Get user's assets
    user_assets = Asset.query.filter_by(user_id=user_id).all()
    asset_ids = [asset.id for asset in user_assets]

    if not asset_ids:
        return jsonify([]), 200

    data = MarketData.query.filter(MarketData.asset_id.in_(asset_ids)).all()

    results = []
    # Create a dictionary mapping asset ID to symbol for efficient lookup
    asset_id_to_symbol = {asset.id: asset.symbol for asset in user_assets}

    for entry in data:
        results.append({
            "id": entry.id,
            "asset_id": entry.asset_id,
            "symbol": asset_id_to_symbol.get(entry.asset_id, "Unknown"),
            "date": entry.date.strftime("%Y-%m-%d"),
            "price": float(entry.price)
        })
    return jsonify(results), 200

@market_bp.route("/<int:asset_id>", methods=["GET"])
@login_required # Require login for this route
def get_market_data_by_asset(asset_id):
    """Retrieve market data for a specific asset belonging to the logged-in user."""
    user_id = current_user.id

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
            "price": float(entry.price)
        })
    return jsonify(results), 200

@market_bp.route("/", methods=["POST"])
@login_required # Require login for this route
def add_market_data():
    """Add a new market data entry for an asset belonging to the logged-in user."""
    user_id = current_user.id

    data = request.get_json()
    asset_id = data.get("asset_id")
    price = data.get("price")
    date_str = data.get("date")

    if not asset_id or price is None:
        return jsonify({"error": "asset_id and price are required"}), 400

    # Verify that the asset belongs to the user
    asset = Asset.query.filter_by(id=asset_id, user_id=user_id).first()
    if not asset:
        return jsonify({"error": "Asset not found or unauthorized"}), 404

    # If a date is provided, parse it; otherwise, use current timestamp (UTC).
    try:
        # Use datetime.now(UTC) for timezone-aware UTC datetime
        date_obj = datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.now(UTC) # <--- CHANGED from utcnow()
    except ValueError:
        return jsonify({"error": "Invalid date format. Use %Y-%m-%d."}), 400

    try:
        price_float = float(price)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid price format."}), 400

    # Check if an entry for this asset and exact date/time already exists (simple check)
    existing_entry = MarketData.query.filter_by(asset_id=asset.id, date=date_obj).first()
    if existing_entry:
         return jsonify({"message": "Market data entry for this date already exists."}), 409 # Conflict


    new_entry = MarketData(asset_id=asset.id, price=price_float, date=date_obj)
    db.session.add(new_entry)
    try:
        db.session.commit()
        return jsonify({"message": "Market data added successfully", "id": new_entry.id}), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error adding market data entry: {e}")
        traceback.print_exc()
        return jsonify({"error": "An error occurred while adding market data."}), 500


@market_bp.route("/search-ticker", methods=["GET"])
def search_ticker():
    """
    Search for ticker symbols using Alpha Vantage.
    Query Parameter:
      - keyword: The search term with at least 2 characters
    Returns a list of matching symbols and names.
    """
    keyword = request.args.get("keyword", "").strip()
    if len(keyword) < 2:
        return jsonify([])

    if not ALPHA_VANTAGE_API_KEY:
        current_app.logger.error("Alpha Vantage API key not configured for ticker search")
        return jsonify({"error": "Ticker search is temporarily unavailable."}), 503

    url = f"https://www.alphavantage.co/query?function=SYMBOL_SEARCH&keywords={keyword}&apikey={ALPHA_VANTAGE_API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        suggestions = []
        if "bestMatches" in data:
            for match in data["bestMatches"]:
                suggestions.append({
                    "symbol": match.get("1. symbol", ""),
                    "name": match.get("2. name", "")
                })
        return jsonify(suggestions)
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Alpha Vantage Ticker search request error: {e}")
        traceback.print_exc()
        return jsonify({"error": "Error searching for tickers."}), 500
    except Exception as e:
        current_app.logger.error(f"Alpha Vantage Ticker search general error: {e}")
        traceback.print_exc()
        return jsonify({"error": "An error occurred during ticker search."}), 500


@market_bp.route("/<ticker>", methods=["GET"])
@login_required # Assuming this route requires login
def get_market_data_by_ticker(ticker):
    """
    Retrieve latest market data (latest price) for a specific ticker symbol.
    Requires login. Uses fallback if initial fetch fails.
    """
    try:
        # Attempt to fetch latest price using your combined fetch logic
        # Using fetch_yahoo_data(..., period="current") is a common way to get latest price
        price_or_df = fetch_yahoo_data(ticker, period="current")

        price = None # Variable to hold the scalar price

        if price_or_df is None:
            # Try Alpha Vantage GLOBAL_QUOTE as fallback for latest price if Yahoo fails
             price_scalar = fetch_alpha_vantage_data(ticker, function="GLOBAL_QUOTE")
             if price_scalar is not None:
                  price = price_scalar
             else:
                 # Try CoinGecko simple price if it's likely a crypto
                 # Need to query Asset table here to check asset type
                 asset = Asset.query.filter_by(symbol=ticker).first()
                 if asset and asset.asset_type.lower() == "crypto":
                     # Assumes _get_coingecko_id_map and fetch_coingecko_simple_price are imported
                     cg_map = _get_coingecko_id_map()
                     if cg_map and (cg_id := cg_map.get(asset.symbol.upper())):
                          price_scalar = fetch_coingecko_simple_price(cg_id, vs_currency="usd")
                          if price_scalar is not None:
                              price = price_scalar
                          else:
                              current_app.logger.warning(f"CoinGecko simple-price returned no value for {ticker} (ID: {cg_id})")


        elif isinstance(price_or_df, pd.DataFrame) and not price_or_df.empty:
             # If Yahoo returned a DataFrame (e.g., period='1d'), get the latest 'Close' price
             if 'Close' in price_or_df.columns:
                 price = price_or_df['Close'].iloc[-1]
             else:
                 current_app.logger.warning(f"'Close' column not found in Yahoo latest DF for {ticker}. Columns: {price_or_df.columns.tolist()}")

        elif isinstance(price_or_df, (int, float)) and not pd.isna(price_or_df):
             # If Yahoo returned a scalar directly (less common for period='current')
             price = price_or_df

        if price is None:
            # Return 404 if no price was found from any source
            return jsonify({"error": f"Could not fetch latest data for {ticker} from any source."}), 404

        # Return the latest price as JSON
        # Use datetime.now(UTC) for timezone-aware current time
        return jsonify({
            "symbol": ticker,
            "price": float(price),
            "timestamp": datetime.now(UTC).isoformat()
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching latest data for {ticker}: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": f"An error occurred fetching latest data for {ticker}."}), 500
