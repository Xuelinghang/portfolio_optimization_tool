# app/routes/efficient_frontier.py

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, jsonify, session, current_app
)
from flask_login import login_required, current_user
from app.market_fetcher import (
    get_historical_data_for_asset,
    fetch_and_map_asset_details,
    fetch_yahoo_data,
    fetch_alpha_vantage_data,
    fetch_alpha_vantage_bond_yield,
    fetch_fred_data,
    fetch_coingecko_data,
)
from app import db
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date, UTC
import traceback
from scipy.optimize import minimize
from sqlalchemy.orm import joinedload
from uuid import uuid4
from app.models import (
    User, Portfolio, Asset, MarketData,
    PortfolioAsset, CalculationResult
)
from utils.financial_metrics import (
    calculate_portfolio_metrics,
    calculate_returns,
    generate_efficient_frontier,
    calculate_asset_metrics,
    calculate_tangency_portfolio,
    calculate_max_info_ratio_portfolio,
    generate_equal_weight_portfolio,
    generate_efficient_frontier_chart,
    generate_transition_map,
)

efficient_frontier_bp = Blueprint('efficient_frontier', __name__)


@efficient_frontier_bp.route('/', methods=['GET'])
@login_required
def efficient_frontier_page():
    """Display the efficient frontier tool input page."""
    user_id = current_user.id
    username = current_user.username
    try:
        portfolios = (
            Portfolio.query
            .filter_by(user_id=user_id)
            .options(joinedload(Portfolio.holdings).joinedload(PortfolioAsset.asset))
            .all()
        )
    except Exception as e:
        current_app.logger.error(f"Error fetching portfolios: {e}")
        traceback.print_exc()
        db.session.rollback()
        flash('Error loading portfolios. Please try again.', 'danger')
        portfolios = []

    return render_template(
        'efficient_frontier.html',
        portfolios=portfolios,
        username=username
    )


