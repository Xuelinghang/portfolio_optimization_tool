import os
import yfinance as yf
import requests
import pandas as pd
from alpha_vantage.timeseries import TimeSeries
from apscheduler.schedulers.background import BackgroundScheduler
import time
from datetime import datetime, timedelta
import json

from app import create_app, db
from app.models import Asset, MarketData

app = create_app()
app.app_context().push()

# Environment variable keys
ALPHA_VANTAGE_API_KEY = os.environ.get('ALPHA_VANTAGE_API_KEY', '')
YAHOO_FINANCE_API_KEY = os.environ.get('YAHOO_FINANCE_API_KEY', '')
FRED_API_KEY = os.environ.get('FRED_API_KEY', '')
COINGECKO_API_KEY = os.environ.get('COINGECKO_API_KEY', '')

def fetch_yahoo_data(symbol, period="1mo", interval="1d"):
    """
    Fetch data from Yahoo Finance
    
    Args:
        symbol: Stock/ETF symbol
        period: Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
        interval: Data interval (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)
    
    Returns:
        DataFrame with historical price data or latest price if period='1d'
    """
    try:
        # Normalize the ticker by removing whitespace and converting to uppercase
        symbol = symbol.strip().upper()
        
        # Use yfinance to get real data
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        
        if period == "1d" or period == "current":
            # Get the latest real-time price data
            # Setting prepost=True to include pre-market and post-market data
            hist = ticker.history(period="1d", prepost=True)
            
            if hist.empty:
                print(f"No price data found for {symbol}")
                # Try alpha vantage as a fallback
                if ALPHA_VANTAGE_API_KEY:
                    alpha_price = fetch_alpha_vantage_data(symbol, "TIME_SERIES_DAILY")
                    if alpha_price is not None:
                        return alpha_price
                return None
                
            latest_price = hist['Close'].iloc[-1]
            print(f"[Fetched] {symbol}: ${latest_price:.2f}")
            return latest_price
        
        # Get historical data for the specified period with improved parameters
        # Setting actions=True to include dividends and stock splits
        # Including prepost=True for more complete data
        hist = ticker.history(period=period, interval=interval, 
                             actions=True, prepost=True)
        
        if hist.empty:
            print(f"No historical data found for {symbol}")
            return None
        
        # For max recency, try to get up to the current minute if we're asking for recent data
        if period in ["1d", "5d", "1mo"] and interval in ["1m", "5m", "15m", "30m", "60m"]:
            try:
                # Attempt to get very recent intraday data
                live_data = ticker.history(period="1d", interval="1m", prepost=True)
                if not live_data.empty:
                    # Append the most recent live data
                    hist = pd.concat([hist, live_data.loc[hist.index[-1]:]])
            except Exception as e:
                print(f"Warning: Could not get live data for {symbol}: {e}")
            
        # Print how many data points we got
        print(f"Ticker {symbol}: Got {len(hist)} data points from Yahoo Finance (up to {hist.index[-1]})")
        
        return hist
    except Exception as e:
        print(f"Yahoo Finance error for {symbol}: {e}")
        return None

