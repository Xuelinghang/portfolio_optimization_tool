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

# Fetch Stock/ETF/Mutual Fund Data from Yahoo Finance
def fetch_yahoo_data(symbol):
    try:
        stock = yf.Ticker(symbol)
        data = stock.history(period="1d")
        if data.empty:
            raise ValueError(f"No data for {symbol}")
        return data["Close"].iloc[-1]  # Last closing price
    except Exception as e:
        print(f"Yahoo Finance error: {e}")
        return None

# Fetch Stock/ETF Data from Alpha Vantage
def fetch_alpha_vantage_data(symbol):
    try:
        ts = TimeSeries(key=ALPHA_VANTAGE_API_KEY, output_format="json")
        data, meta_data = ts.get_quote_endpoint(symbol=symbol)
        if "05. price" not in data:
            raise ValueError(f"No data from Alpha Vantage for {symbol}")
        return float(data["05. price"])
    except Exception as e:
        print(f"Alpha Vantage error: {e}")
        return None

# Fetch Crypto Data from CoinGecko
def fetch_coingecko_data(crypto_id):
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto_id}&vs_currencies=usd"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            raise ValueError(f"CoinGecko API error: {response.status_code}")
        data = response.json()
        return data.get(crypto_id, {}).get("usd")
    except Exception as e:
        print(f"CoinGecko error: {e}")
        return None

# Save Data to Database
def store_market_data(symbol, price):
    if price is not None:
        new_entry = MarketData(symbol=symbol, price=price)
        db.session.add(new_entry)
        db.session.commit()
        print(f"Saved {symbol}: ${price}")

# Market Data Fetching Job
def fetch_market_data():
    assets = ["AAPL", "MSFT", "SPY", "VTSAX", "bitcoin"]  # Example symbols
    for asset in assets:
        if asset.isalpha():
            price = fetch_yahoo_data(asset) or fetch_alpha_vantage_data(asset)
        else:
            price = fetch_coingecko_data(asset)
        store_market_data(asset, price)
        time.sleep(1)  # Avoid rate limits

# Schedule Market Data Fetching Every Hour
scheduler = BackgroundScheduler()
scheduler.add_job(fetch_market_data, "interval", hours=1)
scheduler.start()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        fetch_market_data()  # Fetch once on startup
    print("Market data fetcher is running...")
