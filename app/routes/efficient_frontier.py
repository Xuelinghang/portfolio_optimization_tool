from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, current_app, g
from app.models import User, Portfolio, Asset, MarketData
from app import db
import json
import pandas as pd
import numpy as np
from datetime import datetime
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import plotly.io as pio
from scipy.optimize import minimize
import json

# Create Blueprint
efficient_frontier_bp = Blueprint('efficient_frontier', __name__)

@efficient_frontier_bp.route('/efficient-frontier', methods=['GET'])
def efficient_frontier_page():
    """Display the efficient frontier tool input page"""
    # Get current date for max date input
    current_date = datetime.now().strftime('%Y-%m')
    
    # Get all portfolios for the logged-in user
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to access this page', 'warning')
        return redirect(url_for('login_page'))
    
    # Use current_app to ensure we're in the correct app context
    with current_app.app_context():
        portfolios = Portfolio.query.filter_by(user_id=user_id).all()
    
    return render_template('efficient_frontier.html', 
                          portfolios=portfolios,
                          current_date=current_date)

@efficient_frontier_bp.route('/efficient-frontier/calculate', methods=['POST'])
def calculate_efficient_frontier():
    """Calculate and display the efficient frontier"""
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to access this page', 'warning')
        return redirect(url_for('login_page'))
    
    # Get form data
    start_year = request.form.get('start_year')
    start_month = request.form.get('start_month', '01')  # Default to January
    end_year = request.form.get('end_year')
    end_month = request.form.get('end_month', '01')  # Default to January
    
    # Format date strings
    start_date = f"{start_year}-{start_month}-01"
    end_date = f"{end_year}-{end_month}-01"
    
    # Check if using existing portfolio or creating a new one
    use_existing = request.form.get('portfolio_option') == 'existing'
    
    if use_existing:
        portfolio_id = request.form.get('portfolio_id')
        if not portfolio_id:
            flash('Please select a portfolio', 'warning')
            return redirect(url_for('efficient_frontier.efficient_frontier_page'))
        
        # Use current_app to ensure we're in the correct app context
        with current_app.app_context():
            # Get portfolio data directly
            portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=user_id).first()
        
        if not portfolio:
            flash('Portfolio not found', 'warning')
            return redirect(url_for('efficient_frontier.efficient_frontier_page'))
        
        portfolio_data = json.loads(portfolio.portfolio_data)
        # Handle different portfolio data structures
        if isinstance(portfolio_data, list):
            # Handle list format
            tickers = [item['ticker'] for item in portfolio_data]
        elif isinstance(portfolio_data, dict) and 'assets' in portfolio_data:
            # Handle dict format with 'assets' key
            tickers = [item['ticker'] for item in portfolio_data['assets']]
        else:
            # Fallback to manual extraction
            tickers = []
            if isinstance(portfolio_data, dict):
                for entry in portfolio_data:
                    if isinstance(entry, dict) and 'ticker' in entry:
                        tickers.append(entry['ticker'])

            
            if not tickers:
                flash('Portfolio format not recognized. Please enter tickers manually.', 'warning')
                return redirect(url_for('efficient_frontier.efficient_frontier_page'))
        
    else:
        # Parse the tickers from the form
        tickers_input = request.form.get('tickers', '')
        tickers = [ticker.strip().upper() for ticker in tickers_input.split(',') if ticker.strip()]
        
        if not tickers:
            flash('Please enter at least one ticker', 'warning')
            return redirect(url_for('efficient_frontier.efficient_frontier_page'))
    
    # Calculate efficient frontier
    try:
        # Fetch historical data for the tickers
        historical_data = fetch_historical_data(tickers, start_date, end_date)
        
        # Calculate returns
        returns_data = calculate_returns(historical_data)
        
        # Generate efficient frontier portfolios
        efficient_portfolios = generate_efficient_frontier(returns_data)
        
        # Calculate asset metrics
        asset_metrics = calculate_asset_metrics(returns_data)
        
        # Calculate asset correlations
        correlations = returns_data.corr()
        
        # Calculate tangency and max info ratio portfolios
        tangency_portfolio = calculate_tangency_portfolio(returns_data)
        max_info_portfolio = calculate_max_info_ratio_portfolio(returns_data)
        
        # Generate charts for the efficient frontier
        efficient_frontier_chart = generate_efficient_frontier_chart(efficient_portfolios, tangency_portfolio, max_info_portfolio, asset_metrics)
        transition_map_chart = generate_transition_map(efficient_portfolios)
        
        # Convert dataframes to JSON for passing to template
        efficient_portfolios_json = efficient_portfolios.to_json(orient='records')
        asset_metrics_json = asset_metrics.to_json(orient='records')
        correlations_json = correlations.to_json()
        
        # Generate equal-weight portfolio for comparison
        equal_weight_portfolio = generate_equal_weight_portfolio(returns_data)
        
        # Return the template with the results
        return render_template(
            'efficient_frontier_results.html',
            start_date=start_date,
            end_date=end_date,
            efficient_frontier_chart=efficient_frontier_chart,
            transition_map_chart=transition_map_chart,
            asset_metrics=asset_metrics.to_dict(orient='records'),
            correlations=correlations.to_dict(),
            efficient_portfolios=efficient_portfolios.to_dict(orient='records'),
            tangency_portfolio=tangency_portfolio,
            max_info_portfolio=max_info_portfolio,
            equal_weight_portfolio=equal_weight_portfolio,
            tickers=tickers
        )
        
    except Exception as e:
        flash(f'Error calculating efficient frontier: {str(e)}', 'danger')
        return redirect(url_for('efficient_frontier.efficient_frontier_page'))

