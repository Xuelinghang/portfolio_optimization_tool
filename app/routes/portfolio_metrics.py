from flask import Blueprint, jsonify, session
from app import db
from app.models import Portfolio, Asset, MarketData
import numpy as np
import pandas as pd
import json
from datetime import datetime, timedelta
from utils.financial_metrics import calculate_portfolio_metrics

metrics_bp = Blueprint("metrics", __name__)

@metrics_bp.route("/portfolio/metrics/<int:portfolio_id>", methods=["GET"])
def get_portfolio_metrics(portfolio_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    user_id = session["user_id"]

    portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=user_id).first()
    if not portfolio:
        return jsonify({"error": "Portfolio not found"}), 404

    try:
        portfolio_data = json.loads(portfolio.portfolio_data)
    except:
        return jsonify({"error": "Invalid portfolio data format"}), 400

    assets = {}
    for item in portfolio_data:
        ticker = item.get("ticker")
        allocation = item.get("allocation")
        if ticker and allocation is not None:
            assets[ticker] = float(allocation)

    total_allocation = sum(assets.values())
    weights = {ticker: alloc / total_allocation for ticker, alloc in assets.items()}

    asset_prices = {}
    returns_data = {}

    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * 3)

    asset_lookup = {}
    for ticker in assets.keys():
        asset = Asset.query.filter_by(symbol=ticker, user_id=user_id).first()
        asset_lookup[ticker] = asset

        if not asset:
            continue

        market_data = MarketData.query.filter(
            MarketData.asset_id == asset.id,
            MarketData.date >= start_date,
            MarketData.date <= end_date
        ).order_by(MarketData.date).all()

        if not market_data or len(market_data) < 10:
            continue

        dates = [data.date for data in market_data]
        prices = [data.price for data in market_data]
        price_series = pd.Series(prices, index=dates)
        monthly_prices = price_series.resample('M').last()
        returns = monthly_prices.pct_change().dropna()

        asset_prices[ticker] = monthly_prices
        returns_data[ticker] = returns

    if not asset_prices:
        return jsonify({
            "error": "Insufficient market data for portfolio metrics calculation. Please refresh market data first.",
            "portfolio_name": portfolio.portfolio_name
        }), 404

    portfolio_returns = pd.Series(0.0, index=next(iter(returns_data.values())).index)
    for ticker, ticker_returns in returns_data.items():
        weight = weights.get(ticker, 0)
        aligned_returns = ticker_returns.reindex(portfolio_returns.index).fillna(0)
        portfolio_returns += aligned_returns * weight

    initial_investment = 10000.0
    portfolio_values = (1 + portfolio_returns).cumprod() * initial_investment

    portfolio_data = {
        'returns': portfolio_returns,
        'values': portfolio_values
    }

    metrics_results = calculate_portfolio_metrics(portfolio_data, returns_data)

    formatted_metrics = {
        "risk_decomposition": [
            {
                "Ticker": ticker,
                "Name": asset_lookup[ticker].name if asset_lookup[ticker] else ticker,
                "Contribution": float(metrics_results['risk_contributions'].get(ticker, 0) * 100)
            } for ticker in assets.keys()
        ],
        "return_decomposition": [
            {
                "Ticker": ticker,
                "Name": asset_lookup[ticker].name if asset_lookup[ticker] else ticker,
                "Contribution": float(metrics_results['return_contributions'].get(ticker, 0))
            } for ticker in assets.keys()
        ],
        "holdings": [
            {
                "Ticker": ticker,
                "Name": asset_lookup[ticker].name if asset_lookup[ticker] else ticker,
                "Weight": weights[ticker]
            } for ticker in assets.keys()
        ],
        "portfolio_name": portfolio.portfolio_name,
        "assets": list(assets.keys()),
        "weights": [weights[ticker] for ticker in assets.keys()],
        "metrics": {
            "Start Balance": float(portfolio_values.iloc[0]),
            "End Balance": float(portfolio_values.iloc[-1]),
            "Annualized Return (CAGR)": float(metrics_results['portfolio']['cagr'] * 100),
            "Standard Deviation": float(metrics_results['portfolio']['std_dev_annual'] * 100),
            "Sharpe Ratio": float(metrics_results['portfolio']['sharpe_ratio']),
            "Sortino Ratio": float(metrics_results['portfolio']['sortino_ratio']),
            "Maximum Drawdown": float(metrics_results['portfolio']['max_drawdown'] * 100),
            "Monthly Positive Periods": f"{metrics_results['portfolio']['positive_periods']}/{metrics_results['portfolio']['total_periods']}",
            "Gain/Loss Ratio": float(metrics_results['portfolio']['gain_loss_ratio']),
        },
        "annual_returns": {
            str(year): float(value * 100)
            for year, value in metrics_results['annual_returns'].items()
        },
        "trailing_returns": {
            period: float(value * 100)
            for period, value in metrics_results['trailing_returns'].items()
        },
        "asset_metrics": [
            {
                "Ticker": ticker,
                "Name": asset_lookup[ticker].name if asset_lookup[ticker] else ticker,
                "CAGR": float(metrics['cagr'] * 100),
                "StandardDeviation": float(metrics['std_dev'] * 100),
                "MaximumDrawdown": float(metrics['max_drawdown'] * 100),
                "SharpeRatio": float(metrics['sharpe_ratio'])
            } for ticker, metrics in metrics_results['assets'].items()
        ],
        "calculation_date": datetime.now().strftime('%Y-%m-%d')
    }

    return jsonify(formatted_metrics), 200
