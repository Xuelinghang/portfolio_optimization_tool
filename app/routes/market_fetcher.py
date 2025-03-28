import yfinance as yf
import requests
import json
from alpha_vantage.timeseries import TimeSeries
from apscheduler.schedulers.background import BackgroundScheduler
from flask_sqlalchemy import SQLAlchemy
from flask import Flask
import time

# Initialize Flask & Database
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///portfolio.db"
db = SQLAlchemy(app)

# Alpha Vantage API Key
ALPHA_VANTAGE_API_KEY = "your_alpha_vantage_api_key"

# Define MarketData Model
class MarketData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False)
    price = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, server_default=db.func.current_timestamp())

# Yahoo Finance (stocks, ETFs, mutual funds)
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

# Alpha Vantage - quote endpoint (stocks, ETFs)
def fetch_alpha_vantage_data(symbol):
    try:
        ts = TimeSeries(key=ALPHA_VANTAGE_API_KEY, output_format="json")
        data, _ = ts.get_quote_endpoint(symbol=symbol)
        return float(data["05. price"])
    except Exception as e:
        print(f"Alpha Vantage error for {symbol}: {e}")
        return None

# Alpha Vantage - Treasury bond yields
def fetch_alpha_vantage_bond_yield(maturity="10year"):
    try:
        url = (
            f"https://www.alphavantage.co/query?"
            f"function=TREASURY_YIELD&interval=daily&maturity={maturity}&apikey={ALPHA_VANTAGE_API_KEY}"
        )
        response = requests.get(url, timeout=10)
        data = response.json()

        # Try to extract the most recent yield
        yields = data.get("data", [])
        if not yields:
            raise ValueError("No bond data available")
        latest_yield = float(yields[0]["value"])
        return latest_yield
    except Exception as e:
        print(f"Bond yield fetch error for {maturity}: {e}")
        return None

# CoinGecko (crypto)
def fetch_coingecko_data(crypto_id):
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto_id}&vs_currencies=usd"
        response = requests.get(url, timeout=10)
        data = response.json()
        return data.get(crypto_id, {}).get("usd")
    except Exception as e:
        print(f"CoinGecko error for {crypto_id}: {e}")
        return None

# Save price to DB
def store_market_data(symbol, price):
    if price is not None:
        entry = MarketData(symbol=symbol, price=price)
        db.session.add(entry)
        db.session.commit()
        print(f"[Saved] {symbol}: ${price}")

# Scheduled job
def fetch_market_data():
    print("\n[Fetching market data...]")
    assets = {
        "AAPL": "yahoo",
        "SPY": "yahoo",
        "VFINX": "yahoo",
        "bitcoin": "crypto",
        "10Y": "bond"
    }

    for symbol, asset_type in assets.items():
        if asset_type == "yahoo":
            price = fetch_yahoo_data(symbol) or fetch_alpha_vantage_data(symbol)
        elif asset_type == "crypto":
            price = fetch_coingecko_data(symbol)
        elif asset_type == "bond":
            price = fetch_alpha_vantage_bond_yield("10year")
        else:
            price = None

        store_market_data(symbol, price)
        time.sleep(1)  # Prevent rate limit

# Schedule periodic task
scheduler = BackgroundScheduler()
scheduler.add_job(fetch_market_data, "interval", hours=1)
scheduler.start()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        fetch_market_data()  # Fetch immediately once
    print("Market data fetcher running (with bond support)...")