def fetch_historical_data(tickers, start_date, end_date):
    """
    Fetch historical price data for the given tickers and date range
    
    Args:
        tickers: List of ticker symbols
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)
        
    Returns:
        DataFrame with historical price data
    """
    # This is a placeholder function - in a real implementation, you would 
    # fetch data from your database or from a financial API
    
    # For demo purposes, we'll generate random data
    # In production, replace this with actual data fetching logic
    start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
    end_datetime = datetime.strptime(end_date, '%Y-%m-%d')
    
    # Create a date range (changed from 'M' to 'ME' as 'M' is deprecated)
    date_range = pd.date_range(start=start_datetime, end=end_datetime, freq='ME')
    
    # Initialize DataFrame with dates as index
    data = pd.DataFrame(index=date_range)
    
    # Fetch data for each ticker
    for ticker in tickers:
        # Use app context to query database
        with current_app.app_context():
            # Get asset data from database directly
            asset = Asset.query.filter_by(symbol=ticker.upper()).first()
            
            if asset:
                # Get historical prices from database directly
                prices = MarketData.query.filter(
                    MarketData.asset_id == asset.id,
                    MarketData.date >= start_datetime,
                    MarketData.date <= end_datetime
                ).order_by(MarketData.date).all()
                
                # Create price series
                dates = [price.date for price in prices]
                values = [price.price for price in prices]
                
                if dates and values:
                    price_series = pd.Series(values, index=dates).sort_index()
                    price_series = price_series[~price_series.index.duplicated(keep='first')]
                    data[ticker] = price_series.reindex(date_range, method='ffill')
        
    # Replace any remaining NaN values with forward fill, then backward fill
    # Fix deprecated fillna method
    data = data.ffill().bfill()
    
    # If data is completely empty, generate price data
    if data.empty:
        for ticker in tickers:
            # Generate random price series with an upward trend
            start_price = np.random.uniform(50, 200)
            monthly_returns = np.random.normal(0.01, 0.05, size=len(date_range))
            price_series = start_price * np.cumprod(1 + monthly_returns)
            data[ticker] = price_series
    # Check if there are any NaN values and fill them
    elif data.isna().values.any():
        for ticker in tickers:
            if ticker in data.columns and data[ticker].isna().any():
                # If we have partial data for this ticker, fill gaps
                if not data[ticker].isna().all():
                    data[ticker] = data[ticker].ffill().bfill()
                else:
                    # Generate data for this ticker only
                    start_price = np.random.uniform(50, 200)
                    monthly_returns = np.random.normal(0.01, 0.05, size=len(date_range))
                    price_series = start_price * np.cumprod(1 + monthly_returns)
                    data[ticker] = price_series
    
    return data

