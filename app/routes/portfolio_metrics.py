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
    # Check if user is logged in
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    user_id = session["user_id"]

    # Get the portfolio
    portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=user_id).first()
    if not portfolio:
        return jsonify({"error": "Portfolio not found"}), 404

    # Parse portfolio data
    try:
        portfolio_data = json.loads(portfolio.portfolio_data)
    except:
        return jsonify({"error": "Invalid portfolio data format"}), 400

    # Extract tickers and allocations
    assets = {}
    for item in portfolio_data:
        ticker = item.get("ticker")
        allocation = item.get("allocation")
        if ticker and allocation is not None:
            assets[ticker] = float(allocation)
    
    # Normalize allocations (ensure they sum to 1.0)
    total_allocation = sum(assets.values())
    weights = {ticker: alloc/total_allocation for ticker, alloc in assets.items()}
    
    # Get historical market data for each asset
    asset_prices = {}
    returns_data = {}
    
    # Default time period: 1 year
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365*3)  # 3 years of data for better metrics
    
    for ticker in assets.keys():
        # Find the asset in the database
        asset = Asset.query.filter_by(symbol=ticker, user_id=user_id).first()
        
        if not asset:
            continue
            
        # Get market data for this asset
        market_data = MarketData.query.filter(
            MarketData.asset_id == asset.id,
            MarketData.date >= start_date,
            MarketData.date <= end_date
        ).order_by(MarketData.date).all()
        
        if not market_data or len(market_data) < 10:  # Need at least some data points
            continue
            
        # Convert to DataFrame
        dates = [data.date for data in market_data]
        prices = [data.price for data in market_data]
        
        # Create a Series with dates as index
        price_series = pd.Series(prices, index=dates)
        
        # Resample to monthly frequency for more stable metrics
        monthly_prices = price_series.resample('M').last()
        
        # Calculate returns
        returns = monthly_prices.pct_change().dropna()
        
        # Store data
        asset_prices[ticker] = monthly_prices
        returns_data[ticker] = returns
    
    # If we don't have any asset data, return a simple response
    if not asset_prices:
        return jsonify({
            "error": "Insufficient market data for portfolio metrics calculation. Please refresh market data first.",
            "portfolio_name": portfolio.portfolio_name
        }), 404
    
    # Calculate portfolio returns based on weights
    portfolio_returns = pd.Series(0.0, index=next(iter(returns_data.values())).index)
    
    for ticker, ticker_returns in returns_data.items():
        weight = weights.get(ticker, 0)
        aligned_returns = ticker_returns.reindex(portfolio_returns.index).fillna(0)
        portfolio_returns += aligned_returns * weight
    
    # Calculate portfolio values (starting with $10,000)
    initial_investment = 10000.0
    portfolio_values = (1 + portfolio_returns).cumprod() * initial_investment
    
    # Prepare data for metrics calculation
    portfolio_data = {
        'returns': portfolio_returns,
        'values': portfolio_values
    }
    
    # Calculate comprehensive metrics using the utility function
    metrics_results = calculate_portfolio_metrics(portfolio_data, returns_data)
    
    # Format the results for the API response
    formatted_metrics = {
    "risk_decomposition": [
        {
            "ticker": ticker,
            "Name": ticker,
            "Contribution": float(metrics_results['risk_contributions'].get(ticker, 0) * 100)
        } for ticker in assets.keys()
    ],
    "return_decomposition": [
        {
            "ticker": ticker,
            "Name": ticker,
            "Contribution": float(metrics_results['return_contributions'].get(ticker, 0))
        } for ticker in assets.keys()
    ],
    "holdings": [
        {
            "ticker": ticker,
            "Weight": weights[ticker],
            "Name": ticker
        } for ticker in assets.keys()
    ],
        "portfolio_name": portfolio.portfolio_name,
        "assets": list(assets.keys()),
        "weights": [weights[ticker] for ticker in assets.keys()],
        "metrics": {
            "Start Balance": float(portfolio_values.iloc[0]),
            "End Balance": float(portfolio_values.iloc[-1]),
            "Annualized Return (CAGR)": float(metrics_results['portfolio']['cagr'] * 100),  # Convert to percentage
            "Standard Deviation": float(metrics_results['portfolio']['std_dev_annual'] * 100),  # Convert to percentage
            "Sharpe Ratio": float(metrics_results['portfolio']['sharpe_ratio']),
            "Sortino Ratio": float(metrics_results['portfolio']['sortino_ratio']),
            "Maximum Drawdown": float(metrics_results['portfolio']['max_drawdown'] * 100),  # Convert to percentage
            "Monthly Positive Periods": f"{metrics_results['portfolio']['positive_periods']}/{metrics_results['portfolio']['total_periods']}",
            "Gain/Loss Ratio": float(metrics_results['portfolio']['gain_loss_ratio']),
        },
        "annual_returns": {str(year): float(value * 100) for year, value in metrics_results['annual_returns'].items()},  # Convert to percentage
        "trailing_returns": {period: float(value * 100) for period, value in metrics_results['trailing_returns'].items()},  # Convert to percentage
        "asset_metrics": {
            ticker: {
                "CAGR": float(metrics['cagr'] * 100),  # Convert to percentage
                "Standard Deviation": float(metrics['std_dev'] * 100),  # Convert to percentage
                "Maximum Drawdown": float(metrics['max_drawdown'] * 100),  # Convert to percentage
                "Sharpe Ratio": float(metrics['sharpe_ratio'])
            } for ticker, metrics in metrics_results['assets'].items()
        },
        "calculation_date": datetime.now().strftime('%Y-%m-%d')
    }
    
    return jsonify(formatted_metrics), 200