@efficient_frontier_bp.route('/calculate', methods=['POST'])
@login_required
def calculate_efficient_frontier():
    """
    Handle calculation requests: existing saved portfolio or new temporary portfolio.
    """
    user_id = current_user.id
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data received'}), 400

    # 1. Read incoming payload
    portfolio_id = data.get('portfolio_id')
    new_data     = data.get('new_portfolio_data')

    # 2. Initialize common vars
    portfolio       = None
    tickers         = []
    portfolio_name  = "Custom Portfolio"
    start_date      = None
    end_date        = None
    holdings_list   = []

    # 3A. Branch: existing saved portfolio
    if portfolio_id:
        try:
            portfolio = (
                Portfolio.query
                .filter_by(id=portfolio_id, user_id=user_id)
                .options(joinedload(Portfolio.holdings).joinedload(PortfolioAsset.asset))
                .first()
            )
            if not portfolio:
                return jsonify({'error': 'Portfolio not found or unauthorized'}), 404

            portfolio_name = portfolio.portfolio_name
            for h in portfolio.holdings:
                if h.asset and h.asset.symbol:
                    tick = h.asset.symbol.upper()
                    tickers.append(tick)
                    holdings_list.append({
                        'ticker': tick,
                        'Name':    h.asset.company_name or tick,
                        'Category':h.asset.asset_type  or 'Unknown',
                        'Weight':  float(h.allocation_pct  or 0.0),
                        'DollarAmount': float(h.dollar_amount or 0.0),
                        'PurchaseDate': h.purchase_date.strftime('%Y-%m-%d') if h.purchase_date else None
                    })

            sd = data.get('start_date'); ed = data.get('end_date')
            start_date = pd.to_datetime(sd) if sd else None
            end_date   = pd.to_datetime(ed) if ed else None
            if start_date is None:
                dates = [h.purchase_date for h in portfolio.holdings if h.purchase_date]
                if dates:
                    start_date = datetime.combine(min(dates), datetime.min.time(), tzinfo=UTC)
            if end_date is None:
                end_date = datetime.now(UTC)

        except Exception as e:
            current_app.logger.error(f"Error loading existing portfolio: {e}")
            traceback.print_exc()
            db.session.rollback()
            return jsonify({'error': 'Error fetching portfolio details'}), 500

    # 3B. Branch: new temporary portfolio
    elif new_data:
        portfolio_name = new_data.get('name', portfolio_name)
        entries = new_data.get('assets', [])
        if not entries:
            return jsonify({'error': 'No assets provided for calculation'}), 400

        for entry in entries:
            t      = entry.get('ticker')
            amt    = entry.get('amount')
            pd_str = entry.get('purchase_date')
            if not t or amt is None:
                continue
            try:
                amt = float(amt)
                if amt <= 0: continue
            except:
                continue

            ticker = t.strip().upper()
            asset_obj = Asset.query.filter_by(symbol=ticker, user_id=user_id).first()
            if asset_obj:
                name = asset_obj.company_name or ticker
                cat  = asset_obj.asset_type    or 'Unknown'
            else:
                try:
                    details = fetch_and_map_asset_details(ticker)
                    name = details.get('name', ticker)
                    cat  = details.get('type', 'Unknown')
                except:
                    name = ticker
                    cat  = 'Unknown'

            tickers.append(ticker)
            holdings_list.append({
                'ticker': ticker,
                'Name':    name,
                'Category':cat,
                'Weight':  0.0,
                'DollarAmount': amt,
                'PurchaseDate': pd_str
            })

        if not holdings_list:
            return jsonify({'error': 'No valid assets provided'}), 400

        dates = [
            pd.to_datetime(h['PurchaseDate']).date()
            for h in holdings_list if h.get('PurchaseDate')
        ]
        start_date = min(dates) if dates else None
        end_date   = datetime.now(UTC)

    else:
        return jsonify({'error': 'Select a portfolio or provide asset data'}), 400

    # 4. Dedupe tickers & holdings
    seen = set()
    unique_holdings = []
    for h in holdings_list:
        t = h['ticker']
        if t not in seen:
            seen.add(t)
            unique_holdings.append(h)
    tickers = list(seen)
    holdings_list = unique_holdings

    # 5. Fetch historical prices
    historical = {}
    db_assets = {
        a.symbol.upper(): a
        for a in Asset.query.filter(Asset.symbol.in_(tickers), Asset.user_id == user_id).all()
    }
    for ticker in tickers:
        asset_obj = db_assets.get(ticker)
        if not asset_obj:
            continue
        df = get_historical_data_for_asset(
            asset_obj.id, start_date=start_date, end_date=end_date
        )
        if isinstance(df, pd.DataFrame) and not df.empty:
            historical[ticker] = df['price']

    price_df = pd.DataFrame(historical)
    if price_df.empty:
        return jsonify({'error': 'No sufficient historical data available for calculation'}), 400

    # 6. Clean & align prices
    price_df.index = pd.to_datetime(price_df.index)
    price_df = (
        price_df
        .resample('D').last()
        .ffill().bfill()
        .dropna(axis=1, how='all')
    )
    tickers_with_data = price_df.columns.tolist()
    if not tickers_with_data:
        return jsonify({'error': 'No valid daily price data after cleaning'}), 404

    # 7. Compute initial weights
    initial_amounts = {}
    if portfolio:
        for h in portfolio.holdings:
            t = h.asset.symbol.upper()
            if t in tickers_with_data:
                initial_amounts[t] = h.dollar_amount or 0.0
    else:
        for h in holdings_list:
            t = h['ticker']
            if t in tickers_with_data:
                initial_amounts[t] = h['DollarAmount']

    total_amt = sum(initial_amounts.values())
    if total_amt <= 0:
        weights = np.array([1/len(tickers_with_data)] * len(tickers_with_data))
    else:
        weights = np.array([
            initial_amounts.get(t, 0.0) / total_amt
            for t in tickers_with_data
        ])
    weights_series = pd.Series(weights, index=tickers_with_data)

    # 8. Calculate metrics, frontier, and save results
    try:
        metrics_results        = calculate_portfolio_metrics(
                                    price_df, weights_series, holdings_list, tickers_with_data
                                )
        portfolio_values       = (price_df * weights_series.values).sum(axis=1)
        returns_data           = calculate_returns(price_df)
        efficient_portfolios   = generate_efficient_frontier(returns_data)
        asset_metrics_df       = calculate_asset_metrics(returns_data)
        tangency_portfolio     = calculate_tangency_portfolio(returns_data)
        max_info_portfolio     = calculate_max_info_ratio_portfolio(returns_data)
        equal_weight_portfolio = generate_equal_weight_portfolio(returns_data)

        # 8A. Build the base payload
        results_for_save = {
            'portfolio_name':           portfolio_name,
            **metrics_results,
            'efficient_portfolios':     efficient_portfolios.to_dict(orient='records'),
            'asset_metrics':            asset_metrics_df.to_dict(orient='records'),
            'tangency_portfolio':       tangency_portfolio,
            'max_info_portfolio':       max_info_portfolio,
            'equal_weight_portfolio':   equal_weight_portfolio
        }

        # 8B. Add tickers & correlations
        cor_matrix = price_df.corr()
        results_for_save['tickers']            = tickers_with_data
        results_for_save['correlations_data']  = cor_matrix.to_dict()

        # 8C. Add ticker → company‐name map for correlations “Name” column
        ticker_names = {h['ticker']: h['Name'] for h in holdings_list}
        results_for_save['ticker_names']       = ticker_names

        # 9. Persist and return
        rec = CalculationResult(
            id=str(uuid4()),
            user_id=user_id,
            timestamp=datetime.now(UTC),
            results_data=results_for_save
        )
        db.session.add(rec)
        db.session.commit()

        return jsonify({
            'redirect': url_for(
                'efficient_frontier.efficient_frontier_results_page',
                result_id=rec.id
            )
        }), 200

    except Exception as e:
        current_app.logger.error(f"CRITICAL ERROR during calculation: {e}")
        traceback.print_exc()
        db.session.rollback()
        return jsonify({
            'error': 'An unexpected error occurred during calculation.'
        }), 500