def calculate_returns(price_data):
    """
    Calculate monthly returns from price data
    
    Args:
        price_data: DataFrame with historical price data
        
    Returns:
        DataFrame with monthly returns
    """
    # Calculate monthly returns
    returns = price_data.pct_change().dropna()
    return returns

def generate_efficient_frontier(returns_data, num_portfolios=20):
    """
    Generate portfolios along the efficient frontier
    
    Args:
        returns_data: DataFrame with asset returns
        num_portfolios: Number of portfolios to generate
        
    Returns:
        DataFrame with portfolio weights and metrics
    """
    try:
        # Basic data cleaning and validation
        if returns_data is None or returns_data.empty or returns_data.shape[1] <= 1:
            print("Insufficient data for efficient frontier: Need multiple assets with returns data")
            return pd.DataFrame(columns=['Return', 'Risk', 'Sharpe Ratio', 'Active Return', 'Tracking Error', 'Information Ratio'])
            
        # Drop any columns with all NaN values
        returns_data = returns_data.dropna(axis=1, how='all')
        
        # Calculate mean returns and covariance matrix
        mean_returns = returns_data.mean()
        cov_matrix = returns_data.cov()
        num_assets = len(mean_returns)
        risk_free_rate = 0.02 / 12  # Monthly risk-free rate (2% annual)
        
        # Identify benchmark (SPY) if present
        benchmark_idx = None
        for i, ticker in enumerate(returns_data.columns):
            if ticker.upper() == 'SPY':
                benchmark_idx = i
                break
                
        # Create results DataFrame columns
        asset_cols = list(returns_data.columns)
        metric_cols = ['Return', 'Risk', 'Sharpe Ratio', 'Active Return', 'Tracking Error', 'Information Ratio']
        all_cols = asset_cols + metric_cols
        
        # Initialize results DataFrame
        results = pd.DataFrame(columns=all_cols)
        
        # Portfolio metrics calculation function
        def calculate_portfolio_metrics(weights):
            weights = np.array(weights)
            
            # Basic return and risk calculation
            portfolio_return = np.sum(mean_returns * weights) * 12  # Annualized
            portfolio_risk = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights))) * np.sqrt(12)  # Annualized
            
            # Handle potential division by zero in Sharpe calculation
            if portfolio_risk > 0:
                sharpe_ratio = (portfolio_return - risk_free_rate * 12) / portfolio_risk
            else:
                sharpe_ratio = 0
                
            # Default values for tracking metrics
            active_return = 0
            tracking_error = 0
            info_ratio = 0
                
            # Calculate benchmark-relative metrics if benchmark exists
            if benchmark_idx is not None:
                # Benchmark return
                benchmark_return = mean_returns.iloc[benchmark_idx] * 12
                active_return = portfolio_return - benchmark_return
                
                # Calculate tracking error
                benchmark_returns = returns_data.iloc[:, benchmark_idx].values
                tracking_error_cov = np.zeros((num_assets, num_assets))
                
                for i in range(num_assets):
                    for j in range(num_assets):
                        # Get excess returns vs benchmark
                        excess_i = returns_data.iloc[:, i].values - benchmark_returns
                        excess_j = returns_data.iloc[:, j].values - benchmark_returns
                        tracking_error_cov[i, j] = np.cov(excess_i, excess_j)[0, 1]
                
                # Calculate portfolio tracking error
                tracking_error = np.sqrt(np.dot(weights.T, np.dot(tracking_error_cov, weights))) * np.sqrt(12)
                
                # Information ratio (handle division by zero)
                if tracking_error > 0:
                    info_ratio = active_return / tracking_error
                    
            return portfolio_return, portfolio_risk, sharpe_ratio, active_return, tracking_error, info_ratio
        
        # Optimization constraint: weights sum to 1
        def weights_sum_to_one(weights):
            return np.sum(weights) - 1
            
        # Set bounds and initial weights
        bounds = tuple((0, 1) for _ in range(num_assets))
        initial_weights = np.array([1.0/num_assets] * num_assets)
        constraint = {'type': 'eq', 'fun': weights_sum_to_one}
        
        # Minimum variance portfolio
        min_var_function = lambda weights: calculate_portfolio_metrics(weights)[1]  # Return risk (index 1)
        min_var_result = minimize(min_var_function, initial_weights, method='SLSQP', 
                                   bounds=bounds, constraints=constraint)
                                   
        if min_var_result['success']:
            min_var_weights = min_var_result['x']
            min_var_metrics = calculate_portfolio_metrics(min_var_weights)
            min_variance_return = min_var_metrics[0]
            
            # Add minimum variance portfolio to results
            min_var_row = list(min_var_weights) + list(min_var_metrics)
            results = pd.concat([results, pd.DataFrame([min_var_row], columns=all_cols)], ignore_index=True)
            
            # Maximum Sharpe ratio portfolio
            neg_sharpe_function = lambda weights: -calculate_portfolio_metrics(weights)[2]  # Negative Sharpe (index 2)
            max_sharpe_result = minimize(neg_sharpe_function, initial_weights, method='SLSQP', 
                                         bounds=bounds, constraints=constraint)
                                         
            if max_sharpe_result['success']:
                max_sharpe_weights = max_sharpe_result['x']
                max_sharpe_metrics = calculate_portfolio_metrics(max_sharpe_weights)
                max_sharpe_return = max_sharpe_metrics[0]
                
                # Add maximum Sharpe portfolio to results
                max_sharpe_row = list(max_sharpe_weights) + list(max_sharpe_metrics)
                results = pd.concat([results, pd.DataFrame([max_sharpe_row], columns=all_cols)], ignore_index=True)
                
                # Generate efficient frontier points between min variance and beyond max Sharpe
                target_returns = np.linspace(min_variance_return, 
                                            max_sharpe_return * 1.2, 
                                            num_portfolios)
                
                # For each target return, find minimum risk portfolio
                for target_return in target_returns:
                    # Return constraint for the target
                    return_constraint = {'type': 'eq', 
                                        'fun': lambda weights: calculate_portfolio_metrics(weights)[0] - target_return}
                                        
                    # Combined constraints
                    constraints = [constraint, return_constraint]
                    
                    # Minimize volatility subject to target return
                    efficient_result = minimize(min_var_function, initial_weights, method='SLSQP',
                                              bounds=bounds, constraints=constraints)
                                              
                    if efficient_result['success']:
                        efficient_weights = efficient_result['x']
                        efficient_metrics = calculate_portfolio_metrics(efficient_weights)
                        
                        # Add to results
                        efficient_row = list(efficient_weights) + list(efficient_metrics)
                        results = pd.concat([results, pd.DataFrame([efficient_row], columns=all_cols)], ignore_index=True)
        
        # Sort by risk (for traditional efficient frontier)
        return results.sort_values('Risk')
        
    except Exception as e:
        print(f"Error generating efficient frontier: {e}")
        # Return empty DataFrame
        empty_results = pd.DataFrame(columns=['Return', 'Risk', 'Sharpe Ratio', 'Active Return', 'Tracking Error', 'Information Ratio'])
        return empty_results

