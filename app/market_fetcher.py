import yfinance as yf
import requests
from alpha_vantage.timeseries import TimeSeries
from apscheduler.schedulers.background import BackgroundScheduler
import time
from datetime import datetime

from app import create_app, db
from app.models import Asset, MarketData

app = create_app()
app.app_context().push()

# Alpha Vantage API Key (replace with your key)
ALPHA_VANTAGE_API_KEY = "your_alpha_vantage_api_key"

def fetch_yahoo_data(symbol):
    try:
        asset = yf.Ticker(symbol)
        data = asset.history(period="1d")
        if data.empty:
            raise ValueError(f"No Yahoo data for {symbol}")
        return data["Close"].iloc[-1]
    except Exception as e:
        print(f"Yahoo Finance error for {symbol}: {e}")
        return None

def fetch_alpha_vantage_data(symbol):
    try:
        ts = TimeSeries(key=ALPHA_VANTAGE_API_KEY, output_format="json")
        data, _ = ts.get_quote_endpoint(symbol=symbol)
        return float(data["05. price"])
    except Exception as e:
        print(f"Alpha Vantage error for {symbol}: {e}")
        return None

def fetch_alpha_vantage_bond_yield(maturity="10year"):
    try:
        url = (
            f"https://www.alphavantage.co/query?"
            f"function=TREASURY_YIELD&interval=daily&maturity={maturity}&apikey={ALPHA_VANTAGE_API_KEY}"
        )
        response = requests.get(url, timeout=10)
        data = response.json()
        yields = data.get("data", [])
        if not yields:
            raise ValueError("No bond data available")
        latest_yield = float(yields[0]["value"])
        return latest_yield
    except Exception as e:
        print(f"Bond yield fetch error for {maturity}: {e}")
        return None

def fetch_coingecko_data(crypto_id):
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto_id}&vs_currencies=usd"
        response = requests.get(url, timeout=10)
        data = response.json()
        return data.get(crypto_id, {}).get("usd")
    except Exception as e:
        print(f"CoinGecko error for {crypto_id}: {e}")
        return None

def store_market_data(asset, price):
    if price is not None:
        entry = MarketData(asset_id=asset.id, price=price, date=datetime.utcnow())
        db.session.add(entry)
        db.session.commit()
        print(f"[Saved] {asset.symbol}: ${price}")

def fetch_market_data():
    print("\n[Fetching market data...]")
    assets = Asset.query.all()
    for asset in assets:
        if asset.asset_type.lower() in ["stock", "etf"]:
            price = fetch_yahoo_data(asset.symbol) or fetch_alpha_vantage_data(asset.symbol)
        elif asset.asset_type.lower() == "crypto":
            price = fetch_coingecko_data(asset.symbol)
        elif asset.asset_type.lower() == "bond":
            price = fetch_alpha_vantage_bond_yield("10year")
        else:
            price = None
        
        store_market_data(asset, price)
        time.sleep(1)  # To help avoid rate limits

scheduler = BackgroundScheduler()
scheduler.add_job(fetch_market_data, "interval", hours=1)
scheduler.start()

if __name__ == "__main__":
    fetch_market_data()
    print("Market data fetcher running...")
