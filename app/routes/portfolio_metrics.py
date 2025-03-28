from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import Portfolio, MarketData
import numpy as np
import pandas as pd
import datetime

metrics_bp = Blueprint("metrics", __name__)

@metrics_bp.route("/portfolio/metrics", methods=["GET"])
@jwt_required()
def calculate_portfolio_metrics():
    user_id = get_jwt_identity()

    # Step 1: Get user portfolio
    portfolios = Portfolio.query.filter_by(user_id=user_id).all()
    if not portfolios:
        return jsonify({"error": "No portfolio found"}), 404

    assets = [p.asset.symbol for p in portfolios]
    quantities = {p.asset.symbol: p.quantity for p in portfolios}

    # Step 2: Get recent price history from MarketData (or mock for now)
    data = {}
    today = datetime.date.today()

    for asset in assets:
        # Simulate 252 days of returns (for demo; replace with real DB prices)
        np.random.seed(hash(asset) % 10000)
        daily_returns = np.random.normal(0.0005, 0.01, 252)
        data[asset] = daily_returns

    returns_df = pd.DataFrame(data)

    # Step 3: Compute portfolio weights
    latest_prices = {symbol: 100 for symbol in assets}  # TODO: pull real latest prices from MarketData table
    total_value = sum(quantities[symbol] * latest_prices[symbol] for symbol in assets)
    weights = np.array([quantities[symbol] * latest_prices[symbol] / total_value for symbol in assets])

    # Step 4: Compute metrics
    risk_free_rate = 0.02 / 252

    def expected_return(returns, weights):
        return np.dot(weights, returns.mean()) * 252

    def portfolio_volatility(returns, weights):
        cov_matrix = returns.cov() * 252
        return np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))

    def sharpe_ratio(returns, weights, risk_free_rate):
        er = expected_return(returns, weights)
        vol = portfolio_volatility(returns, weights)
        return (er - risk_free_rate * 252) / vol

    def max_drawdown(values):
        cumulative = values.cummax()
        drawdowns = (values - cumulative) / cumulative
        return drawdowns.min()

    def cagr(start, end, years):
        return (end / start) ** (1 / years) - 1

    start_balance = 10000
    end_balance = start_balance * (1 + expected_return(returns_df, weights))
    years = 1  # 252 trading days

    values = (1 + returns_df @ weights).cumprod()

    metrics = {
        "Start Balance": start_balance,
        "End Balance": round(end_balance, 2),
        "Annualized Return (CAGR)": round(cagr(start_balance, end_balance, years) * 100, 2),
        "Standard Deviation": round(portfolio_volatility(returns_df, weights) * 100, 2),
        "Best Year": round(returns_df.mean().max() * 252 * 100, 2),
        "Worst Year": round(returns_df.mean().min() * 252 * 100, 2),
        "Maximum Drawdown": round(max_drawdown(values) * 100, 2),
        "Sharpe Ratio": round(sharpe_ratio(returns_df, weights, risk_free_rate), 2),
    }

    return jsonify(metrics), 200