def calculate_asset_metrics(returns_data):
    """
    Calculate metrics for individual assets
    
    Args:
        returns_data: DataFrame with asset returns
        
    Returns:
        DataFrame with asset metrics
    """
    mean_returns = returns_data.mean() * 12  # Annualized
    std_dev = returns_data.std() * np.sqrt(12)  # Annualized
    risk_free_rate = 0.02  # Annual risk-free rate (2%)
    
    # Calculate Sharpe ratio (handle division by zero or NaN)
    sharpe_ratio = pd.Series(np.zeros(len(mean_returns)), index=mean_returns.index)
    valid_indices = std_dev > 0
    sharpe_ratio[valid_indices] = (mean_returns[valid_indices] - risk_free_rate) / std_dev[valid_indices]
    
    # Calculate tracking error and information ratio versus SPY (if SPY is in the portfolio)
    spy_index = None
    for i, ticker in enumerate(returns_data.columns):
        if ticker.upper() == 'SPY':
            spy_index = i
            break
    
    if spy_index is not None:
        # Calculate active returns
        active_return = mean_returns - mean_returns.iloc[spy_index]
        
        # Calculate tracking error for each asset (safe calculation)
        spy_returns = returns_data.iloc[:, spy_index]
        tracking_error = returns_data.apply(
            lambda x: np.sqrt(np.mean((x.values - spy_returns.values) ** 2)) * np.sqrt(12) 
            if not np.isnan(x.values).any() and not np.isnan(spy_returns.values).any() else np.nan
        )
        
        # Calculate information ratio (handle division by zero or NaN)
        info_ratio = pd.Series(np.zeros(len(mean_returns)), index=mean_returns.index)
        valid_indices = tracking_error > 0
        info_ratio[valid_indices] = active_return[valid_indices] / tracking_error[valid_indices]
    else:
        # Default values if SPY is not in the portfolio
        active_return = pd.Series([0] * len(mean_returns), index=mean_returns.index)
        tracking_error = pd.Series([0] * len(mean_returns), index=mean_returns.index)
        info_ratio = pd.Series([0] * len(mean_returns), index=mean_returns.index)
    
    # Create DataFrame with asset metrics
    asset_metrics = pd.DataFrame({
        'Asset': returns_data.columns,
        'Expected Return': mean_returns.values,
        'Standard Deviation': std_dev.values,
        'Sharpe Ratio': sharpe_ratio.values,
        'Expected Active Return': active_return.values,
        'Tracking Error': tracking_error.values,
        'Information Ratio': info_ratio.values,
        'Min. Weight': [0.0] * len(returns_data.columns),
        'Max. Weight': [100.0] * len(returns_data.columns)
    })
    
    return asset_metrics

