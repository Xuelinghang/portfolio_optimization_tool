# app/routes/portfolio_metrics.py

import os
import json
import pandas as pd
import numpy as np
# Import necessary date/time modules and UTC timezone
from datetime import datetime, timedelta, date, UTC # <--- ADDED UTC
import traceback
import requests
# Import Flask-Login decorator and proxy object
from flask_login import login_required, current_user, login_required
from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template, send_file, flash, current_app # Import necessary Flask modules
from sqlalchemy.orm import joinedload

from app import db # Assuming db is initialized in app/__init__.py
# Ensure models are imported
from app.models import User, Portfolio, Asset, MarketData, PortfolioAsset, Transaction, CalculationResult
from utils.financial_metrics import calculate_portfolio_metrics 

# Assuming get_historical_data_for_asset is in market_fetcher.py
from app.market_fetcher import get_historical_data_for_asset # <--- IMPORT DB FETCH FUNCTION

metrics_bp = Blueprint("metrics", __name__)

@metrics_bp.route("/portfolio/metrics/<int:portfolio_id>", methods=["GET"])
@login_required # <--- ADDED Flask-Login decorator to require login
def get_portfolio_metrics(portfolio_id):
    """
    Calculates comprehensive portfolio metrics for a given portfolio ID based on local market data.
    Determines data fetch range from local DB based on earliest purchase date or a default (1 year).
    Fetches data from the local MarketData table. Calls calculate_portfolio_metrics helper.
    Structures and returns metrics and data for dashboard visualizations as JSON.
    """
    # The @login_required decorator handles authentication
    # Access user ID via current_user from Flask-Login
    user_id = current_user.id # <--- CHANGED from session["user_id"]

    # Fetch the portfolio and verify it belongs to the logged-in user
    # Load holdings and asset relationships efficiently for metrics calculation
    try:
        portfolio = (Portfolio.query
                     .filter_by(id=portfolio_id, user_id=user_id)
                     .options(joinedload(Portfolio.holdings).joinedload(PortfolioAsset.asset))
                     .first())

        if not portfolio:
            print(f"Metrics fetch failed: Portfolio ID {portfolio_id} not found or not authorized for user {user_id}")
            return jsonify({"error": "Portfolio not found"}), 404 # Use 404 if the resource doesn't exist for this user

    except Exception as e:
        current_app.logger.error(f"Error fetching portfolio for metrics (user {user_id}): {str(e)}")
        traceback.print_exc() # Print traceback for debug
        db.session.rollback() # Safeguard
        return jsonify({'error': 'Error fetching portfolio details for metrics'}), 500


    # === Use PortfolioAsset to extract holdings, weights, tickers, and find earliest purchase date ===
    # This data is needed for passing to the calculation helper and structuring the response
    holdings_list = [] # Use a list to store detailed holding info for the response
    tickers_in_portfolio = set() # Use a set to collect unique tickers
    portfolio_total_dollar_value = 0.0 # May be used for normalization or checks
    earliest_purchase_date_from_holdings = None # Variable to track the earliest purchase date (date object)

    # Iterate through PortfolioAsset records to get details and find earliest purchase date
    for h in portfolio.holdings: # Use the loaded holdings relationship
         if h.asset: # Ensure asset relationship is loaded and exists
              # Ensure np is imported for np.isfinite check on numeric fields
              weight = float(h.allocation_pct) if h.allocation_pct is not None and np.isfinite(h.allocation_pct) else 0.0
              dollar_amount = float(h.dollar_amount) if h.dollar_amount is not None and np.isfinite(h.dollar_amount) else 0.0

              holdings_list.append({
                  "ticker": h.asset.symbol,
                  "Name": h.asset.company_name or h.asset.symbol, # Use company name or symbol from Asset
                  "Category": h.asset.asset_type or "Unknown", # Use asset type from Asset or Unknown
                  "Weight": weight,
                  "DollarAmount": dollar_amount,
                  "PurchaseDate": h.purchase_date.strftime('%Y-%m-%d') if h.purchase_date else None, # Format date or None
                  "Sector": h.asset.sector
              })
              tickers_in_portfolio.add(h.asset.symbol) # Add ticker to the set
              portfolio_total_dollar_value += dollar_amount

              # Update earliest_purchase_date_from_holdings (comparing date objects)
              if h.purchase_date: # Check if purchase_date is not None
                   if earliest_purchase_date_from_holdings is None or h.purchase_date < earliest_purchase_date_from_holdings:
                        earliest_purchase_date_from_holdings = h.purchase_date


    if not holdings_list:
        print(f"Metrics fetch failed: No holdings found for portfolio {portfolio_id}")
        return jsonify({"error": "No holdings found for this portfolio"}), 400

    # Create a dictionary of tickers and their weights for the calculation helper if needed
    weights = {h['ticker']: h['Weight'] for h in holdings_list} # Weights from PortfolioAsset

    # --- Determine the historical date range for fetching data from the local MarketData database ---
    # Use the earliest purchase date from holdings as the start date for calculation, or a fallback (e.g., 1 year)
    # The get_historical_data_for_asset function defaults the start date to 1 year ago if start_date is None.
    start_date_for_db_fetch = earliest_purchase_date_from_holdings # Use earliest purchase date (datetime.date or None)
    end_date_for_db_fetch = datetime.now(UTC) # End date is now (as timezone-aware datetime in UTC) # <--- CHANGED from utcnow()


    # Ensure start date is not in the future relative to the end date (shouldn't happen with utcnow but safeguards)
    # Compare date parts if start_date_for_db_fetch is a date object
    if start_date_for_db_fetch and start_date_for_db_fetch > end_date_for_db_fetch.date():
         print(f"Warning: Calculated start date {start_date_for_db_fetch} is in the future ({end_date_for_db_fetch.date()}). Setting start date to end date.")
         start_date_for_db_fetch = end_date_for_db_fetch.date() # Ensure it's a date object


    print(f"Fetching market data from DB for metrics calculation from {start_date_for_db_fetch.strftime('%Y-%m-%d') if start_date_for_db_fetch else 'Default (1 Year)'} to {end_date_for_db_fetch.date().strftime('%Y-%m-%d')}")

    # --- Query local MarketData table using the determined dynamic date range ---
    # Get Asset IDs for the tickers to query MarketData efficiently
    # Assuming Asset.query.filter(...).all() is not excessively slow
    ticker_asset_ids = {asset.symbol: asset.id for asset in Asset.query.filter(Asset.symbol.in_(list(tickers_in_portfolio)), Asset.user_id == user_id).all()}

    asset_prices_series = {} # Dictionary to store daily/original price Series {ticker: price_series}

    for ticker in tickers_in_portfolio:
        asset_id = ticker_asset_ids.get(ticker)
        if asset_id is None:
             print(f"Warning: Asset ID not found in DB for ticker {ticker}. Cannot fetch market data for metrics.")
             continue

        # Query local MarketData table for this asset and the dynamic date range
        # get_historical_data_for_asset accepts start_date (date object or None) and end_date (datetime or None).
        # It orders by date and returns a DataFrame with date index and 'price' column.
        df_from_db = get_historical_data_for_asset(asset_id, start_date=start_date_for_db_fetch, end_date=end_date_for_db_fetch)


        if df_from_db is not None and isinstance(df_from_db, pd.DataFrame) and not df_from_db.empty and df_from_db.index.name == 'date' and 'price' in df_from_db.columns:
             # Store the price Series (DataFrame with date index and 'price' column)
             asset_prices_series[ticker] = df_from_db['price'] # Store the price Series for this ticker
             print(f"  Successfully fetched DataFrame from DB for {ticker} ({len(df_from_db)} points).")
        else:
             print(f"No historical data found in DB for ticker {ticker} within calculation range ({start_date_for_db_fetch.strftime('%Y-%m-%d') if start_date_for_db_fetch else 'Default (1 Year)'} to {end_date_for_db_fetch.date().strftime('%Y-%m-%d')}) after DB fetch.")


    # --- Prepare data for the calculation helper ---
    # The calculation helper likely expects a DataFrame where columns are tickers and the index is the date.
    # We have individual price Series (date index, price values) in asset_prices_series.

    # Combine the individual price Series into a single DataFrame
    # The keys of the dictionary (tickers) become the column names
    # The indices (dates) are aligned automatically by pandas (union of all indices).
    price_data_for_calc = pd.DataFrame(asset_prices_series)

    if price_data_for_calc.empty:
         print("No sufficient historical data found in DB for metrics calculation after checking all tickers.")
         # Adjust the error message to reflect the actual dynamic date range used
         return jsonify({
             "error": f"Insufficient market data in the database for portfolio metrics calculation for the period from {start_date_for_db_fetch.date() if start_date_for_db_fetch else 'Default (1 Year)'} to {end_date_for_db_fetch.date()}. Ensure assets have data saved via background jobs for this period.",
             "portfolio_name": portfolio.portfolio_name
         }), 404


    # Clean the data for calculation (handle missing values)
    # Financial metrics require clean time series data.
    # Resampling to a fixed frequency (like daily or monthly) is often necessary.
    # Let's resample to daily frequency first to ensure all tickers have daily points for the common date range.
    # Then, forward fill missing daily prices, and optionally backward fill initial NaNs.

    try:
        # Resample to daily frequency across the common index
        daily_prices = price_data_for_calc.resample('D').last() # Resample to daily, take last price of the day

        # Handle missing daily prices (forward fill then backward fill)
        daily_prices = daily_prices.ffill().bfill()

        # Drop any columns (tickers) that still have NaN after filling (meaning no data at all in the range)
        daily_prices = daily_prices.dropna(axis=1, how='all')

        # Check if we still have tickers with data after cleaning
        tickers_with_daily_data = daily_prices.columns.tolist()
        if not tickers_with_daily_data:
             print("No tickers with valid daily price data after resampling and cleaning.")
             return jsonify({
                 "error": f"No valid daily price data found in the database for calculation after cleaning.",
                 "portfolio_name": portfolio.portfolio_name
             }), 404


        # Ensure weights are aligned with the columns of daily_prices and normalized
        # Only include tickers that made it into the daily_prices DataFrame
        weights_list_for_alignment = [weights.get(ticker, 0) for ticker in tickers_with_daily_data]
        aligned_weights = pd.Series(weights_list_for_alignment, index=tickers_with_daily_data)
        sum_aligned_weights = aligned_weights.sum()
        if sum_aligned_weights > 0:
            aligned_weights = aligned_weights / sum_aligned_weights
        else:
            print("Warning: Aligned weights sum to zero. Setting all weights to 0.0.")
            aligned_weights = aligned_weights * 0.0
        # --- Call the financial metrics calculation helper (calculate_portfolio_metrics) ---
        # This helper function takes the daily price data DataFrame and the aligned weights
        # It should handle calculating returns, portfolio values, and all metrics internally.
        try:
            print("Calling financial metrics calculation helper...")
            # Assuming calculate_portfolio_metrics now takes daily price data and weights
            # You might need to adjust the signature of calculate_portfolio_metrics
            metrics_results = calculate_portfolio_metrics(
                daily_prices, # Pass the cleaned daily price data DataFrame
                aligned_weights,
                holdings_list,
                tickers_with_daily_data# Pass the aligned weights
            )
            print("Debug (Backend): metrics_results_dict['asset_metrics_data'] after calc:", metrics_results.get('asset_metrics_data'))
            print("Financial metrics calculation completed.")


        except Exception as metrics_calc_err:
            print(f"Error during financial metrics calculation helper call for portfolio ID {portfolio_id}: {metrics_calc_err}")
            traceback.print_exc()
            return jsonify({
                "error": "An error occurred during financial metrics helper calculation.",
                "portfolio_name": portfolio.portfolio_name
            }), 500


        # --- Structure the JSON Response (formatted_metrics) for the frontend dashboard ---
        print("Structuring JSON response for frontend dashboard...")

        # The calculate_portfolio_metrics helper should return a dictionary containing all the required metrics
        # Adapt this structure based on what your helper function actually returns
        # Example expected structure from helper:
        # {
        #     'portfolio': {'cagr': ..., 'std_dev_annual': ..., ...},
        #     'assets': {ticker: {'cagr': ..., 'std_dev_annual': ..., ...}, ...},
        #     'portfolio_values_series': pandas.Series, # Portfolio value over time
        #     'annual_returns_portfolio': dict, # {year: return}
        #     'monthly_returns_data': dict, # {date_str: {portfolio: return, ticker1: return, ...}}
        #     'risk_contributions_data': dict, # {ticker: contribution}
        #     'return_contributions_data': dict, # {ticker: contribution}
        #     'correlations': pandas.DataFrame, # Correlation matrix
        #     # ... other results ...
        # }

        # Use the results dictionary returned by calculate_portfolio_metrics to build the JSON response
        # Ensure metrics_results is a dictionary before accessing keys
        if not isinstance(metrics_results, dict):
             print("Error: calculate_portfolio_metrics did not return a dictionary.")
             metrics_results = {} # Default to empty dictionary

        formatted_metrics = {
            # Overall portfolio metrics (from metrics_results['portfolio_overall_metrics'])
            "overall_metrics": {
                # Access data directly from 'portfolio_overall_metrics' sub-dictionary
                "portfolio_name": metrics_results.get('portfolio_overall_metrics', {}).get('portfolio_name', portfolio.portfolio_name),
                "Start Balance": float(metrics_results.get('portfolio_overall_metrics', {}).get('start_value', 0.0)) if np.isfinite(metrics_results.get('portfolio_overall_metrics', {}).get('start_value', 0.0)) else 0.0,
                "End Balance": float(metrics_results.get('portfolio_overall_metrics', {}).get('end_value', 0.0)) if np.isfinite(metrics_results.get('portfolio_overall_metrics', {}).get('end_value', 0.0)) else 0.0,
                "Cumulative Return": float(metrics_results.get('portfolio_overall_metrics', {}).get('cumulative_return', 0.0)) if np.isfinite(metrics_results.get('portfolio_overall_metrics', {}).get('cumulative_return', 0.0)) else 0.0,
                # Fix scaling: CAGR is already a decimal in metrics_results, multiply by 100 here
                "Annualized Return (CAGR)": float(metrics_results.get('portfolio_overall_metrics', {}).get('cagr', 0.0)) if np.isfinite(metrics_results.get('portfolio_overall_metrics', {}).get('cagr', 0.0)) else 0.0,
                # Fix scaling: Std Dev is already a decimal in metrics_results, multiply by 100 here
                "Standard Deviation": float(metrics_results.get('portfolio_overall_metrics', {}).get('std_dev_annual', 0.0)) if np.isfinite(metrics_results.get('portfolio_overall_metrics', {}).get('std_dev_annual', 0.0)) else 0.0,
                "Sharpe Ratio": float(metrics_results.get('portfolio_overall_metrics', {}).get('sharpe_ratio', 0.0)) if np.isfinite(metrics_results.get('portfolio_overall_metrics', {}).get('sharpe_ratio', 0.0)) else 0.0,
                 "Sortino Ratio": float(metrics_results.get('portfolio_overall_metrics', {}).get('sortino_ratio', 0.0)) if np.isfinite(metrics_results.get('portfolio_overall_metrics', {}).get('sortino_ratio', 0.0)) else 0.0,
                # Fix scaling: Max Drawdown is already a decimal in metrics_results, multiply by 100 here
                "Maximum Drawdown": float(metrics_results.get('portfolio_overall_metrics', {}).get('max_drawdown_value', 0.0)) if np.isfinite(metrics_results.get('portfolio_overall_metrics', {}).get('max_drawdown_value', 0.0)) else 0.0,
                "Drawdown Start Date": metrics_results.get('portfolio_overall_metrics', {}).get('max_drawdown_start_date', None), # Dates are likely already formatted strings
                "Drawdown End Date": metrics_results.get('portfolio_overall_metrics', {}).get('max_drawdown_end_date', None), # Dates are likely already formatted strings
                "Drawdown Recovery Time": metrics_results.get('portfolio_overall_metrics', {}).get('max_drawdown_recovery_time_months', 'N/A'),
                 "Monthly Positive Periods": metrics_results.get('portfolio_overall_metrics', {}).get('positive_periods', 'N/A'), # Assuming these are already formatted
                "Total Periods": metrics_results.get('portfolio_overall_metrics', {}).get('total_periods', 'N/A'), # Assuming these are already formatted
                "Gain/Loss Ratio": float(metrics_results.get('portfolio_overall_metrics', {}).get('gain_loss_ratio', 0.0)) if np.isfinite(metrics_results.get('portfolio_overall_metrics', {}).get('gain_loss_ratio', 0.0)) else 0.0,
                 # Fix scaling: safe/perpetual withdrawal rates are likely decimals, multiply by 100
                "Safe Withdrawal Rate": float(metrics_results.get('portfolio_overall_metrics', {}).get('safe_withdrawal_rate', 0.0)) if np.isfinite(metrics_results.get('portfolio_overall_metrics', {}).get('safe_withdrawal_rate', 0.0)) else 0.0,
                "Perpetual Withdrawal Rate": float(metrics_results.get('portfolio_overall_metrics', {}).get('perpetual_withdrawal_rate', 0.0)) if np.isfinite(metrics_results.get('portfolio_overall_metrics', {}).get('perpetual_withdrawal_rate', 0.0)) else 0.0,
                "Beta": float(metrics_results.get('portfolio_overall_metrics', {}).get('beta', 0.0)) if np.isfinite(metrics_results.get('portfolio_overall_metrics', {}).get('beta', 0.0)) else 0.0,
                # Fix scaling: Alpha is likely a decimal, multiply by 100
                "Alpha": float(metrics_results.get('portfolio_overall_metrics', {}).get('alpha', 0.0)) if np.isfinite(metrics_results.get('portfolio_overall_metrics', {}).get('alpha', 0.0)) else 0.0,
                "Calmar Ratio": float(metrics_results.get('portfolio_overall_metrics', {}).get('calmar_ratio', 0.0)) if np.isfinite(metrics_results.get('portfolio_overall_metrics', {}).get('calmar_ratio', 0.0)) else 0.0,
                "best_year":   metrics_results['portfolio_overall_metrics']['best_year'],
                "best_year_return":  metrics_results['portfolio_overall_metrics']['best_year_return'],
                "worst_year":  metrics_results['portfolio_overall_metrics']['worst_year'],
                "worst_year_return": metrics_results['portfolio_overall_metrics']['worst_year_return'],
                "Calculation Start Date": metrics_results.get('portfolio_overall_metrics', {}).get('calculation_start_date', None), # Dates are likely already formatted strings
                "Calculation End Date": metrics_results.get('portfolio_overall_metrics', {}).get('calculation_end_date', None), # Dates are likely already formatted strings
                "Initial Investment Used": float(metrics_results.get('portfolio_overall_metrics', {}).get('initial_investment_used', 0.0)) if np.isfinite(metrics_results.get('portfolio_overall_metrics', {}).get('initial_investment_used', 0.0)) else 0.0,
                "calculation_date": metrics_results.get('portfolio_overall_metrics', {}).get('metrics_calculation_date', datetime.now().strftime('%Y-%m-%d')) # Get from backend or default
            },

            # Data for Portfolio Growth Chart (Value over time)
            # Access data directly from 'portfolio_growth_data'
            "portfolio_growth_data": metrics_results.get('portfolio_growth_data', {'dates': [], 'values': []}),

            # Data for Risk/Return Decomposition Tables
            # Access data directly from 'risk_decomposition_data' and 'return_decomposition_data'
            "risk_decomposition_data": metrics_results.get('risk_decomposition_data', []),
            "return_decomposition_data": metrics_results.get('return_decomposition_data', []),

            # Data for Holdings Table (combined from DB holdings and per-asset metrics)
            # Iterate through the original holdings_list, but get metrics from 'asset_metrics_data'

            "holdings_table_data": [
                 {
                    "ticker": h['ticker'],
                    "Name": h['Name'],
                    "Category": h['Category'],
                    "Weight": float(h['Weight']) / 100,
                    "DollarAmount": float(h['DollarAmount']),
                    "PurchaseDate": h['PurchaseDate'],
                    # Get per-asset metrics from the CORRECT nested location
                    # Access the nested 'asset_metrics_data' within 'portfolio_overall_metrics'
                    "Total Return": float(metrics_results.get('portfolio_overall_metrics', {}).get('asset_metrics_data', {}).get(h['ticker'], {}).get('cumulative_return', 0.0)) if np.isfinite(metrics_results.get('portfolio_overall_metrics', {}).get('asset_metrics_data', {}).get(h['ticker'], {}).get('cumulative_return', 0.0)) else 0.0,
                    "Annualized Return (CAGR)": float(metrics_results.get('portfolio_overall_metrics', {}).get('asset_metrics_data', {}).get(h['ticker'], {}).get('cagr', 0.0)) if np.isfinite(metrics_results.get('portfolio_overall_metrics', {}).get('asset_metrics_data', {}).get(h['ticker'], {}).get('cagr', 0.0)) else 0.0,
                    "Standard Deviation": float(metrics_results.get('portfolio_overall_metrics', {}).get('asset_metrics_data', {}).get(h['ticker'], {}).get('std_dev_annual', 0.0)) if np.isfinite(metrics_results.get('portfolio_overall_metrics', {}).get('asset_metrics_data', {}).get(h['ticker'], {}).get('std_dev_annual', 0.0)) else 0.0,
                    "Sharpe Ratio": float(metrics_results.get('portfolio_overall_metrics', {}).get('asset_metrics_data', {}).get(h['ticker'], {}).get('sharpe_ratio', 0.0)) if np.isfinite(metrics_results.get('portfolio_overall_metrics', {}).get('asset_metrics_data', {}).get(h['ticker'], {}).get('sharpe_ratio', 0.0)) else 0.0,
                    "Sortino Ratio": float(metrics_results.get('portfolio_overall_metrics', {}).get('asset_metrics_data', {}).get(h['ticker'], {}).get('sortino_ratio', 0.0)) if np.isfinite(metrics_results.get('portfolio_overall_metrics', {}).get('asset_metrics_data', {}).get(h['ticker'], {}).get('sortino_ratio', 0.0)) else 0.0,
                     "Maximum Drawdown": float(metrics_results.get('portfolio_overall_metrics', {}).get('asset_metrics_data', {}).get(h['ticker'], {}).get('max_drawdown', 0.0)) if np.isfinite(metrics_results.get('portfolio_overall_metrics', {}).get('asset_metrics_data', {}).get(h['ticker'], {}).get('max_drawdown', 0.0)) else 0.0,
                     "Best Year Return": float(metrics_results.get('portfolio_overall_metrics', {}).get('asset_metrics_data', {}).get(h['ticker'], {}).get('best_year_return', 0.0)) if np.isfinite(metrics_results.get('portfolio_overall_metrics', {}).get('asset_metrics_data', {}).get(h['ticker'], {}).get('best_year_return', 0.0)) else 0.0,
                     "Worst Year Return": float(metrics_results.get('portfolio_overall_metrics', {}).get('asset_metrics_data', {}).get(h['ticker'], {}).get('worst_year_return', 0.0)) if np.isfinite(metrics_results.get('portfolio_overall_metrics', {}).get('asset_metrics_data', {}).get(h['ticker'], {}).get('worst_year_return', 0.0)) else 0.0,

                 } for h in holdings_list
            ],

            # Data for Annual and Monthly Returns Tables/Charts
            # Access data directly from 'annual_returns_portfolio' and 'monthly_returns_data'
            # Fix scaling for annual returns here if needed (backend already multiplied by 100)
            "annual_returns_portfolio": metrics_results.get('annual_returns_portfolio', {}), # Backend already multiplied by 100
            "monthly_returns_data": metrics_results.get('monthly_returns_data', {}),

            # Data for Asset-level Metrics Table (from metrics_results['asset_metrics_data'])
            # This seems redundant with holdings_table_data if the same metrics are shown.
            # If you need a separate table, access data from 'asset_metrics_data' and format.
            # If not needed, you can remove this or populate it differently.
            # Assuming you want it, access data from 'asset_metrics_data' and format percentages:
            # Data for Asset-level Metrics Table (should pull from the calculated metrics)
            "asset_metrics_data": { # <-- THIS IS THE TOP-LEVEL KEY THE FRONTEND uses for renderPortfolioAssetsTable
                 # Get calculated asset metrics from the correct nested source
                 # Iterate over the nested asset_metrics_data and map lowercase keys to capitalized keys
                 ticker: {
                    "CAGR": float(metrics.get('cagr', 0.0)) if np.isfinite(metrics.get('cagr', 0.0)) else 0.0,
                    "Standard Deviation": float(metrics.get('std_dev_annual', 0.0)) if np.isfinite(metrics.get('std_dev_annual', 0.0)) else 0.0,
                    "Maximum Drawdown": float(metrics.get('max_drawdown', 0.0)) if np.isfinite(metrics.get('max_drawdown', 0.0)) else 0.0,
                    "Sharpe Ratio": float(metrics.get('sharpe_ratio', 0.0)) if np.isfinite(metrics.get('sharpe_ratio', 0.0)) else 0.0,
                    "Sortino Ratio": float(metrics.get('sortino_ratio', 0.0)) if np.isfinite(metrics.get('sortino_ratio', 0.0)) else 0.0,
                    "Best Year Return": float(metrics.get('best_year_return', 0.0)) if np.isfinite(metrics.get('best_year_return', 0.0)) else 0.0,
                    "Worst Year Return": float(metrics.get('worst_year_return', 0.0)) if np.isfinite(metrics.get('worst_year_return', 0.0)) else 0.0,
                 } for ticker, metrics in metrics_results.get('portfolio_overall_metrics', {}).get('asset_metrics_data', {}).items() # <-- FETCH FROM THE CORRECT NESTED LOCATION
            },


            # Data for Allocation Charts (Assuming sector data is available or can be derived)
            # Access data directly from 'sector_allocation_data' if calculate_portfolio_metrics populates it
            "sector_allocation_data": metrics_results.get('sector_allocation_data', {}),

            # Other potential data: risk correlations, beta/alpha matrices, etc.
            # Access data directly from 'correlations_data'
            "correlations_data": metrics_results.get('correlations_data', {}), # This might need .to_dict() if it's a DataFrame

            # Calculation period and initial investment are already in overall_metrics now
            "calculation_period": metrics_results.get('calculation_period', {}), # Access directly
            "calculation_date": metrics_results.get('metrics_calculation_date', datetime.now().strftime('%Y-%m-%d')) # Access directly or use a default

        }
        correlations_data = formatted_metrics.get('correlations_data', {})
        for ticker, values in correlations_data.items():
            for key, value in values.items():
                if isinstance(value, float) and np.isnan(value):
                    correlations_data[ticker][key] = None # Replace NaN with None
                # Also handle potential Inf values if necessary
                if isinstance(value, float) and (value == float('inf') or value == float('-inf')):
                    correlations_data[ticker][key] = None # Replace Inf with None
        formatted_metrics['correlations_data'] = correlations_data
        print("Structuring JSON response for frontend dashboard completed.")
        print("Debug: formatted_metrics before jsonify:", formatted_metrics)
        return jsonify(formatted_metrics), 200

    except Exception as e:
        import traceback
        print(f"CRITICAL ERROR in get_portfolio_metrics for portfolio ID {portfolio_id} (user {user_id}): {str(e)}")
        print(traceback.format_exc())
        db.session.rollback()
        return jsonify({"error": "An unexpected error occurred while calculating portfolio metrics."}), 500

# --- Your other calculation and charting functions (calculate_returns, generate_efficient_frontier, etc.)
# should remain in this file or be imported if they are in a separate utility file. ---
# Ensure these functions are updated to accept/use the DataFrame format provided by the DB fetch and cleaning.

# The calculate_portfolio_metrics function imported from utils.financial_metrics is called above.
# Ensure its definition matches what is expected (takes daily price data and weights, returns a dictionary of results).