@efficient_frontier_bp.route('/results/<string:result_id>', methods=['GET'])
def efficient_frontier_results_page(result_id):
    """Render the results page for a completed calculation."""
    if 'user_id' not in session:
        flash('Please log in to access this page', 'warning')
        return redirect(url_for('auth.login_page'))

    user_id = session['user_id']
    rec = CalculationResult.query.filter_by(
        id=result_id,
        user_id=user_id
    ).first()
    if not rec:
        flash('Results not found or unauthorized.', 'warning')
        return redirect(url_for('efficient_frontier.efficient_frontier_page'))

    # Load the JSON we saved earlier
    data = rec.results_data

    # Rebuild DataFrames for chart generators
    ef_df     = pd.DataFrame(data.get('efficient_portfolios', []))
    assets_df = pd.DataFrame(data.get('asset_metrics', []))

    # Generate the two Plotly chart snippets
    ef_chart_html         = generate_efficient_frontier_chart(
                                ef_df,
                                data.get('tangency_portfolio', {}),
                                data.get('max_info_portfolio', {}),
                                assets_df
                            )
    transition_map_chart  = generate_transition_map(ef_df)

    # Pull out correlations table data
    tickers      = data.get('tickers', [])
    correlations = data.get('correlations_data', {})

    # And now the new ticker → company-name map
    ticker_names = data.get('ticker_names', {})

    # Finally render
    return render_template(
        'efficient_frontier_results.html',

        # Chart placeholders
        efficient_frontier_chart = ef_chart_html,
        transition_map_chart     = transition_map_chart,

        # Correlation table data
        tickers     = tickers,
        correlations= correlations,
        ticker_names= ticker_names,

        # Tab data
        efficient_portfolios    = data.get('efficient_portfolios', []),
        asset_metrics           = data.get('asset_metrics', []),
        tangency_portfolio      = data.get('tangency_portfolio', {}),
        max_info_portfolio      = data.get('max_info_portfolio', {}),
        equal_weight_portfolio  = data.get('equal_weight_portfolio', {}),

        # Date range display
        start_date = data.get('calculation_period', {}).get('start_date'),
        end_date   = data.get('calculation_period', {}).get('end_date'),
    )