def calculate_tangency_portfolio(returns_data):
    """
    Calculate the tangency portfolio (maximum Sharpe ratio)
    
    Args:
        returns_data: DataFrame with asset returns
        
    Returns:
        Dict with tangency portfolio details
    """
    mean_returns = returns_data.mean()
    cov_matrix = returns_data.cov()
    risk_free_rate = 0.02 / 12  # Monthly risk-free rate (2% annual)
    
    # Number of assets
    num_assets = len(mean_returns)
    
    # Function to calculate portfolio Sharpe ratio
    def portfolio_sharpe(weights):
        portfolio_return = np.sum(mean_returns * weights) * 12  # Annualized
        portfolio_stddev = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights))) * np.sqrt(12)  # Annualized
        sharpe_ratio = (portfolio_return - risk_free_rate * 12) / portfolio_stddev
        return -sharpe_ratio  # Negative for minimization
    
    # Function for optimization constraint (weights sum to 1)
    def constraint(weights):
        return np.sum(weights) - 1
    
    # Set optimization constraints
    constraints = {'type': 'eq', 'fun': constraint}
    bounds = tuple((0, 1) for _ in range(num_assets))
    
    # Initialize weights
    equal_weights = np.array([1/num_assets] * num_assets)
    
    # Optimize for maximum Sharpe ratio
    result = minimize(portfolio_sharpe, equal_weights, method='SLSQP', bounds=bounds, constraints=constraints)
    
    if result['success']:
        weights = result['x']
        
        # Calculate portfolio metrics
        portfolio_return = np.sum(mean_returns * weights) * 12  # Annualized
        portfolio_stddev = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights))) * np.sqrt(12)  # Annualized
        sharpe_ratio = (portfolio_return - risk_free_rate * 12) / portfolio_stddev
        
        # Calculate tracking error and information ratio versus SPY (if SPY is in the portfolio)
        spy_index = None
        for i, ticker in enumerate(returns_data.columns):
            if ticker.upper() == 'SPY':
                spy_index = i
                break
        
        if spy_index is not None:
            # Calculate active returns
            active_return = mean_returns - mean_returns.iloc[spy_index]
            
            # Calculate expected active return for the portfolio
            expected_active_return = np.sum(active_return * weights)
            
            # Calculate tracking error for each asset versus SPY safely
            spy_returns = returns_data.iloc[:, spy_index]
            
            # Create a tracking error matrix (covariance of tracking errors)
            tracking_error_cov = np.zeros((num_assets, num_assets))
            for i in range(num_assets):
                for j in range(num_assets):
                    # Calculate covariance of tracking errors
                    asset_i_excess = returns_data.iloc[:, i].values - spy_returns.values
                    asset_j_excess = returns_data.iloc[:, j].values - spy_returns.values
                    tracking_error_cov[i, j] = np.mean(asset_i_excess * asset_j_excess)
            
            # Calculate tracking error for the portfolio
            tracking_error_portfolio = np.sqrt(np.dot(weights.T, np.dot(tracking_error_cov, weights))) * np.sqrt(12)
            
            # Calculate information ratio
            info_ratio = expected_active_return / tracking_error_portfolio if tracking_error_portfolio > 0 else 0
        else:
            # Default values if SPY is not in the portfolio
            expected_active_return = 0
            tracking_error_portfolio = 0
            info_ratio = 0
        
        # Create portfolio dict
        portfolio = {
            'name': 'Tangency Portfolio',
            'weights': {ticker: weight for ticker, weight in zip(returns_data.columns, weights)},
            'return': portfolio_return,
            'risk': portfolio_stddev,
            'sharpe': sharpe_ratio,
            'active_return': expected_active_return,
            'tracking_error': tracking_error_portfolio,
            'info_ratio': info_ratio
        }
        
        return portfolio
    else:
        # Return default portfolio if optimization fails
        return {
            'name': 'Tangency Portfolio',
            'weights': {ticker: 1/num_assets for ticker in returns_data.columns},
            'return': 0,
            'risk': 0,
            'sharpe': 0,
            'active_return': 0,
            'tracking_error': 0,
            'info_ratio': 0
        }