def fetch_alpha_vantage_data(symbol, function="TIME_SERIES_DAILY"):
    """
    Fetch data from Alpha Vantage
    
    Args:
        symbol: Stock/ETF symbol
        function: Alpha Vantage API function (TIME_SERIES_DAILY, TIME_SERIES_WEEKLY, etc.)
    
    Returns:
        DataFrame with historical price data or latest price
    """
    try:
        url = (
            f"https://www.alphavantage.co/query?"
            f"function={function}&symbol={symbol}&apikey={ALPHA_VANTAGE_API_KEY}&outputsize=compact"
        )
        response = requests.get(url, timeout=10)
        data = response.json()
        
        # Check for error messages
        if "Error Message" in data:
            raise ValueError(f"Alpha Vantage error: {data['Error Message']}")
        
        # Get the time series data
        if function == "TIME_SERIES_DAILY":
            time_series = data.get("Time Series (Daily)", {})
        elif function == "TIME_SERIES_WEEKLY":
            time_series = data.get("Weekly Time Series", {})
        elif function == "TIME_SERIES_MONTHLY":
            time_series = data.get("Monthly Time Series", {})
        elif function == "GLOBAL_QUOTE":
            # For single price quote
            return float(data.get("Global Quote", {}).get("05. price", 0))
        else:
            time_series = {}
        
        if not time_series:
            raise ValueError(f"No time series data available for {symbol}")
        
        # Convert to DataFrame
        df = pd.DataFrame(time_series).T
        # Rename columns
        df.columns = [col.split(". ")[1] for col in df.columns]
        # Convert string values to float
        for col in df.columns:
            df[col] = df[col].astype(float)
        # Reset index and rename to date
        df = df.reset_index().rename(columns={"index": "date"})
        # Convert date to datetime
        df["date"] = pd.to_datetime(df["date"])
        # Sort by date
        df = df.sort_values("date")
        
        # Return the full DataFrame for historical data
        if function != "GLOBAL_QUOTE":
            return df
            
        # Return latest price for quotea
        return df.iloc[-1]["close"]
    except Exception as e:
        print(f"Alpha Vantage error for {symbol}: {e}")
        return None

def fetch_alpha_vantage_bond_yield(maturity="10year"):
    """
    Fetch Treasury yield data from Alpha Vantage
    
    Args:
        maturity: Bond maturity period (3month, 2year, 5year, 7year, 10year, 30year)
    
    Returns:
        Latest yield value or DataFrame with historical yields
    """
    try:
        url = (
            f"https://www.alphavantage.co/query?"
            f"function=TREASURY_YIELD&interval=daily&maturity={maturity}&apikey={ALPHA_VANTAGE_API_KEY}"
        )
        response = requests.get(url, timeout=10)
        data = response.json()
        yields_data = data.get("data", [])
        
        if not yields_data:
            raise ValueError("No bond data available")
            
        # Get latest yield
        latest_yield = float(yields_data[0]["value"])
        return latest_yield
    except Exception as e:
        print(f"Bond yield fetch error for {maturity}: {e}")
        return None

def fetch_fred_data(series_id, start_date=None, end_date=None):
    """
    Fetch economic data from FRED (Federal Reserve Economic Data)
    
    Args:
        series_id: FRED series identifier (e.g., 'GDP', 'UNRATE', 'CPIAUCSL')
        start_date: Start date for data (YYYY-MM-DD)
        end_date: End date for data (YYYY-MM-DD)
    
    Returns:
        DataFrame with historical data or latest value
    """
    try:
        # Set default dates if not provided
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')
        if not start_date:
            # Default to 1 year of data
            start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
            
        url = (
            f"https://api.stlouisfed.org/fred/series/observations?"
            f"series_id={series_id}&api_key={FRED_API_KEY}&file_type=json&"
            f"observation_start={start_date}&observation_end={end_date}"
        )
        response = requests.get(url, timeout=10)
        data = response.json()
        observations = data.get("observations", [])
        
        if not observations:
            raise ValueError(f"No data available for {series_id}")
            
        # Convert to DataFrame
        df = pd.DataFrame(observations)
        # Convert date to datetime
        df["date"] = pd.to_datetime(df["date"])
        # Convert value to float (handling missing values)
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        # Sort by date
        df = df.sort_values("date")
        
        # Return the full DataFrame
        return df
    except Exception as e:
        print(f"FRED error for {series_id}: {e}")
        return None

