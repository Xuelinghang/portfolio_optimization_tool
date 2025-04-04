import os
import json
import io
import csv
import random
import pandas as pd
from flask import (
    Blueprint, request, jsonify, session, redirect,
    url_for, render_template, abort, send_file
)
from werkzeug.utils import secure_filename
from app import db
from app.models import Portfolio, Asset

portfolio_bp = Blueprint("portfolio", __name__)

# --- Portfolio API Endpoints (Session-based) ---

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
    # Check if user is logged in
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    user_id = session["user_id"]

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join("uploads", filename)
    os.makedirs("uploads", exist_ok=True)

    try:
        file.save(filepath)
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
    # Check if user is logged in
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    user_id = session["user_id"]

    portfolios = Portfolio.query.filter_by(user_id=user_id).all()
    if not portfolios:
        return jsonify({"error": "No assets found in portfolio"}), 400

    # For demo purposes, return simulated data
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


@portfolio_bp.route("/portfolio/open/<int:portfolio_id>", methods=["GET"])
def open_portfolio(portfolio_id):
    if "user_id" not in session:
        return redirect(url_for("auth.login_page"))

    # Verify ownership of the portfolio
    portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=session["user_id"]).first()
    if not portfolio:
        abort(404, description="Portfolio not found or unauthorized.")

    try:
        portfolio_data = json.loads(portfolio.portfolio_data) if portfolio.portfolio_data else []
    except Exception:
        portfolio_data = []

    # Compute or retrieve analysis data (stubbed example)
    analysis = {
        "summary": {
            "growth": "$10,000 invested on January 1, 2024 would be worth $10,450 as of February 28, 2025 (4.50% cumulative return)",
            "return": "3.85% per year; 57.14% of months positive. Best Year: 2024 (5.37%), Worst Year: 2025 (-0.82%)",
            "risk": "Maximum drawdown of 9.69% (Jan-Apr 2024) with a Sharpe Ratio of -0.08"
        }
        # Additional keys for exposures, metrics, returns, drawdowns, etc.
    }

    return render_template("portfolio_detail.html",
                           portfolio=portfolio,
                           portfolio_data=portfolio_data,
                           analysis=analysis,
                           username=session.get("username"))


@portfolio_bp.route("/portfolio/edit/<int:portfolio_id>", methods=["GET"])
def edit_portfolio(portfolio_id):
    if "user_id" not in session:
        return redirect(url_for("auth.login_page"))

    # Verify ownership of the portfolio
    portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=session["user_id"]).first()
    if not portfolio:
        abort(404, description="Portfolio not found or unauthorized.")

    # Render the data-entry page pre-populated with portfolio data
    return render_template("data-entry.html", portfolio=portfolio, username=session.get("username"))


@portfolio_bp.route("/portfolio/download/<int:portfolio_id>", methods=["GET"])
def download_portfolio(portfolio_id):
    if "user_id" not in session:
        abort(401)

    # Verify ownership
    portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=session["user_id"]).first()
    if not portfolio:
        abort(404, description="Portfolio not found or unauthorized.")

    try:
        portfolio_data = json.loads(portfolio.portfolio_data) if portfolio.portfolio_data else []
    except Exception:
        portfolio_data = []

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Ticker", "Company Name", "Allocation Percentage"])
    for entry in portfolio_data:
        writer.writerow([
            entry.get("ticker", ""),
            entry.get("company_name", "N/A"),
            entry.get("allocation", "")
        ])

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype="text/csv",
        as_attachment=True,
        attachment_filename=f"portfolio_{portfolio_id}.csv"
    )


@portfolio_bp.route("/portfolio/delete/<int:portfolio_id>", methods=["POST"])
def delete_portfolio(portfolio_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    # Verify ownership
    portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=session["user_id"]).first()
    if not portfolio:
        return jsonify({"error": "Portfolio not found or unauthorized"}), 404

    db.session.delete(portfolio)
    db.session.commit()
    return jsonify({"message": "Portfolio deleted successfully"}), 200