def calculate_max_info_ratio_portfolio(returns_data):
    """
    Calculate the maximum information ratio portfolio
    
    Args:
        returns_data: DataFrame with asset returns
        
    Returns:
        Dict with maximum information ratio portfolio details
    """
    mean_returns = returns_data.mean()
    cov_matrix = returns_data.cov()
    
    # Number of assets
    num_assets = len(mean_returns)
    
    # Find SPY index
    spy_index = None
    for i, ticker in enumerate(returns_data.columns):
        if ticker.upper() == 'SPY':
            spy_index = i
            break
    
    # If SPY is not in the portfolio, return the tangency portfolio
    if spy_index is None:
        return calculate_tangency_portfolio(returns_data)
    
    # Calculate active returns
    active_return = mean_returns - mean_returns.iloc[spy_index]
    
    # Calculate tracking error covariance matrix safely
    spy_returns = returns_data.iloc[:, spy_index]
    
    # Create a tracking error covariance matrix
    tracking_error_cov = np.zeros((num_assets, num_assets))
    for i in range(num_assets):
        for j in range(num_assets):
            # Calculate covariance of tracking errors
            asset_i_excess = returns_data.iloc[:, i].values - spy_returns.values
            asset_j_excess = returns_data.iloc[:, j].values - spy_returns.values
            tracking_error_cov[i, j] = np.mean(asset_i_excess * asset_j_excess)
    
    # Function to calculate portfolio information ratio
    def portfolio_info_ratio(weights):
        # Expected active return
        expected_active_return = np.sum(active_return * weights) * 12  # Annualized
        
        # Tracking error using covariance matrix
        tracking_error_portfolio = np.sqrt(np.dot(weights.T, np.dot(tracking_error_cov, weights))) * np.sqrt(12)  # Annualized
        
        # Information ratio
        info_ratio = expected_active_return / tracking_error_portfolio if tracking_error_portfolio > 0 else 0
        
        return -info_ratio  # Negative for minimization
    
    # Function for optimization constraint (weights sum to 1)
    def constraint(weights):
        return np.sum(weights) - 1
    
    # Set optimization constraints
    constraints = {'type': 'eq', 'fun': constraint}
    bounds = tuple((0, 1) for _ in range(num_assets))
    
    # Initialize weights
    equal_weights = np.array([1/num_assets] * num_assets)
    
    # Optimize for maximum information ratio
    result = minimize(portfolio_info_ratio, equal_weights, method='SLSQP', bounds=bounds, constraints=constraints)
    
    if result['success']:
        weights = result['x']
        
        # Calculate portfolio metrics
        portfolio_return = np.sum(mean_returns * weights) * 12  # Annualized
        portfolio_stddev = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights))) * np.sqrt(12)  # Annualized
        risk_free_rate = 0.02  # Annual risk-free rate (2%)
        sharpe_ratio = (portfolio_return - risk_free_rate) / portfolio_stddev
        
        # Calculate expected active return for the portfolio
        expected_active_return = np.sum(active_return * weights) * 12  # Annualized
        
        # Calculate tracking error for the portfolio
        tracking_error_portfolio = np.sqrt(np.dot(weights.T, np.dot(tracking_error_cov, weights))) * np.sqrt(12)  # Annualized
        
        # Calculate information ratio
        info_ratio = expected_active_return / tracking_error_portfolio if tracking_error_portfolio > 0 else 0
        
        # Create portfolio dict
        portfolio = {
            'name': 'Max Information Ratio Portfolio',
            'weights': {ticker: weight for ticker, weight in zip(returns_data.columns, weights)},
            'return': portfolio_return,
            'risk': portfolio_stddev,
            'sharpe': sharpe_ratio,
            'active_return': expected_active_return,
            'tracking_error': tracking_error_portfolio,
            'info_ratio': info_ratio
        }
        
        return portfolio
    else:
        # Return default portfolio if optimization fails
        return {
            'name': 'Max Information Ratio Portfolio',
            'weights': {ticker: 1/num_assets for ticker in returns_data.columns},
            'return': 0,
            'risk': 0,
            'sharpe': 0,
            'active_return': 0,
            'tracking_error': 0,
            'info_ratio': 0
        }