def fetch_coingecko_data(crypto_id, vs_currency="usd", days="30"):
    """
    Fetch cryptocurrency data from CoinGecko
    
    Args:
        crypto_id: CoinGecko crypto ID (e.g., 'bitcoin', 'ethereum')
        vs_currency: Conversion currency (default 'usd')
        days: Amount of historical data to fetch (default '30')
    
    Returns:
        DataFrame with historical data or latest price
    """
    try:
        headers = {}
        if COINGECKO_API_KEY:
            headers["x-cg-api-key"] = COINGECKO_API_KEY
            
        # For latest price only
        if days == "0":
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto_id}&vs_currencies={vs_currency}"
            response = requests.get(url, headers=headers, timeout=10)
            data = response.json()
            return data.get(crypto_id, {}).get(vs_currency)
        
        # For historical data
        url = (
            f"https://api.coingecko.com/api/v3/coins/{crypto_id}/market_chart?"
            f"vs_currency={vs_currency}&days={days}&interval=daily"
        )
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        
        # Extract price data
        prices = data.get("prices", [])
        if not prices:
            raise ValueError(f"No price data available for {crypto_id}")
            
        # Convert to DataFrame
        df = pd.DataFrame(prices, columns=["timestamp", "price"])
        # Convert timestamp to datetime
        df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
        # Drop original timestamp column
        df = df.drop("timestamp", axis=1)
        
        # Return full DataFrame
        return df
    except Exception as e:
        print(f"CoinGecko error for {crypto_id}: {e}")
        return None

def store_market_data(asset, price=None, prices_df=None):
    """
    Store market data in database
    
    Args:
        asset: Asset object
        price: Latest price (for single price update)
        prices_df: DataFrame with historical prices (for bulk update)
    """
    try:
        if price is not None:
            # Store single price point
            entry = MarketData(asset_id=asset.id, price=price, date=datetime.utcnow())
            db.session.add(entry)
            db.session.commit()
            print(f"[Saved] {asset.symbol}: ${price}")
            
        elif prices_df is not None:
            # Store historical price data
            entries = []
            
            # Check if we have a 'date' and 'price' or 'close' column
            if 'date' in prices_df.columns and ('price' in prices_df.columns or 'close' in prices_df.columns):
                price_column = 'price' if 'price' in prices_df.columns else 'close'
                
                # Create MarketData objects
                for _, row in prices_df.iterrows():
                    entries.append(MarketData(
                        asset_id=asset.id,
                        price=float(row[price_column]),
                        date=row['date']
                    ))
                
                # Bulk insert
                db.session.bulk_save_objects(entries)
                db.session.commit()
                print(f"[Saved] {asset.symbol}: {len(entries)} historical data points")
            else:
                print(f"[Error] DataFrame for {asset.symbol} missing required columns")
    except Exception as e:
        db.session.rollback()
        print(f"Database error storing data for {asset.symbol}: {e}")

