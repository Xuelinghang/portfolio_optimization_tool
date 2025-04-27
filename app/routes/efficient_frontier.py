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
    user_id = current_user.id
    data    = request.get_json()
    if not data:
        return jsonify({'error': 'No data received'}), 400

    # --- 1) Build tickers & holdings_list ---
    portfolio_id    = data.get('portfolio_id')
    new_data        = data.get('new_portfolio_data')
    portfolio       = None
    tickers         = []
    portfolio_name  = "Custom Portfolio"
    start_date      = None
    end_date        = None
    holdings_list   = []

    # existing portfolio branch
    if portfolio_id:
        try:
            portfolio = (
                Portfolio.query
                .filter_by(id=portfolio_id, user_id=user_id)
                .options(joinedload(Portfolio.holdings)
                         .joinedload(PortfolioAsset.asset))
                .first()
            )
            if not portfolio:
                return jsonify({'error': 'Portfolio not found'}), 404

            portfolio_name = portfolio.portfolio_name
            for h in portfolio.holdings:
                sym = h.asset.symbol.upper()
                tickers.append(sym)
                holdings_list.append({
                    'ticker':       sym,
                    'Name':         h.asset.company_name or sym,
                    'Category':     h.asset.asset_type   or 'Unknown',
                    'Weight':       float(h.allocation_pct or 0),
                    'DollarAmount': float(h.dollar_amount  or 0),
                    'PurchaseDate': (h.purchase_date.strftime('%Y-%m-%d')
                                     if h.purchase_date else None)
                })

            sd = data.get('start_date'); ed = data.get('end_date')
            start_date = pd.to_datetime(sd) if sd else None
            end_date   = pd.to_datetime(ed) if ed else None

            if start_date is None:
                dates = [h.purchase_date for h in portfolio.holdings
                         if h.purchase_date]
                if dates:
                    start_date = datetime.combine(
                        min(dates),
                        datetime.min.time(),
                        tzinfo=UTC
                    )
            if end_date is None:
                end_date = datetime.now(UTC)

        except Exception:
            current_app.logger.exception("Error loading existing portfolio")
            db.session.rollback()
            return jsonify({'error': 'Error fetching portfolio'}), 500

    # new portfolio branch
    elif new_data:
        portfolio_name = new_data.get('name', portfolio_name)
        entries        = new_data.get('assets', [])
        if not entries:
            return jsonify({'error': 'No assets provided'}), 400

        for entry in entries:
            sym    = entry.get('ticker','').strip().upper()
            amt    = entry.get('amount')
            pd_str = entry.get('purchase_date')
            if not sym or amt is None:
                continue
            try:
                amt = float(amt)
                if amt <= 0:
                    continue
            except:
                continue

            asset_obj = Asset.query.filter_by(
                symbol=sym, user_id=user_id
            ).first()
            if asset_obj:
                name = asset_obj.company_name or sym
                cat  = asset_obj.asset_type    or 'Unknown'
            else:
                name, cat = sym, 'Unknown'

            tickers.append(sym)
            holdings_list.append({
                'ticker':       sym,
                'Name':         name,
                'Category':     cat,
                'Weight':       0.0,
                'DollarAmount': amt,
                'PurchaseDate': pd_str
            })

        if not holdings_list:
            return jsonify({'error': 'No valid assets'}), 400

        dates      = [pd.to_datetime(h['PurchaseDate']).date()
                      for h in holdings_list if h['PurchaseDate']]
        start_date = min(dates) if dates else None
        end_date   = datetime.now(UTC)

    else:
        return jsonify({'error': 'Select or provide a portfolio'}), 400

    # dedupe tickers/holdings
    seen, unique = set(), []
    for h in holdings_list:
        t = h['ticker']
        if t not in seen:
            seen.add(t)
            unique.append(h)
    tickers       = list(seen)
    holdings_list = unique

    # --- 2) Fetch historical price series from DB ---
    historical = {}
    db_assets  = {
        a.symbol.upper(): a
        for a in Asset.query
                     .filter(Asset.symbol.in_(tickers),
                             Asset.user_id==user_id)
                     .all()
    }
    for sym in tickers:
        a = db_assets.get(sym)
        if not a:
            continue
        df = get_historical_data_for_asset(
            a.id, start_date=start_date, end_date=end_date
        )
        if isinstance(df, pd.DataFrame) and 'price' in df:
            historical[sym] = df['price']

    price_df = pd.DataFrame(historical)
    if price_df.empty:
        return jsonify({'error': 'Insufficient historical data'}), 400

    # --- 3) Inject SPY for calculation only ---
    spy_asset = Asset.query.filter_by(symbol='SPY').first()
    if spy_asset:
        df_spy = get_historical_data_for_asset(
            spy_asset.id, start_date=start_date, end_date=end_date
        )
        spy_ser = df_spy['price'] if 'price' in df_spy else df_spy.iloc[:,0]
    else:
        tmp = fetch_alpha_vantage_data(
            'SPY', start_date=start_date, end_date=end_date
        )
        if not tmp:
            return jsonify({'error': 'Failed SPY fetch'}), 500
        if isinstance(tmp, pd.DataFrame):
            spy_ser = tmp.get('price') or tmp.get('close') or tmp.iloc[:,0]
        elif isinstance(tmp, dict):
            spy_ser = pd.Series(tmp.get('close') or tmp.get('price'))
        else:
            return jsonify({'error': 'Bad SPY format'}), 500

    spy_ser.index = pd.to_datetime(spy_ser.index)
    if spy_ser.index.tz is None:
        spy_ser = spy_ser.tz_localize(UTC)
    else:
        spy_ser = spy_ser.tz_convert(UTC)

    spy_aligned     = spy_ser.reindex(price_df.index).ffill().bfill()
    price_df['SPY'] = spy_aligned

    # --- 4) Clean, resample, compute returns ---
    price_df = (
        price_df
        .resample('D').last()
        .ffill().bfill()
        .dropna(axis=1, how='all')
    )
    returns_data = calculate_returns(price_df)

    # --- 4a) Prepare UI-only tickers & correlations (drop SPY) ---
    ui_df      = price_df.drop(columns=['SPY'], errors='ignore')
    ui_tickers = ui_df.columns.tolist()
    corrs      = ui_df.corr().to_dict()

    # build ticker → name map
    ticker_names = {
        h['ticker']: h['Name']
        for h in holdings_list
        if h['ticker'] in ui_tickers
    }

    # --- 5) Weights for only UI assets (no SPY) ---
    initial_amounts = {}
    if portfolio:
        for h in portfolio.holdings:
            s = h.asset.symbol.upper()
            if s in ui_tickers:
                initial_amounts[s] = h.dollar_amount or 0
    else:
        for h in holdings_list:
            s = h['ticker']
            if s in ui_tickers:
                initial_amounts[s] = h['DollarAmount']

    total_amt = sum(initial_amounts.values())
    if total_amt <= 0:
        w = np.ones(len(ui_tickers)) / len(ui_tickers)
    else:
        w = np.array([initial_amounts.get(t, 0)/total_amt
                      for t in ui_tickers])
    weights_series = pd.Series(w, index=ui_tickers)

    # --- 6) Calculate and save everything ---
    try:
        metrics_results        = calculate_portfolio_metrics(
            price_df, weights_series, holdings_list, ui_tickers
        )
        efficient_portfolios   = generate_efficient_frontier(returns_data)
        asset_metrics_df       = calculate_asset_metrics(returns_data)
        tangency_portfolio     = calculate_tangency_portfolio(returns_data)
        max_info_portfolio     = calculate_max_info_ratio_portfolio(returns_data)
        equal_weight_portfolio = generate_equal_weight_portfolio(returns_data)

        results_for_save = {
            
            'portfolio_name':          portfolio_name,
            'start_date':              start_date.isoformat() if start_date else None,
            'end_date':                end_date.isoformat()   if end_date   else None,
            **metrics_results,
            'efficient_portfolios':    efficient_portfolios.to_dict(orient='records'),
            'asset_metrics':           asset_metrics_df.to_dict(orient='records'),
            'tangency_portfolio':      tangency_portfolio,
            'max_info_portfolio':      max_info_portfolio,
            'equal_weight_portfolio':  equal_weight_portfolio,
            'tickers':                 ui_tickers,
            'correlations_data':       corrs,
            'ticker_names':            ticker_names
        }

        rec = CalculationResult(
            id           = str(uuid4()),
            user_id      = user_id,
            timestamp    = datetime.now(UTC),
            results_data = results_for_save
        )
        db.session.add(rec)
        db.session.commit()

        return jsonify({
            'redirect': url_for(
                'efficient_frontier.efficient_frontier_results_page',
                result_id=rec.id
            )
        }), 200

    except Exception:
        current_app.logger.exception("CRITICAL ERROR during calculation")
        db.session.rollback()
        return jsonify({'error': 'An unexpected error occurred'}), 500

