import yfinance as yf
import requests
import json
from alpha_vantage.timeseries import TimeSeries

ALPHA_VANTAGE_API_KEY = ""

def fetch_yahoo_finance_data(symbol):
    """Fetch stock, ETF, mutual fund, or bond data from Yahoo Finance with error handling."""
    try:
        asset = yf.Ticker(symbol)
        data = asset.history(period="1mo")  # Fetch last 1 month of data

        if data.empty:
            raise ValueError(f"No data found for symbol: {symbol}")

        return data
    except ValueError as ve:
        return {"error": str(ve)}
    except Exception as e:
        return {"error": f"Failed to fetch Yahoo Finance data: {str(e)}"}

def fetch_alpha_vantage_data(symbol):
    """Fetch stock or ETF data from Alpha Vantage with error handling."""
    try:
        ts = TimeSeries(key=ALPHA_VANTAGE_API_KEY, output_format="json")
        data, meta_data = ts.get_daily(symbol=symbol, outputsize="compact")

        if not data:
            raise ValueError(f"No data returned for symbol: {symbol}")

        return data
    except ValueError as ve:
        return {"error": str(ve)}
    except requests.exceptions.RequestException as re:
        return {"error": f"Network error while fetching Alpha Vantage data: {str(re)}"}
    except Exception as e:
        return {"error": f"Failed to fetch Alpha Vantage data: {str(e)}"}

def fetch_coingecko_data(crypto_id):
    """Fetch cryptocurrency data from CoinGecko with error handling."""
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto_id}&vs_currencies=usd"
        response = requests.get(url, timeout=10)  # 10-second timeout

        if response.status_code != 200:
            raise ValueError(f"CoinGecko API returned error code: {response.status_code}")

        data = response.json()

        if crypto_id not in data:
            raise ValueError(f"No data found for cryptocurrency: {crypto_id}")

        return data
    except ValueError as ve:
        return {"error": str(ve)}
    except requests.exceptions.Timeout:
        return {"error": "CoinGecko request timed out"}
    except requests.exceptions.RequestException as re:
        return {"error": f"Network error while fetching CoinGecko data: {str(re)}"}
    except Exception as e:
        return {"error": f"Failed to fetch CoinGecko data: {str(e)}"}

def fetch_alpha_vantage_bond(bond_maturity):
    """Fetch U.S. Treasury bond yield data from Alpha Vantage."""
    try:
        url = f"https://www.alphavantage.co/query?function=TREASURY_YIELD&interval=monthly&maturity={bond_maturity}&apikey={ALPHA_VANTAGE_API_KEY}"
        response = requests.get(url)

        if response.status_code != 200:
            raise ValueError(f"Alpha Vantage API returned error code: {response.status_code}")

        data = response.json()
        return data
    except requests.exceptions.RequestException as re:
        return {"error": f"Network error while fetching bond data: {str(re)}"}
    except Exception as e:
        return {"error": f"Failed to fetch bond data: {str(e)}"}

if __name__ == "__main__":
    stock_symbol = "AAPL"  # Example stock
    etf_symbol = "SPY"  # S&P 500 ETF
    mutual_fund_symbol = "VFINX"  # Vanguard 500 Index Fund
    crypto_id = "bitcoin"  # Example cryptocurrency
    bond_maturity = "10year"  # U.S. 10-Year Treasury Bond

    yahoo_stock_data = fetch_yahoo_finance_data(stock_symbol)
    yahoo_etf_data = fetch_yahoo_finance_data(etf_symbol)
    yahoo_mutual_fund_data = fetch_yahoo_finance_data(mutual_fund_symbol)
    alpha_vantage_stock_data = fetch_alpha_vantage_data(stock_symbol)
    coingecko_data = fetch_coingecko_data(crypto_id)
    alpha_vantage_bond_data = fetch_alpha_vantage_bond(bond_maturity)

    print("Yahoo Finance Stock Data:", yahoo_stock_data)
    print("Yahoo Finance ETF Data:", yahoo_etf_data)
    print("Yahoo Finance Mutual Fund Data:", yahoo_mutual_fund_data)
    print("Alpha Vantage Stock Data:", alpha_vantage_stock_data)
    print("CoinGecko Data:", coingecko_data)
    print("Alpha Vantage Bond Data:", alpha_vantage_bond_data)
