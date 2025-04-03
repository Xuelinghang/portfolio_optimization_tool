import pandas as pd
import numpy as np
from scipy import stats

def calculate_portfolio_metrics(portfolio_data, returns_data):
    """
    Calculate comprehensive portfolio performance metrics.
    
    Args:
        portfolio_data (dict): Portfolio time series data
        returns_data (dict): Asset returns data
    
    Returns:
        dict: Dictionary containing calculated metrics
    """
    portfolio_returns = portfolio_data['returns']
    portfolio_values = portfolio_data['values']
    
    # Basic portfolio statistics
    start_balance = portfolio_values.iloc[0]
    end_balance = portfolio_values.iloc[-1]
    
    # Time period calculations
    time_years = len(portfolio_returns) / 12  # Assuming monthly data
    
    # Calculate annualized return (CAGR)
    cagr = (end_balance / start_balance) ** (1 / time_years) - 1
    
    # Monthly returns statistics
    mean_monthly_return = portfolio_returns.mean()
    annualized_return = (1 + mean_monthly_return) ** 12 - 1
    
    # Geometric mean (annualized)
    geometric_mean_monthly = (1 + portfolio_returns).prod() ** (1 / len(portfolio_returns)) - 1
    geometric_mean_annual = (1 + geometric_mean_monthly) ** 12 - 1
    
    # Standard deviation
    std_dev_monthly = portfolio_returns.std()
    std_dev_annual = std_dev_monthly * np.sqrt(12)
    
    # Downside deviation (only negative returns)
    downside_returns = portfolio_returns.copy()
    downside_returns[downside_returns > 0] = 0
    downside_deviation = np.sqrt(np.sum(downside_returns ** 2) / len(downside_returns))
    
    # Calculate maximum drawdown
    rolling_max = portfolio_values.cummax()
    drawdowns = (portfolio_values / rolling_max) - 1
    max_drawdown = drawdowns.min()
    
    # Risk metrics
    # Assuming risk-free rate of 0.02 (2%) for Sharpe and Sortino ratios
    rf_rate = 0.02
    monthly_rf = (1 + rf_rate) ** (1/12) - 1
    
    # Sharpe ratio
    sharpe_ratio = (annualized_return - rf_rate) / std_dev_annual if std_dev_annual != 0 else 0
    
    # Sortino ratio
    sortino_ratio = (annualized_return - rf_rate) / (downside_deviation * np.sqrt(12)) if downside_deviation != 0 else 0
    
    # Calculate annual returns
    annual_returns = {}
    for year in portfolio_returns.index.year.unique():
        year_returns = portfolio_returns[portfolio_returns.index.year == year]
        annual_return = (1 + year_returns).prod() - 1
        annual_returns[year] = annual_return
    
    # Best and worst years
    best_year = max(annual_returns.items(), key=lambda x: x[1]) if annual_returns else (None, 0)
    worst_year = min(annual_returns.items(), key=lambda x: x[1]) if annual_returns else (None, 0)
    
    # Calculate skewness and kurtosis
    skewness = stats.skew(portfolio_returns.dropna())
    kurtosis = stats.kurtosis(portfolio_returns.dropna())
    
    # Value at Risk (VaR)
    var_historic = np.percentile(portfolio_returns, 5)
    var_analytic = mean_monthly_return - (std_dev_monthly * 1.645)  # 95% confidence
    
    # Conditional VaR (CVaR)
    cvar = portfolio_returns[portfolio_returns <= var_historic].mean()
    
    # Trailing returns
    trailing_returns = {}
    current_date = portfolio_returns.index[-1]
    
    if len(portfolio_values) >= 3:  # At least 3 months for 3-month return
        three_month_ago = portfolio_values.iloc[-3] if len(portfolio_values) >= 3 else portfolio_values.iloc[0]
        trailing_returns['3_month'] = (portfolio_values.iloc[-1] / three_month_ago) - 1
    
    # YTD return
    ytd_start_idx = portfolio_values[portfolio_values.index.year == current_date.year].index[0]
    ytd_start_value = portfolio_values.loc[ytd_start_idx]
    trailing_returns['ytd'] = (portfolio_values.iloc[-1] / ytd_start_value) - 1
    
    # 1-year return
    if time_years >= 1:
        one_year_ago_idx = -12 if len(portfolio_values) >= 12 else 0
        trailing_returns['1_year'] = (portfolio_values.iloc[-1] / portfolio_values.iloc[one_year_ago_idx]) - 1
    
    # 3-year return (annualized)
    if time_years >= 3:
        three_year_ago_idx = -36 if len(portfolio_values) >= 36 else 0
        trailing_returns['3_year'] = ((portfolio_values.iloc[-1] / portfolio_values.iloc[three_year_ago_idx]) ** (1/3)) - 1
    
    # 5-year return (annualized)
    if time_years >= 5:
        five_year_ago_idx = -60 if len(portfolio_values) >= 60 else 0
        trailing_returns['5_year'] = ((portfolio_values.iloc[-1] / portfolio_values.iloc[five_year_ago_idx]) ** (1/5)) - 1
    
    # Positive periods
    positive_periods = (portfolio_returns > 0).sum()
    total_periods = len(portfolio_returns)
    
    # Gain/Loss ratio
    avg_gain = portfolio_returns[portfolio_returns > 0].mean() if len(portfolio_returns[portfolio_returns > 0]) > 0 else 0
    avg_loss = portfolio_returns[portfolio_returns < 0].mean() if len(portfolio_returns[portfolio_returns < 0]) > 0 else 0
    gain_loss_ratio = abs(avg_gain / avg_loss) if avg_loss != 0 else float('inf')
    
    # Safe withdrawal rate (4% rule adjusted by CAGR)
    safe_withdrawal_rate = 0.04 * (1 + (cagr - 0.04)/2) if cagr > 0.02 else 0.04 * (cagr / 0.04)
    
    # Perpetual withdrawal rate (conservative estimate)
    perpetual_withdrawal_rate = max(0, cagr - 0.01)  # Accounting for inflation protection
    
    # Compile all metrics
    metrics = {
        'portfolio': {
            'start_balance': start_balance,
            'end_balance': end_balance,
            'cagr': cagr,
            'std_dev_monthly': std_dev_monthly,
            'std_dev_annual': std_dev_annual,
            'best_year': best_year,
            'worst_year': worst_year,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'downside_deviation': downside_deviation,
            'mean_monthly_return': mean_monthly_return,
            'annualized_return': annualized_return,
            'geometric_mean_monthly': geometric_mean_monthly,
            'geometric_mean_annual': geometric_mean_annual,
            'skewness': skewness,
            'excess_kurtosis': kurtosis,
            'var_historic': var_historic,
            'var_analytic': var_analytic,
            'cvar': cvar,
            'positive_periods': positive_periods,
            'total_periods': total_periods,
            'gain_loss_ratio': gain_loss_ratio,
            'safe_withdrawal_rate': safe_withdrawal_rate,
            'perpetual_withdrawal_rate': perpetual_withdrawal_rate,
        },
        'annual_returns': annual_returns,
        'trailing_returns': trailing_returns
    }
    
    # Asset-specific metrics
    assets_metrics = {}
    
    for asset in returns_data:
        asset_returns = returns_data[asset]
        
        # Skip if not enough data
        if len(asset_returns) < 12:
            continue
        
        # Calculate annualized return
        asset_annualized = (1 + asset_returns.mean()) ** 12 - 1
        
        # Standard deviation
        asset_std_dev = asset_returns.std() * np.sqrt(12)
        
        # Calculate annual returns for the asset
        asset_annual_returns = {}
        for year in asset_returns.index.year.unique():
            year_returns = asset_returns[asset_returns.index.year == year]
            annual_return = (1 + year_returns).prod() - 1
            asset_annual_returns[year] = annual_return
            
        # Best and worst years
        asset_best_year = max(asset_annual_returns.items(), key=lambda x: x[1]) if asset_annual_returns else (None, 0)
        asset_worst_year = min(asset_annual_returns.items(), key=lambda x: x[1]) if asset_annual_returns else (None, 0)
        
        # Calculate maximum drawdown
        asset_values = (1 + asset_returns).cumprod()
        asset_rolling_max = asset_values.cummax()
        asset_drawdowns = (asset_values / asset_rolling_max) - 1
        asset_max_drawdown = asset_drawdowns.min()
        
        # Risk metrics
        asset_downside_returns = asset_returns.copy()
        asset_downside_returns[asset_downside_returns > 0] = 0
        asset_downside_deviation = np.sqrt(np.sum(asset_downside_returns ** 2) / len(asset_downside_returns))
        
        # Sharpe and Sortino ratios
        asset_sharpe = (asset_annualized - rf_rate) / asset_std_dev if asset_std_dev != 0 else 0
        asset_sortino = (asset_annualized - rf_rate) / (asset_downside_deviation * np.sqrt(12)) if asset_downside_deviation != 0 else 0
        
        assets_metrics[asset] = {
            'cagr': (1 + asset_returns).prod() ** (12 / len(asset_returns)) - 1,
            'std_dev': asset_std_dev,
            'best_year': asset_best_year,
            'worst_year': asset_worst_year,
            'max_drawdown': asset_max_drawdown,
            'sharpe_ratio': asset_sharpe,
            'sortino_ratio': asset_sortino
        }
    
    metrics['assets'] = assets_metrics
    
    return metrics