def generate_equal_weight_portfolio(returns_data):
    """
    Generate an equal-weight portfolio for comparison
    
    Args:
        returns_data: DataFrame with asset returns
        
    Returns:
        Dict with equal-weight portfolio details
    """
    mean_returns = returns_data.mean()
    cov_matrix = returns_data.cov()
    risk_free_rate = 0.02  # Annual risk-free rate (2%)
    
    # Number of assets
    num_assets = len(mean_returns)
    
    # Equal weights
    weights = np.array([1/num_assets] * num_assets)
    
    # Calculate portfolio metrics
    portfolio_return = np.sum(mean_returns * weights) * 12  # Annualized
    portfolio_stddev = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights))) * np.sqrt(12)  # Annualized
    sharpe_ratio = (portfolio_return - risk_free_rate) / portfolio_stddev
    
    # Calculate tracking error and information ratio versus SPY (if SPY is in the portfolio)
    spy_index = None
    for i, ticker in enumerate(returns_data.columns):
        if ticker.upper() == 'SPY':
            spy_index = i
            break
    
    if spy_index is not None:
        # Calculate active returns
        active_return = mean_returns - mean_returns.iloc[spy_index]
        
        # Calculate expected active return for the portfolio
        expected_active_return = np.sum(active_return * weights) * 12  # Annualized
        
        # Calculate tracking error covariance matrix safely
        spy_returns = returns_data.iloc[:, spy_index]
        
        # Create a tracking error covariance matrix
        tracking_error_cov = np.zeros((num_assets, num_assets))
        for i in range(num_assets):
            for j in range(num_assets):
                # Calculate covariance of tracking errors
                asset_i_excess = returns_data.iloc[:, i].values - spy_returns.values
                asset_j_excess = returns_data.iloc[:, j].values - spy_returns.values
                tracking_error_cov[i, j] = np.mean(asset_i_excess * asset_j_excess)
        
        # Calculate tracking error for the portfolio
        tracking_error_portfolio = np.sqrt(np.dot(weights.T, np.dot(tracking_error_cov, weights))) * np.sqrt(12)  # Annualized
        
        # Calculate information ratio
        info_ratio = expected_active_return / tracking_error_portfolio if tracking_error_portfolio > 0 else 0
    else:
        # Default values if SPY is not in the portfolio
        expected_active_return = 0
        tracking_error_portfolio = 0
        info_ratio = 0
    
    # Create portfolio dict
    portfolio = {
        'name': 'Equal Weight Portfolio',
        'weights': {ticker: weight for ticker, weight in zip(returns_data.columns, weights)},
        'return': portfolio_return,
        'risk': portfolio_stddev,
        'sharpe': sharpe_ratio,
        'active_return': expected_active_return,
        'tracking_error': tracking_error_portfolio,
        'info_ratio': info_ratio
    }
    
    return portfolio

