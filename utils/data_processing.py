import pandas as pd
import numpy as np
import io

def load_data(holdings_file, prices_file):
    """
    Load and validate portfolio holdings and price data from uploaded files.
    
    Args:
        holdings_file: File object containing portfolio holdings data
        prices_file: File object containing price history data
    
    Returns:
        tuple: (holdings_df, prices_df) DataFrames
    """
    # Read holdings data
    holdings_content = holdings_file.read()
    holdings_df = pd.read_csv(io.StringIO(holdings_content.decode('utf-8')))
    
    # Read price history data
    prices_content = prices_file.read()
    prices_df = pd.read_csv(io.StringIO(prices_content.decode('utf-8')))
    
    # Ensure price data has date as index
    date_col = prices_df.columns[0]
    prices_df[date_col] = pd.to_datetime(prices_df[date_col])
    prices_df.set_index(date_col, inplace=True)
    
    # Validate holdings data
    required_columns = ['Ticker', 'Name', 'Category', 'Weight']
    for col in required_columns:
        if col not in holdings_df.columns:
            raise ValueError(f"Missing required column in holdings data: {col}")
    
    # Ensure weights sum to 1 (100%)
    if abs(holdings_df['Weight'].sum() - 1) > 0.01:  # Allow 1% tolerance
        holdings_df['Weight'] = holdings_df['Weight'] / holdings_df['Weight'].sum()
    
    return holdings_df, prices_df

def process_portfolio_data(holdings_df, prices_df):
    """
    Process holdings and price data to create portfolio time series and returns.
    
    Args:
        holdings_df: DataFrame with portfolio holdings
        prices_df: DataFrame with price history
    
    Returns:
        tuple: (portfolio_data, assets_data, returns_data)
            - portfolio_data: Dict with portfolio values and returns time series
            - assets_data: Dict with asset details and allocations
            - returns_data: Dict with returns for each asset
    """
    # Ensure date index is properly formatted
    prices_df.index = pd.to_datetime(prices_df.index)
    prices_df = prices_df.sort_index()
    
    # Extract tickers from holdings
    tickers = holdings_df['Ticker'].tolist()
    
    # Filter price data to include only portfolio assets
    portfolio_prices = prices_df[tickers].copy()
    
    # Calculate returns for each asset
    returns = portfolio_prices.pct_change().dropna()
    
    # Calculate weighted returns for the portfolio
    weighted_returns = pd.DataFrame(index=returns.index)
    
    for ticker in tickers:
        weight = holdings_df.loc[holdings_df['Ticker'] == ticker, 'Weight'].values[0]
        weighted_returns[ticker] = returns[ticker] * weight
    
    # Calculate portfolio returns
    portfolio_returns = weighted_returns.sum(axis=1)
    
    # Calculate cumulative portfolio value (starting with $10,000)
    initial_investment = 10000
    portfolio_values = initial_investment * (1 + portfolio_returns).cumprod()
    
    # Create monthly returns dataframe
    monthly_returns = portfolio_returns.resample('M').apply(lambda x: (1 + x).prod() - 1)
    
    # Calculate monthly values
    monthly_values = portfolio_values.resample('M').last()
    
    # Calculate annual returns
    annual_returns = {}
    for year in monthly_returns.index.year.unique():
        year_returns = monthly_returns[monthly_returns.index.year == year]
        annual_returns[year] = (1 + year_returns).prod() - 1
    
    # Extract more detailed asset data
    assets_data = []
    
    for _, row in holdings_df.iterrows():
        ticker = row['Ticker']
        
        # Calculate contribution to return
        if ticker in returns.columns:
            # Last 12 months return
            last_12m_return = (1 + returns[ticker].tail(12)).prod() - 1 if len(returns) >= 12 else (1 + returns[ticker]).prod() - 1
            
            # Risk (standard deviation of returns)
            risk = returns[ticker].std() * np.sqrt(12)  # Annualized
        else:
            last_12m_return = np.nan
            risk = np.nan
        
        asset_data = {
            'Ticker': ticker,
            'Name': row['Name'],
            'Category': row['Category'],
            'Weight': row['Weight'],
            'Yield': row.get('Yield', np.nan),
            'Expense_Ratio': row.get('Expense_Ratio', np.nan),
            'PE': row.get('PE', np.nan),
            'Return_Contribution': last_12m_return * row['Weight'],
            'Return': last_12m_return,
            'Risk': risk
        }
        assets_data.append(asset_data)
    
    assets_df = pd.DataFrame(assets_data)
    
    # Create returns dictionary for each asset
    returns_data = {}
    for ticker in tickers:
        if ticker in returns.columns:
            returns_data[ticker] = returns[ticker]
    
    # Create portfolio data dictionary
    portfolio_data = {
        'values': portfolio_values,
        'returns': portfolio_returns,
        'monthly_values': monthly_values,
        'monthly_returns': monthly_returns,
        'annual_returns': annual_returns
    }
    
    return portfolio_data, assets_df, returns_data