def fetch_market_data(historical=False):
    """
    Fetch market data for all assets in database
    
    Args:
        historical: Whether to fetch historical data or just latest prices
    """
    print("\n[Fetching market data...]")
    assets = Asset.query.all()
    
    for asset in assets:
        try:
            if historical:
                # Fetch and store historical data
                if asset.asset_type.lower() in ["stock", "etf"]:
                    # Try Yahoo Finance first with more recent data, then Alpha Vantage as backup
                    # Use a shorter timeframe (1mo) with a smaller interval (1h) for more recent data
                    prices_df = fetch_yahoo_data(asset.symbol, period="1mo", interval="1h")
                    
                    # If we got recent data, also get historical data and merge them
                    if prices_df is not None and not prices_df.empty:
                        # Also get longer-term data
                        historical_df = fetch_yahoo_data(asset.symbol, period="1y", interval="1d")
                        if historical_df is not None and not historical_df.empty:
                            # Combine the datasets, with recent data taking precedence
                            combined_df = pd.concat([historical_df, prices_df.loc[historical_df.index[-1]:]])
                            prices_df = combined_df
                    # If Yahoo fails, try Alpha Vantage        
                    elif prices_df is None or (isinstance(prices_df, pd.DataFrame) and prices_df.empty):
                        prices_df = fetch_alpha_vantage_data(asset.symbol, function="TIME_SERIES_DAILY")
                    
                    if prices_df is not None and not isinstance(prices_df, float):
                        store_market_data(asset, prices_df=prices_df)
                
                elif asset.asset_type.lower() == "crypto":
                    prices_df = fetch_coingecko_data(asset.symbol, days="365")
                    if prices_df is not None and isinstance(prices_df, pd.DataFrame) and not prices_df.empty:
                        store_market_data(asset, prices_df=prices_df)
                
                elif asset.asset_type.lower() == "bond":
                    # FRED for historical bond data
                    if asset.symbol == "10YEAR":
                        prices_df = fetch_fred_data("DGS10")  # 10-Year Treasury Constant Maturity Rate
                    elif asset.symbol == "5YEAR":
                        prices_df = fetch_fred_data("DGS5")   # 5-Year Treasury Constant Maturity Rate
                    elif asset.symbol == "30YEAR":
                        prices_df = fetch_fred_data("DGS30")  # 30-Year Treasury Constant Maturity Rate
                    else:
                        prices_df = None
                        
                    if prices_df is not None and isinstance(prices_df, pd.DataFrame) and not prices_df.empty:
                        # Rename columns to match our structure
                        prices_df = prices_df.rename(columns={"value": "price"})
                        store_market_data(asset, prices_df=prices_df)
            else:
                # Fetch and store latest price only
                if asset.asset_type.lower() in ["stock", "etf"]:
                    yahoo_price = fetch_yahoo_data(asset.symbol)
                    if yahoo_price is not None and not isinstance(yahoo_price, pd.DataFrame):
                        price = yahoo_price
                    else:
                        price = fetch_alpha_vantage_data(asset.symbol, function="GLOBAL_QUOTE")
                elif asset.asset_type.lower() == "crypto":
                    price = fetch_coingecko_data(asset.symbol, days="0")
                elif asset.asset_type.lower() == "bond":
                    if asset.symbol == "10YEAR":
                        price = fetch_alpha_vantage_bond_yield("10year")
                    elif asset.symbol == "5YEAR":
                        price = fetch_alpha_vantage_bond_yield("5year")
                    elif asset.symbol == "30YEAR":
                        price = fetch_alpha_vantage_bond_yield("30year")
                    else:
                        price = None
                else:
                    price = None
                
                store_market_data(asset, price=price)
        except Exception as e:
            print(f"Error processing {asset.symbol}: {e}")
        
        # For testing only - no delay
        pass  # time.sleep(1.5)

def get_historical_data_for_asset(asset_id, start_date=None, end_date=None):
    """
    Get historical data for a specific asset from database
    
    Args:
        asset_id: Asset ID
        start_date: Start date (datetime)
        end_date: End date (datetime)
    
    Returns:
        DataFrame with historical prices
    """
    try:
        # Set default dates if not provided
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            # Default to 1 year of data
            start_date = end_date - timedelta(days=365)
            
        # Query database
        query = MarketData.query.filter(MarketData.asset_id == asset_id)
        
        if start_date:
            query = query.filter(MarketData.date >= start_date)
        if end_date:
            query = query.filter(MarketData.date <= end_date)
            
        data = query.order_by(MarketData.date).all()
        
        if not data or len(data) == 0:
            return None
            
        # Convert to DataFrame
        df = pd.DataFrame([(item.date, item.price) for item in data], columns=["date", "price"])
        return df
    except Exception as e:
        print(f"Error fetching historical data for asset {asset_id}: {e}")
        return None

def initialize_scheduler():
    """Initialize the background scheduler for market data updates"""
    scheduler = BackgroundScheduler()
    
    # Schedule data updates
    scheduler.add_job(lambda: fetch_market_data(historical=False), "interval", hours=1)
    
    # Once a day, update historical data
    scheduler.add_job(lambda: fetch_market_data(historical=True), "cron", hour=1, minute=0)
    
    scheduler.start()
    print("Market data scheduler initialized")
    
    return scheduler

# Don't initialize scheduler automatically when imported
# Instead, the scheduler will be initialized by the Flask app
scheduler = None

def init():
    """Initialize the market fetcher module with scheduler"""
    global scheduler
    if scheduler is None:
        scheduler = initialize_scheduler()
    return scheduler

if __name__ == "__main__":
    # If run directly, fetch market data immediately
    scheduler = initialize_scheduler()
    fetch_market_data(historical=True)
    print("Market data fetcher running...")