def generate_efficient_frontier_chart(efficient_portfolios, tangency_portfolio, max_info_portfolio, asset_metrics):
    """
    Generate a chart showing the efficient frontier with portfolios and assets
    
    Args:
        efficient_portfolios: DataFrame with efficient frontier portfolios
        tangency_portfolio: Dict with tangency portfolio details
        max_info_portfolio: Dict with maximum information ratio portfolio details
        asset_metrics: DataFrame with asset metrics
        
    Returns:
        HTML representation of the plotly chart
    """
    # Create figure
    fig = go.Figure()
    
    # Add efficient frontier line
    fig.add_trace(go.Scatter(
        x=efficient_portfolios['Tracking Error'],
        y=efficient_portfolios['Active Return'],
        mode='lines',
        name='Efficient Frontier',
        line=dict(color='blue', width=2)
    ))
    
    # Add individual assets
    for i, asset in asset_metrics.iterrows():
        fig.add_trace(go.Scatter(
            x=[asset['Tracking Error']],
            y=[asset['Expected Active Return']],
            mode='markers',
            name=asset['Asset'],
            marker=dict(size=10, opacity=0.8),
            text=[asset['Asset']]
        ))
    
    # Add tangency portfolio
    fig.add_trace(go.Scatter(
        x=[tangency_portfolio['tracking_error']],
        y=[tangency_portfolio['active_return']],
        mode='markers',
        name='Tangency Portfolio',
        marker=dict(size=12, symbol='star', color='green'),
        text=['Tangency Portfolio']
    ))
    
    # Add max information ratio portfolio
    fig.add_trace(go.Scatter(
        x=[max_info_portfolio['tracking_error']],
        y=[max_info_portfolio['active_return']],
        mode='markers',
        name='Max Info Ratio Portfolio',
        marker=dict(size=12, symbol='star', color='purple'),
        text=['Max Info Ratio Portfolio']
    ))
    
    # Add equal-weight portfolio dot with label "222"
    equal_weight_index = len(efficient_portfolios) // 2
    if equal_weight_index < len(efficient_portfolios):
        equal_weight = efficient_portfolios.iloc[equal_weight_index]
        fig.add_trace(go.Scatter(
            x=[equal_weight['Tracking Error']],
            y=[equal_weight['Active Return']],
            mode='markers+text',
            name='222',
            marker=dict(size=10, color='black'),
            text=['222'],
            textposition='bottom center'
        ))
    
    # Update layout
    fig.update_layout(
        title="Resampled Tracking Error Efficient Frontier",
        xaxis_title="Tracking Error",
        yaxis_title="Expected Active Return",
        legend=dict(
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01
        ),
        plot_bgcolor='white',
        width=800,
        height=600
    )
    
    # Add grid lines
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='lightgray')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='lightgray')
    
    # Convert to HTML
    return pio.to_html(fig, full_html=False)

def generate_transition_map(efficient_portfolios):
    """
    Generate a transition map showing how portfolio weights change along the frontier
    
    Args:
        efficient_portfolios: DataFrame with efficient frontier portfolios
        
    Returns:
        HTML representation of the plotly chart
    """
    # Get asset columns (all columns except the metrics)
    asset_columns = efficient_portfolios.columns[:-6]  # Exclude last 6 columns which are metrics
    
    # Create figure
    fig = go.Figure()
    
    # Add area traces for each asset
    cumulative_weights = np.zeros(len(efficient_portfolios))
    
    for asset in asset_columns:
        fig.add_trace(go.Scatter(
            x=efficient_portfolios['Tracking Error'],
            y=cumulative_weights + efficient_portfolios[asset] * 100,  # Convert to percentage
            mode='lines',
            name=asset,
            fill='tonexty',
            line=dict(width=0)
        ))
        cumulative_weights += efficient_portfolios[asset] * 100
    
    # Update layout
    fig.update_layout(
        title="Tracking Error Efficient Frontier Transition Map",
        xaxis_title="Tracking Error",
        yaxis_title="Allocation (%)",
        legend=dict(
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01
        ),
        plot_bgcolor='white',
        width=800,
        height=600,
        yaxis=dict(range=[0, 100])
    )
    
    # Add grid lines
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='lightgray')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='lightgray')
    
    # Convert to HTML
    return pio.to_html(fig, full_html=False)