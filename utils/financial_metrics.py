
sector_map = {
    'AAPL': 'Technology',
    'NVDA': 'Technology',
    'MSFT': 'Technology',
    'AMZN': 'Consumer Discretionary',
    'TSLA': 'Consumer Discretionary',
    'GOOGL': 'Communication Services',
    'META': 'Communication Services',
    'BRK.B': 'Financials',
    'JPM': 'Financials',
    'JNJ': 'Healthcare',
    'XOM': 'Energy',
    'V': 'Financials',
    'PG': 'Consumer Staples'
}


# In utils/financial_metrics.py

import pandas as pd
import numpy as np
from scipy import stats
from scipy.optimize import minimize
from datetime import datetime, UTC, date

import traceback
from flask import jsonify

import plotly.graph_objects as go
import plotly.io as pio

def calculate_returns(price_data):
    """
    Calculate returns from price data.
    
    Args:
        price_data: DataFrame with historical price data (date index, price columns)
        
    Returns:
        DataFrame with returns
    """
    if price_data is None or price_data.empty:
         return pd.DataFrame()

    returns = price_data.pct_change().dropna()
    return returns


# This function will now accept daily prices, weights, holdings_list, and tickers_with_daily_data
def calculate_portfolio_metrics(daily_prices, weights, holdings_list, tickers_with_daily_data, initial_investment=1.0):
    """
    Calculate comprehensive portfolio performance metrics, including significant drawdowns, Beta, and Alpha.

    Args:
        daily_prices: DataFrame with daily historical price data (date index, ticker columns).
                      Assumes data is cleaned (e.g., ffilled/bfilled, NaNs dropped where necessary).
                      Date index is assumed to be timezone-aware UTC.
        weights: Pandas Series of asset weights, aligned with daily_prices columns.
        holdings_list: List of dictionaries for holdings (from the calling route), used for names/details.
        tickers_with_daily_data: List of ticker symbols that have valid daily data.

    Returns:
        Dictionary containing various calculated metrics for the portfolio and assets.
        Returns an empty dictionary {} on calculation failure.
    """
    # Initialize all variables that will be used in the final results dictionary
    metrics_results = {
        'portfolio_overall_metrics': {},
        'portfolio_growth_data': {'dates': [], 'values': []},
        'risk_decomposition_data': [],
        'return_decomposition_data': [],
        'holdings_table_data': [], # This should be populated later based on holdings_list and assets_metrics
        'annual_returns_portfolio': {},
        'monthly_returns_data': {},
        'asset_metrics_data': {}, # Dictionary to store per-asset calculated metrics
        'sector_allocation_data': {},
        'correlations_data': pd.DataFrame().to_dict(), # Default to empty DataFrame dict
        'calculation_period': {},
        'metrics_calculation_date': None,
        'assets': {}, # Placeholder for per-asset metrics within the calculate_portfolio_metrics scope
        'significant_drawdowns': [], # Add key for significant drawdowns
        'monthly_drawdowns': {} # Add key for monthly drawdowns (as a dictionary)
    }

    # Initialize other variables used in calculations to default values
    cagr = 0.0
    std_dev_monthly = 0.0
    std_dev_annual = 0.0
    downside_deviation_monthly = 0.0
    downside_deviation_annual = 0.0
    best_year_tuple = (None, 0.0)
    worst_year_tuple = (None, 0.0)
    annualized_return = 0.0
    geometric_mean_monthly = 0.0
    geometric_mean_annual = 0.0
    portfolio_daily_returns_series = pd.Series([], dtype='float64')
    portfolio_values_series = pd.Series([], dtype='float64')
    monthly_prices = pd.DataFrame()
    monthly_returns = pd.Series([], dtype='float64')
    positive_periods = 0
    negative_periods = 0
    total_periods = 0
    gains = pd.Series([], dtype='float64')
    losses = pd.Series([], dtype='float64')
    avg_gain = 0.0
    avg_loss = 0.0
    gain_loss_ratio = float('inf')
    skewness = 0.0
    kurtosis_excess = 0.0
    var_historic_daily = 0.0
    cvar_daily = 0.0
    max_drawdown_value = 0.0
    max_drawdown_date = None
    peak_before_drawdown_date = None
    recovery_date = None
    recovery_time_formatted = "N/A"
    initial_investment_for_calc = 0.0

    # Ensure inputs are valid
    if not isinstance(daily_prices, pd.DataFrame) or daily_prices.empty or daily_prices.shape[1] < 1:
         print("Error: daily_prices input is not a DataFrame, is empty, or has less than 1 column.")
         return metrics_results

    if not isinstance(weights, pd.Series) or not weights.index.tolist() == daily_prices.columns.tolist():
         print("Error: Weights must be a Pandas Series aligned with daily_prices columns.")
         return metrics_results

    # Ensure weights sum to 1 and are non-negative
    weights = weights.clip(lower=0)
    sum_weights = weights.sum()
    if sum_weights > 0:
        weights = weights / sum_weights
    else:
         print("Warning: Weights sum to zero after non-negative clipping. Metrics calculation may be invalid.")
         weights = weights * 0.0

    # --- Calculate daily returns ---
    daily_returns = calculate_returns(daily_prices)

    if daily_returns.empty:
        print("Insufficient daily returns data for metrics calculation after cleaning.")
        return metrics_results


    # --- Calculate portfolio daily returns ---
    portfolio_daily_returns_series = (daily_returns * weights).sum(axis=1)


    # --- Calculate portfolio values over time (starting with an initial investment) ---
    initial_investment_for_calc = float(initial_investment)


    # Calculate cumulative product of (1 + daily returns)
    cumulative_returns = (1 + portfolio_daily_returns_series).cumprod()
    if not cumulative_returns.empty:
         if pd.isna(cumulative_returns.iloc[0]) or cumulative_returns.iloc[0] == 0:
              cumulative_returns.iloc[0] = 1.0

         if not isinstance(cumulative_returns.index, pd.DatetimeIndex) or cumulative_returns.index.tzinfo is None:
              print("Warning: Cumulative returns index is not timezone-aware UTC. Localizing as UTC.")
              cumulative_returns.index = pd.to_datetime(cumulative_returns.index).tz_localize(UTC)
         elif cumulative_returns.index.tzinfo != UTC:
              cumulative_returns = cumulative_returns.tz_convert(UTC)

    else:
         print("Cumulative returns series is empty. Portfolio growth calculation skipped.")
         portfolio_values_series = pd.Series([], dtype='float64')
         initial_investment_for_calc = 0.0


    # Calculate portfolio values over time
    if not cumulative_returns.empty and initial_investment_for_calc > 0:
         portfolio_values_series = cumulative_returns * initial_investment_for_calc
    else:
         portfolio_values_series = pd.Series([], dtype='float64')


    # --- Resample daily prices to Monthly Frequency for Metrics ---
    try:
        monthly_prices = daily_prices.resample('ME').last()
        monthly_prices = monthly_prices.dropna(how='all')

        monthly_returns = calculate_returns(monthly_prices)

        if not monthly_returns.empty:
             if not isinstance(monthly_returns.index, pd.DatetimeIndex) or monthly_returns.index.tzinfo is None:
                  print("Warning: Monthly returns index is not timezone-aware UTC. Localizing as UTC.")
                  monthly_returns.index = monthly_returns.index.tz_localize(UTC)
             elif monthly_returns.index.tzinfo != UTC:
                   monthly_returns = monthly_returns.tz_convert(UTC)


        annual_returns_portfolio = {}
        if not monthly_returns.empty:
            cum_by_year = (1 + monthly_returns).groupby(monthly_returns.index.year).prod()

            for year in cum_by_year.index:
                 year_product = cum_by_year.loc[year]

                 prev_years_cum = cum_by_year[cum_by_year.index < year]
                 prev_cum_product = prev_years_cum.prod() if not prev_years_cum.empty else pd.Series([1.0], index=[year-1])

                 annual_return_for_year = year_product - 1

                 annual_return_scalar = annual_return_for_year.sum() if isinstance(annual_return_for_year, pd.Series) else annual_return_for_year

                 annual_returns_portfolio[year] = float(annual_return_scalar)


            best_year_tuple = max(annual_returns_portfolio.items(), key=lambda x: x[1]) if annual_returns_portfolio else (None, 0.0)
            worst_year_tuple = min(annual_returns_portfolio.items(), key=lambda x: x[1]) if annual_returns_portfolio else (None, 0.0)

        else:
             annual_returns_portfolio = {}
             best_year_tuple = (None, 0.0)
             worst_year_tuple = (None, 0.0)


        if not monthly_returns.empty and len(monthly_returns) > 0:
             mean_monthly_asset_returns = monthly_returns.mean()

             geometric_mean_monthly_asset_returns = ((1 + monthly_returns).prod() ** (1 / len(monthly_returns))).mean() - 1 if len(monthly_returns) > 0 else 0.0

             geometric_mean_monthly = geometric_mean_monthly_asset_returns if not np.isnan(geometric_mean_monthly_asset_returns) else 0.0

             geometric_mean_annual = (1 + geometric_mean_monthly) ** 12 - 1 if geometric_mean_monthly is not None else 0.0

        else:
             geometric_mean_monthly = 0.0
             geometric_mean_annual = 0.0


        mean_monthly_return = (mean_monthly_asset_returns * weights).sum() if not monthly_returns.empty and not mean_monthly_asset_returns.empty else 0.0

        annualized_return = (1 + mean_monthly_return) ** 12 - 1 if not np.isnan(mean_monthly_return) else 0.0
        print("Debug: annualized_return (CAGR):", annualized_return)


    except Exception as resample_err:
        print(f"Error during resampling or monthly/annual returns/geometric means calculation: {resample_err}")
        traceback.print_exc()
        monthly_prices = pd.DataFrame()
        monthly_returns = pd.Series([], dtype='float64')
        annual_returns_portfolio = {}
        best_year_tuple = (None, 0.0)
        worst_year_tuple = (None, 0.0)
        geometric_mean_monthly = 0.0
        geometric_mean_annual = 0.0
        mean_monthly_return = 0.0
        annualized_return = 0.0


    # --- Standard Volatility & Downside Deviation (using monthly returns) ---
    std_dev_monthly = monthly_returns.std().mean() if not monthly_returns.empty and len(monthly_returns.dropna(how='all')) > 1 else 0.0
    std_dev_annual  = std_dev_monthly * np.sqrt(12) if not monthly_returns.empty and len(monthly_returns.dropna(how='all')) > 1 else 0.0

    downside_returns_monthly = monthly_returns[monthly_returns < 0].fillna(0)
    downside_deviation_monthly = np.sqrt((downside_returns_monthly ** 2).sum().mean() / len(monthly_returns)) if not monthly_returns.empty and len(monthly_returns) > 0 else 0.0
    downside_deviation_annual = downside_deviation_monthly * np.sqrt(12) if not monthly_returns.empty and len(monthly_returns) > 0 else 0.0


    # --- Drawdown & recovery (using daily values) ---
    max_drawdown_value            = 0.0
    max_drawdown_date             = None
    peak_before_drawdown_date     = None
    recovery_date                 = None
    recovery_time_formatted       = "N/A"
    significant_drawdowns_list = [] # List to store details of each significant drawdown
    monthly_drawdowns_dict = {} # Dictionary to store monthly drawdowns


    if not portfolio_values_series.empty:
        rolling_max = portfolio_values_series.cummax()
        rolling_max = rolling_max.replace(0, np.nan).ffill().fillna(0)

        drawdowns_series = (portfolio_values_series - rolling_max) / rolling_max
        drawdowns_series = drawdowns_series.replace([np.inf, -np.inf], np.nan).fillna(0)


        # --- Identify Significant Drawdown Periods ---
        in_drawdown = False
        current_drawdown_peak_date = None
        current_drawdown_start_value = None
        current_drawdown_min_value = float('inf')
        current_drawdown_min_date = None

        for date, value in portfolio_values_series.items():
            peak_at_date = rolling_max.loc[date]

            if value < peak_at_date and not in_drawdown:
                # Start of a new drawdown
                in_drawdown = True
                # Find the exact date of the peak before this drawdown
                peak_dates_before = rolling_max[rolling_max == peak_at_date].index
                # Get the latest peak date that is on or before the current date
                current_drawdown_peak_date = peak_dates_before[peak_dates_before <= date].max() if not peak_dates_before[peak_dates_before <= date].empty else date # Use current date if no previous peak found (unlikely with cummax)

                current_drawdown_start_value = peak_at_date
                current_drawdown_min_value = value
                current_drawdown_min_date = date

            elif in_drawdown:
                # Within a drawdown
                if value < current_drawdown_min_value:
                    # Found a new lowest point within the current drawdown
                    current_drawdown_min_value = value
                    current_drawdown_min_date = date

                if value >= current_drawdown_start_value:
                    # Drawdown has ended (recovered to or exceeded the peak)
                    in_drawdown = False
                    drawdown_depth = (current_drawdown_min_value - current_drawdown_start_value) / current_drawdown_start_value if current_drawdown_start_value > 0 else 0.0

                    # Record the completed drawdown if it's significant (e.g., depth < -0.01 or duration > threshold)
                    # You can adjust the significance threshold
                    if drawdown_depth < 0: # Only record negative drawdowns
                         drawdown_start_date = current_drawdown_peak_date
                         drawdown_end_date = current_drawdown_min_date # End date is the lowest point date of this drawdown
                         recovery_date_for_drawdown = date # Recovery date is the date of recovery

                         # Calculate duration and recovery time
                         duration_to_bottom_days = (drawdown_end_date - drawdown_start_date).days
                         duration_to_recovery_days = (recovery_date_for_drawdown - drawdown_start_date).days

                         # Format recovery time
                         recovery_time_formatted_drawdown = "N/A"
                         if recovery_date_for_drawdown and recovery_date_for_drawdown > drawdown_start_date:
                             delta_days = (recovery_date_for_drawdown - drawdown_start_date).days
                             months = delta_days / 30.44
                             years = delta_days / 365.25
                             if years >= 1: recovery_time_formatted_drawdown = f"{years:.1f} years"
                             elif months >= 1: recovery_time_formatted_drawdown = f"{int(round(months))} months"
                             elif delta_days > 0: recovery_time_formatted_drawdown = f"{delta_days} days"
                             else: recovery_time_formatted_drawdown = "N/A"
                         # If drawdown ended at the end of the series, recovery_date_for_drawdown might be the last date
                         # And recovery_time_formatted_drawdown would be "N/A" if not fully recovered past the peak.
                         # Let's refine this: If value >= current_drawdown_start_value, it HAS recovered.

                         significant_drawdowns_list.append({
                             'start_date': drawdown_start_date.strftime('%Y-%m-%d'),
                             'end_date': drawdown_end_date.strftime('%Y-%m-%d'), # Date of the lowest point
                             'recovery_date': recovery_date_for_drawdown.strftime('%Y-%m-%d'), # Date of recovery
                             'depth': float(drawdown_depth), # Store as decimal (e.g., -0.10)
                             'duration_to_bottom_days': int(duration_to_bottom_days),
                             'duration_to_recovery_days': int(duration_to_recovery_days), # Duration from peak to recovery
                             'recovery_time_formatted': recovery_time_formatted_drawdown, # Formatted recovery time
                             'peak_value': float(current_drawdown_start_value),
                             'bottom_value': float(current_drawdown_min_value)
                         })

                            # Reset for the next potential drawdown
                         in_drawdown = False
                         current_drawdown_peak_date = None
                         current_drawdown_start_value = None
                         current_drawdown_min_value = float('inf')
                         current_drawdown_min_date = None

        # Handle a potential ongoing drawdown at the end of the series
        # If we are still in a drawdown after looping through all dates
        if in_drawdown:
            drawdown_depth = (current_drawdown_min_value - current_drawdown_start_value) / current_drawdown_start_value if current_drawdown_start_value > 0 else 0.0
            if drawdown_depth < 0: # Only record if it's a negative drawdown
                drawdown_start_date = current_drawdown_peak_date
                drawdown_end_date = current_drawdown_min_date # End date is the lowest point found
                # Recovery date is None for ongoing
                recovery_date_for_drawdown = None
                recovery_time_formatted_drawdown = "Not recovered yet"

                duration_to_bottom_days = (drawdown_end_date - drawdown_start_date).days
                duration_to_recovery_days = None # None for ongoing

                significant_drawdowns_list.append({
                    'start_date': drawdown_start_date.strftime('%Y-%m-%d'),
                    'end_date': drawdown_end_date.strftime('%Y-%m-%d'),
                    'recovery_date': None, # None for ongoing
                    'depth': float(drawdown_depth),
                    'duration_to_bottom_days': int(duration_to_bottom_days),
                    'duration_to_recovery_days': None,
                    'recovery_time_formatted': recovery_time_formatted_drawdown,
                    'peak_value': float(current_drawdown_start_value),
                    'bottom_value': float(current_drawdown_min_value)
                })


        # Sort drawdowns by depth (most severe first) and add a rank
        significant_drawdowns_list.sort(key=lambda x: x['depth']) # Sort by depth ascending (most negative first)
        for i, drawdown in enumerate(significant_drawdowns_list):
            drawdown['rank'] = i + 1 # Add a rank (1-based)


        # --- Calculate Monthly Drawdowns ---
        # Resample the daily drawdowns_series to monthly minimum drawdown
        monthly_drawdowns_series = drawdowns_series.resample("ME").min() # <-- Use "ME" and .min()
        # Convert to dictionary for JSON (Date string -> min drawdown value)
        monthly_drawdowns_dict = {
             date.strftime('%Y-%m-%d'): float(val) if np.isfinite(val) else None
             for date, val in monthly_drawdowns_series.items() # Use .items()
             if val is not None and np.isfinite(val) and val < 0 # Include only valid negative drawdowns
        }


    # --- Risk ratios (using annualized return and risk metrics) ---
    # These calculations should use the annualized_return (CAGR) and std_dev_annual, etc.
    # Ensure these variables are calculated correctly before this section.
    rf_rate_annual = 0.02
    sharpe_ratio  = ((annualized_return - rf_rate_annual) / std_dev_annual) if std_dev_annual > 0 else 0.0
    if not np.isfinite(sharpe_ratio): sharpe_ratio = 0.0

    sortino_ratio = ((annualized_return - rf_rate_annual) / downside_deviation_annual) if downside_deviation_annual > 0 else 0.0
    if not np.isfinite(sortino_ratio): sortino_ratio = 0.0


    # Skewness & kurtosis (using daily returns for better precision)
    if len(portfolio_daily_returns_series.dropna()) > 2: skewness = stats.skew(portfolio_daily_returns_series.dropna())
    else: skewness = 0.0

    if len(portfolio_daily_returns_series.dropna()) > 3: kurtosis_excess = stats.kurtosis(portfolio_daily_returns_series.dropna())
    else: kurtosis_excess = 0.0


    # Historical VaR & CVaR (using daily returns)
    returns_for_var_cvar = portfolio_daily_returns_series.dropna()
    if len(returns_for_var_cvar) >= 1: var_historic_daily = np.percentile(returns_for_var_cvar, 5)
    else: var_historic_daily = 0.0

    if len(returns_for_var_cvar[returns_for_var_cvar <= var_historic_daily]) > 0: cvar_daily = returns_for_var_cvar[returns_for_var_cvar <= var_historic_daily].mean()
    else: cvar_daily = 0.0


    # Period counts & gain/loss (using daily returns)
    positive_periods = (portfolio_daily_returns_series > 0).sum()
    negative_periods = (portfolio_daily_returns_series < 0).sum()
    total_periods    = len(portfolio_daily_returns_series)

    gains = portfolio_daily_returns_series[portfolio_daily_returns_series > 0]
    losses = portfolio_daily_returns_series[portfolio_daily_returns_series < 0]
    avg_gain = gains.mean() if not gains.empty else 0.0
    avg_loss = losses.mean() if not losses.empty else 0.0

    gain_loss_ratio = abs(avg_gain / avg_loss) if avg_loss != 0 else float('inf')


    # Trailing returns (YTD, 3-month, 6-month, etc.)
    trailing_returns = {}
    if not portfolio_values_series.empty:
        today = portfolio_values_series.index[-1]

        # YTD Return
        ytd_start_date = datetime(today.year, 1, 1).replace(tzinfo=UTC)
        vals_on_or_after_ytd_start = portfolio_values_series[portfolio_values_series.index >= ytd_start_date]
        if not vals_on_or_after_ytd_start.empty and vals_on_or_after_ytd_start.iloc[0] != 0:
             trailing_returns['YTD'] = (portfolio_values_series.iloc[-1] / vals_on_or_after_ytd_start.iloc[0]) - 1
        else:
             trailing_returns['YTD'] = 0.0


        # Trailing N-month returns (using monthly returns)
        if not monthly_returns.empty and len(monthly_returns) > 1:
             monthly_returns_for_trailing = calculate_returns(monthly_returns)

             if not monthly_returns_for_trailing.empty:
                 periods = {'3_month': 3, '6_month': 6, '1_year': 12, '3_year': 36, '5_year': 60}
                 for name, months in periods.items():
                     if len(monthly_returns_for_trailing) >= months:
                          trailing_period_returns = monthly_returns_for_trailing.tail(months)
                          cumulative_period_return = (1 + trailing_period_returns).prod() - 1

                          if months < 12 and months > 0:
                               annualized_period_return_trailing = (1 + cumulative_period_return) ** (12 / months) - 1 # Renamed to avoid conflict
                          else:
                               annualized_period_return_trailing = cumulative_period_return

                          trailing_returns[name] = annualized_period_return_trailing


        else:
             periods = ['3_month', '6_month', '1_year', '3_year', '5_year']
             for name in periods:
                  trailing_returns[name] = 0.0


    # Withdrawal rates (using annualized metrics)
    safe_withdrawal_rate = 0.04
    perpetual_withdrawal_rate = max(0.0, cagr)


    # Placeholder advanced metrics (needs implementation)
    risk_contributions_calc = {} # Ensure this is calculated
    return_contributions_calc = {} # Ensure this is calculated
    # Example: Simple Return Contributions (Weighted Daily Return)
    # This requires daily_returns and weights
    if not daily_returns.empty and not weights.empty:
         # Calculate simple return contributions (weighted daily return for each asset)
         # Returns a DataFrame where index is date, columns are tickers, values are weighted daily returns
         return_contributions_df = daily_returns * weights
         # To get a single contribution value per ticker, you might sum or average this
         # A common approach is to sum the weighted daily returns and annualize, or use cumulative return
         # Let's sum the weighted daily returns for each ticker across the period
         return_contributions_calc = return_contributions_df.sum().to_dict() # Sum daily weighted returns per ticker

         # Example: Simple Risk Contributions (Weighted Daily Standard Deviation)
         # Requires daily returns and weights
         daily_std_dev = daily_returns.std() # Daily std dev per ticker
         # A simple risk contribution could be weight * daily_std_dev
         risk_contributions_calc = (weights * daily_std_dev).to_dict()


    correlation_matrix = daily_prices.corr() if not daily_prices.empty else pd.DataFrame()

    calculated_sector_allocation = {}

    if holdings_list: # Ensure holdings_list is not empty
        sector_weights = {}
        for holding in holdings_list:
            # Ensure 'Sector' and 'Weight' keys exist and are valid
            sector = holding.get("Sector") or sector_map.get(holding.get("ticker"), "Unknown") # Default to "Unknown" if sector is missing or None
            weight = holding.get("Weight") # Get the weight

            if weight is not None and np.isfinite(weight) and weight > 0:
                display_sector = sector if sector and str(sector).strip() else "Unknown"
                if display_sector in sector_weights:
                    sector_weights[display_sector] += weight
                else:
                    sector_weights[display_sector] = weight

        # Assign the calculated sector weights dictionary to the temporary variable
        # This assignment happens ONLY if holdings_list is not empty
        calculated_sector_allocation = sector_weights

    # Assign the value from the temporary variable to the outer scope's sector_allocation_calc
    # This ensures sector_allocation_calc is always assigned before the return statement
    sector_allocation_calc = calculated_sector_allocation

    beta_calc = 0.0
    alpha_calc = 0.0

    # --- Implement Beta and Alpha Calculation ---
    benchmark_ticker = "SPY" # Define your benchmark ticker here

    # Check if benchmark ticker is in the daily_returns DataFrame columns
    if benchmark_ticker in daily_returns.columns:
        benchmark_returns_series = daily_returns[benchmark_ticker]

        # Ensure both portfolio and benchmark returns have overlapping dates and are not empty
        common_index = portfolio_daily_returns_series.index.intersection(benchmark_returns_series.index)
        if not common_index.empty and len(common_index) > 1:
            # Align returns based on the common date index
            aligned_portfolio_returns = portfolio_daily_returns_series.loc[common_index]
            aligned_benchmark_returns = benchmark_returns_series.loc[common_index]

            # Perform linear regression: portfolio_returns = alpha + beta * benchmark_returns
            # Using scipy.stats.linregress
            # Note: linregress handles NaNs by dropping corresponding pairs
            try:
                # Ensure inputs to linregress are finite
                valid_indices = np.isfinite(aligned_portfolio_returns) & np.isfinite(aligned_benchmark_returns)
                if valid_indices.sum() > 1: # Need at least 2 valid data points for regression
                    slope, intercept, r_value, p_value, std_err = stats.linregress(
                        aligned_benchmark_returns[valid_indices], # Independent variable (benchmark)
                        aligned_portfolio_returns[valid_indices] # Dependent variable (portfolio)
                    )

                    beta_calc = slope # Beta is the slope
                    # Alpha is the intercept. Annualize if using daily returns.
                    # A common way to annualize daily alpha is (1 + daily_alpha)**252 - 1
                    # Where daily_alpha = intercept
                    annualization_factor = 252 # Assuming daily data and 252 trading days in a year
                    alpha_calc = (1 + intercept)**annualization_factor - 1


                    print(f"Debug: Beta calculated: {beta_calc:.4f}, Alpha calculated (annualized): {alpha_calc:.4f}")

                else:
                    print(f"Warning: Insufficient valid data points ({valid_indices.sum()}) for Beta/Alpha regression for {benchmark_ticker}.")
                    beta_calc = 0.0
                    alpha_calc = 0.0

            except Exception as reg_err:
                 print(f"Error during Beta/Alpha linear regression: {reg_err}")
                 traceback.print_exc() # Print traceback for debug
                 beta_calc = 0.0
                 alpha_calc = 0.0

        else:
            print(f"Warning: No common date overlap or insufficient data ({len(common_index)} points) for Beta/Alpha calculation with benchmark {benchmark_ticker}.")
            beta_calc = 0.0
            alpha_calc = 0.0

    else:
        print(f"Warning: Benchmark ticker {benchmark_ticker} not found in daily_prices columns. Cannot calculate Beta and Alpha.")
        beta_calc = 0.0
        alpha_calc = 0.0


    # Calmar ratio
    calmar_ratio_calc = (cagr / abs(max_drawdown_value)) if max_drawdown_value < 0 else 0.0
    if not np.isfinite(calmar_ratio_calc): calmar_ratio_calc = 0.0


    # Asset-level metrics
    assets_metrics = {}
    # Iterate through daily returns for assets (columns of daily_returns DataFrame)
    if not daily_returns.empty:
        for ticker in daily_returns.columns:
             rets = daily_returns[ticker]

             if len(rets) < 1: continue
             print(f"Debug (Backend): Calculating metrics for asset: {ticker}")
             print(f"Debug (Backend): Returns for {ticker}: {rets.head()}") # Print head of returns Series


             asset_cagr = (1 + rets.mean())**252 - 1 if len(rets) > 0 else 0.0
             print(f"Debug (Backend): {ticker} - CAGR: {asset_cagr}")
             asset_std_dev_annual = rets.std()*np.sqrt(252) if len(rets)>1 else 0.0
             print(f"Debug (Backend): {ticker} - Std Dev Annual: {asset_std_dev_annual}")

             asset_daily_prices = daily_prices[ticker]
             asset_daily_prices = asset_daily_prices.dropna()

             asset_max_drawdown = 0.0
             if not asset_daily_prices.empty:
                  asset_rolling_max = asset_daily_prices.cummax()
                  asset_rolling_max = asset_rolling_max.replace(0, np.nan).ffill().replace(np.nan, 0)
                  asset_drawdowns = (asset_daily_prices / asset_rolling_max - 1) if not asset_rolling_max.empty and asset_rolling_max.iloc[0] != 0 else pd.Series(0.0, index=asset_daily_prices.index)
                  asset_drawdowns = asset_drawdowns.replace([np.inf, -np.inf], np.nan).dropna()
                  asset_max_drawdown = asset_drawdowns.min() if not asset_drawdowns.empty else 0.0

             asset_sharpe_ratio = ((asset_cagr - rf_rate_annual) / asset_std_dev_annual) if asset_std_dev_annual > 0 else 0.0
             print(f"Debug (Backend): {ticker} - Sharpe Ratio: {asset_sharpe_ratio}") # Add print
             if not np.isfinite(asset_sharpe_ratio): asset_sharpe_ratio = 0.0

             asset_downside_returns = rets[rets < 0]
             asset_downside_deviation_annual = np.sqrt((downside_returns_monthly ** 2).sum().mean() / len(monthly_returns)) * np.sqrt(12) if not monthly_returns.empty and len(monthly_returns) > 0 else 0.0 # Note: Re-using monthly_returns here - check if correct

             # Correction: Calculate downside deviation for the ASSET using the ASSET's daily returns
             asset_downside_returns_daily = rets[rets < 0].fillna(0) # Use asset's daily returns, fill 0
             asset_downside_deviation_daily = np.sqrt((asset_downside_returns_daily ** 2).sum() / len(rets)) if len(rets) > 0 else 0.0
             asset_downside_deviation_annual_corrected = asset_downside_deviation_daily * np.sqrt(252) if asset_downside_deviation_daily > 0 else 0.0 # Annualize daily deviation by sqrt(252)

             asset_sortino_ratio = ((asset_cagr - rf_rate_annual) / asset_downside_deviation_annual_corrected) if asset_downside_deviation_annual_corrected > 0 else 0.0 # Use corrected downside deviation
             if not np.isfinite(asset_sortino_ratio): asset_sortino_ratio = 0.0


             assets_metrics[ticker] = {
                 'cagr': asset_cagr,
                 'std_dev_annual': asset_std_dev_annual,
                 'max_drawdown': asset_max_drawdown,
                 'sharpe_ratio': asset_sharpe_ratio,
                 'sortino_ratio': asset_sortino_ratio,
                 'cumulative_return': (1 + rets).prod() - 1 if len(rets) > 0 else 0.0,
                 'best_year_return': 0.0, # Placeholder
                 'worst_year_return': 0.0 # Placeholder
             }
             print(f"Debug (Backend): {ticker} - Metrics stored in assets_metrics: {assets_metrics[ticker]}") # Print the stored metrics


    # Monthly returns data structuring for charting
    monthly_returns_data_structured_df = monthly_returns.copy()
    monthly_returns_data_structured_df['portfolio'] = (1 + monthly_returns).prod(axis=1) - 1

    monthly_returns_data_structured_df = monthly_returns_data_structured_df.fillna(0)

    monthly_returns_data_structured = {}
    if not monthly_returns_data_structured_df.empty:
         monthly_returns_data_structured = monthly_returns_data_structured_df.to_dict(orient='index')
         monthly_returns_data_structured = {
             date.strftime('%Y-%m-%d'): values
             for date, values in monthly_returns_data_structured.items()
         }

    # Final portfolio-level metrics dict
    metrics_results_dict = {
        'portfolio_overall_metrics': {
            'portfolio_name': "Portfolio", # Or get actual portfolio name if available
            'start_value': float(initial_investment_for_calc),
            'end_value': float(portfolio_values_series.iloc[-1]) if not portfolio_values_series.empty else 0.0,
            'cumulative_return': float((portfolio_values_series.iloc[-1] / portfolio_values_series.iloc[0]) - 1) if not portfolio_values_series.empty and portfolio_values_series.iloc[0] != 0 else 0.0,
            'cagr': float(annualized_return), # Use annualized_return (decimal) for CAGR
            'std_dev_monthly': float(std_dev_monthly),
            'std_dev_annual': float(std_dev_annual),
            'best_year': str(best_year_tuple[0]) if best_year_tuple[0] else 'N/A',
            'best_year_return': float(best_year_tuple[1]), # Overall best year return
            'worst_year': str(worst_year_tuple[0]) if worst_year_tuple[0] else 'N/A',
            'worst_year_return': float(worst_year_tuple[1]), # <--- Store as decimal (Fix backend bug here - use worst_year_tuple[1])
            'max_drawdown_value': float(max_drawdown_value), # Store as decimal (e.g., -0.1681)
            # Ensure dates are strings or serializable objects
            'max_drawdown_start_date': peak_before_drawdown_date.strftime('%Y-%m-%d') if peak_before_drawdown_date else None,
            'max_drawdown_end_date': max_drawdown_date.strftime('%Y-%m-%d') if max_drawdown_date else None,
            'max_drawdown_recovery_time_months': recovery_time_formatted, # Store as formatted string
            'sharpe_ratio': float(sharpe_ratio),
            'sortino_ratio': float(sortino_ratio),
            'downside_deviation_monthly': float(downside_deviation_monthly), # Store as decimal
            'downside_deviation_annual': float(downside_deviation_annual), # Store as decimal
            'mean_daily_return': float(portfolio_daily_returns_series.mean()) if not portfolio_daily_returns_series.empty else 0.0,
            'annualized_return_from_daily': float(((1 + portfolio_daily_returns_series.mean())**252 - 1)) if len(portfolio_daily_returns_series) > 0 else 0.0,
            'geometric_mean_daily': float(((1 + portfolio_daily_returns_series).prod()**(1/len(portfolio_daily_returns_series)) - 1)) if len(portfolio_daily_returns_series) > 0 else 0.0,
            'mean_monthly_return': float(mean_monthly_return) if mean_monthly_return is not None else 0.0, # Use mean_monthly_return (decimal)
            'geometric_mean_monthly': float(geometric_mean_monthly) if geometric_mean_monthly is not None else 0.0, # Store as decimal
            'geometric_mean_annual': float(geometric_mean_annual) if geometric_mean_annual is not None else 0.0, # Store as decimal
            'skewness': float(skewness),
            'excess_kurtosis': float(kurtosis_excess),
            'var_historic_daily_5pct': float(var_historic_daily), # Store as decimal
            'cvar_daily_5pct': float(cvar_daily), # Store as decimal
            'positive_periods': int(positive_periods),
            'total_periods': int(total_periods),
            'gain_loss_ratio': float(gain_loss_ratio),
            'safe_withdrawal_rate': float(rf_rate_annual), # Store as decimal
            'perpetual_withdrawal_rate': float(perpetual_withdrawal_rate), # Use perpetual_withdrawal_rate (decimal)
            'calmar_ratio': float(calmar_ratio_calc), # Use calmar_ratio_calc
            'beta': float(beta_calc), # Use calculated beta_calc
            'alpha': float(alpha_calc), # Use calculated alpha_calc

            'calculation_start_date': daily_prices.index.min().strftime('%Y-%m-%d') if not daily_prices.empty else None,
            'calculation_end_date': daily_prices.index.max().strftime('%Y-%m-%d') if not daily_prices.empty else None,
            'initial_investment_used': float(initial_investment_for_calc),
            'metrics_calculation_date': datetime.now(UTC).strftime('%Y-%m-%d')
        },
        "asset_metrics_data": assets_metrics,

        # Data for Portfolio Growth Chart (Value over time)
        "portfolio_growth_data": {
            "dates": portfolio_values_series.index.strftime('%Y-%m-%d').tolist() if not portfolio_values_series.empty else [],
            "values": portfolio_values_series.tolist() if not portfolio_values_series.empty else []
        },

        # Data for Risk/Return Decomposition Tables
        "risk_decomposition_data": [
            {
                "ticker": ticker,
                "Name": next((item['Name'] for item in holdings_list if item['ticker'] == ticker), ticker),
                "Contribution": float(risk_contributions_calc.get(ticker, 0.0)) # Store as decimal
            } for ticker in tickers_with_daily_data
        ],
        "return_decomposition_data": [
            {
                "ticker": ticker,
                "Name": next((item['Name'] for item in holdings_list if item['ticker'] == ticker), ticker),
                "Contribution": float(return_contributions_calc.get(ticker, 0.0)) # Store as decimal
            } for ticker in tickers_with_daily_data
        ],

        # Data for Holdings Table (combined from DB holdings and per-asset metrics)
        # This is populated in app/routes/portfolio_metrics.py, not here.
        # Remove or keep as a placeholder if needed for the overall structure definition.
        "holdings_table_data": [], # Assuming this is populated in the route


        # Data for Annual and Monthly Returns Tables/Charts
        # Use the calculated annual_returns_portfolio and monthly_returns_data_structured
        "annual_returns_portfolio": {str(year): float(value) if np.isfinite(value) else 0.0 for year, value in annual_returns_portfolio.items()}, # Store as decimal
        "monthly_returns_data": monthly_returns_data_structured, # Use the structured data


        # Data for Asset-level Metrics Table (populated with assets_metrics)
        # Use the calculated assets_metrics
        "asset_metrics_data": {
            ticker: {
                "CAGR": float(metrics.get('cagr', 0.0)) if np.isfinite(metrics.get('cagr', 0.0)) else 0.0, # Store as decimal
                "Standard Deviation": float(metrics.get('std_dev_annual', 0.0)) if np.isfinite(metrics.get('std_dev_annual', 0.0)) else 0.0, # Store as decimal
                "Maximum Drawdown": float(metrics.get('max_drawdown', 0.0)) if np.isfinite(metrics.get('max_drawdown', 0.0)) else 0.0, # Store as decimal
                "Sharpe Ratio": float(metrics.get('sharpe_ratio', 0.0)) if np.isfinite(metrics.get('sharpe_ratio', 0.0)) else 0.0,
                "Sortino Ratio": float(metrics.get('sortino_ratio', 0.0)) if np.isfinite(metrics.get('sortino_ratio', 0.0)) else 0.0,
                "Best Year Return": float(metrics.get('best_year_return', 0.0)) if np.isfinite(metrics.get('best_year_return', 0.0)) else 0.0, # Store as decimal
                "Worst Year Return": float(metrics.get('worst_year_return', 0.0)) if np.isfinite(metrics.get('worst_year_return', 0.0)) else 0.0, # Store as decimal
            } for ticker, metrics in assets_metrics.items()
        },

        # Data for Allocation Charts (Sector allocation)
        # Use the calculated sector_allocation_calc
        "sector_allocation_data": sector_allocation_calc, # Use the calculated dictionary

        # Other potential data: risk correlations, beta/alpha matrices, etc.
        # Use the calculated correlation_matrix, beta_calc, alpha_calc
        "correlations_data": correlation_matrix.to_dict() if correlation_matrix is not None else {},

        # Calculation period and initial investment
        "calculation_period": {
             "start_date": daily_prices.index.min().strftime('%Y-%m-%d') if not daily_prices.empty else None,
             "end_date": daily_prices.index.max().strftime('%Y-%m-%d') if not daily_prices.empty else None,
             "initial_investment": float(initial_investment_for_calc),
        },

        "metrics_calculation_date": datetime.now(UTC).strftime('%Y-%m-%d'), # Ensure comma here
        "monthly_drawdowns": monthly_drawdowns_dict, # Use the calculated monthly_drawdowns_dict
        "significant_drawdowns": significant_drawdowns_list # Use the calculated significant_drawdowns_list
    }

    
    # --- FINAL PATCH: Correct Max Drawdown using raw prices ---
    equity_curve = portfolio_values_series.dropna()
    rolling_max = equity_curve.cummax()
    drawdown_series = equity_curve / rolling_max - 1.0
    max_drawdown_value = drawdown_series.min()
    max_drawdown_date = drawdown_series.idxmin()
    peak_before_drawdown_date = equity_curve.loc[:max_drawdown_date].idxmax()

    # Format recovery time
    recovery_date = equity_curve.loc[max_drawdown_date:].idxmax()
    if recovery_date > max_drawdown_date:
        recovery_duration = recovery_date - max_drawdown_date
        recovery_time_formatted = f"{recovery_duration.days // 30} months"
    else:
        recovery_time_formatted = "N/A"

    metrics_results_dict['portfolio_overall_metrics'].update({
        'max_drawdown_value': float(max_drawdown_value),
        'max_drawdown_start_date': peak_before_drawdown_date.strftime('%Y-%m-%d') if peak_before_drawdown_date else None,
        'max_drawdown_end_date': max_drawdown_date.strftime('%Y-%m-%d') if max_drawdown_date else None,
        'max_drawdown_recovery_time_months': recovery_time_formatted
    })


    return metrics_results_dict

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
    
    # Add efficient frontier line (Risk vs. Return)
    fig.add_trace(go.Scatter(
        x=efficient_portfolios['Risk'],
        y=efficient_portfolios['Return'],
        mode='lines',
        name='Efficient Frontier',
        line=dict(color='blue', width=2)
    ))
    
    # Add individual assets (using standard deviation vs. expected return)
    for i, asset in asset_metrics.iterrows():
        fig.add_trace(go.Scatter(
            x=[asset['Standard Deviation']],
            y=[asset['Expected Return']],
            mode='markers',
            name=asset['Asset'],
            marker=dict(size=10, opacity=0.8),
            text=[asset['Asset']]
        ))
    
    # Add tangency portfolio
    fig.add_trace(go.Scatter(
        x=[tangency_portfolio['risk']],
        y=[tangency_portfolio['return']],
        mode='markers',
        name='Tangency Portfolio',
        marker=dict(size=12, symbol='star', color='green'),
        text=['Tangency Portfolio']
    ))
    
    # Add max information ratio portfolio
    fig.add_trace(go.Scatter(
        x=[max_info_portfolio['risk']],
        y=[max_info_portfolio['return']],
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
            x=[equal_weight['Risk']],
            y=[equal_weight['Return']],
            mode='markers+text',
            name='222',
            marker=dict(size=10, color='black'),
            text=['222'],
            textposition='bottom center'
        ))
    
    # Update layout
    fig.update_layout(
        title="Mean-Variance Efficient Frontier",
        xaxis_title="Annualized Risk (Std Dev)",
        yaxis_title="Annualized Return",
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
            x=efficient_portfolios['Risk'],
            y=cumulative_weights + efficient_portfolios[asset] * 100,  # Convert to percentage
            mode='lines',
            name=asset,
            fill='tonexty',
            line=dict(width=0)
        ))
        cumulative_weights += efficient_portfolios[asset] * 100
    
    # Update layout
    fig.update_layout(
        title="Mean-Variance Efficient Frontier Transition Map",
        xaxis_title="Annualized Risk (Std Dev)",
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

# Ensure calculate_portfolio_metrics calls these helper functions with the correct data format.