@efficient_frontier_bp.route('/results/<string:result_id>', methods=['GET'])
def efficient_frontier_results_page(result_id):
    """Render the results page for a completed calculation."""
    # Using session check instead of @login_required decorator here
    if 'user_id' not in session:
        flash('Please log in to access this page', 'warning')
        return redirect(url_for('auth.login_page')) # Adjust 'auth.login_page' if needed

    user_id = session['user_id'] # Get user_id from session

    # Fetch the result record
    try:
        rec = CalculationResult.query.filter_by(
            id=result_id,
            user_id=user_id
        ).first()
    except Exception as e:
        current_app.logger.error(f"Database error fetching CalculationResult id {result_id} for user {user_id}: {e}")
        flash('An error occurred while retrieving results. Please try again later.', 'danger')
        return redirect(url_for('efficient_frontier.efficient_frontier_page')) # Redirect to input page on DB error

    if not rec:
        flash('Results not found or you are not authorized to view them.', 'warning')
        return redirect(url_for('efficient_frontier.efficient_frontier_page'))

    # Load the results data
    data = rec.results_data
    if not data or not isinstance(data, dict):
        current_app.logger.error(f"Results data is missing or invalid for calculation id: {result_id}")
        flash('Calculation data is missing or corrupted.', 'danger')
        return redirect(url_for('efficient_frontier.efficient_frontier_page'))


    # Rebuild DataFrames for chart generators if needed by the functions
    # Ensure functions handle potential missing data gracefully
    try:
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
    except Exception as e:
        current_app.logger.exception(f"Error generating charts for calculation id {result_id}: {e}")
        flash('Error generating charts for display.', 'warning')
        # Set charts to None or empty strings so the template doesn't break
        ef_chart_html = None
        transition_map_chart = None


    # --- Extract data for template ---
    # Use .get() with defaults for robustness

    # Tickers, Correlations, Names
    tickers      = data.get('tickers', []) # Variable name is 'tickers'
    correlations = data.get('correlations_data', {}) # Variable name is 'correlations'
    ticker_names = data.get('ticker_names', {})

    # Portfolio Metrics & Specific Portfolios
    efficient_portfolios    = data.get('efficient_portfolios', [])
    asset_metrics           = data.get('asset_metrics', [])
    tangency_portfolio      = data.get('tangency_portfolio', {})
    max_info_portfolio      = data.get('max_info_portfolio', {})
    equal_weight_portfolio  = data.get('equal_weight_portfolio', {})

    start_date = data.get('start_date')
    end_date   = data.get('end_date')


    # --- Render the template ---
    try:
        return render_template(
            'efficient_frontier_results.html', # Verify this template path

            # Chart placeholders
            efficient_frontier_chart = ef_chart_html,
            transition_map_chart     = transition_map_chart,

            # Correlation table data - FIXES APPLIED HERE
            tickers=tickers,          # Use the variable 'tickers'
            correlations=correlations, # Use the variable 'correlations'
            ticker_names=ticker_names,

            # Tab data
            efficient_portfolios    = efficient_portfolios,
            asset_metrics           = asset_metrics,
            tangency_portfolio      = tangency_portfolio,
            max_info_portfolio      = max_info_portfolio,
            equal_weight_portfolio  = equal_weight_portfolio,

            # Date range display (pass None if not available)
            start_date = start_date,
            end_date   = end_date,

            # Pass other useful info if needed by the template
            portfolio_name = data.get('portfolio_name', 'Analysis Results'),
            calculation_timestamp = rec.timestamp
        )
    except Exception as e:
        # Catch potential Jinja2 rendering errors
        current_app.logger.exception(f"Error rendering results template for calculation id {result_id}: {e}")
        flash('An error occurred while displaying the results page.', 'danger')
        return redirect(url_for('efficient_frontier.efficient_frontier_page'))
