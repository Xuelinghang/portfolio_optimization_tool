# app/market_fetcher.py

import os
import yfinance as yf
import requests
import pandas as pd
from alpha_vantage.timeseries import TimeSeries 
from apscheduler.schedulers.background import BackgroundScheduler
import time
from datetime import datetime, timedelta, date, UTC
import json
import traceback
import numpy as np
from app import db
from app.models import User, Portfolio, Asset, MarketData, PortfolioAsset, Transaction, CalculationResult

ALPHA_VANTAGE_API_KEY = os.environ.get('ALPHA_VANTAGE_API_KEY', '')
YAHOO_FINANCE_API_KEY = os.environ.get('YAHOO_FINANCE_API_KEY', '')
FRED_API_KEY = os.environ.get('FRED_API_KEY', '')
COINGECKO_API_KEY = os.environ.get('COINGECKO_API_KEY', '')

# --- New: Global variable to cache the CoinGecko ID map ---
_coingecko_id_map_cache = None

# Replace your existing _get_coingecko_id_map function with this one
def _get_coingecko_id_map():
    """
    Builds a CoinGecko symbol -> ID map, prioritizing preferred overrides
    and validating IDs against the CoinGecko list.
    Returns the map { "SYMBOL" : "coin_id" } or None if fetching/processing fails.
    """
    global _coingecko_id_map_cache

    if _coingecko_id_map_cache is not None:
        print("  Using cached CoinGecko ID map.")
        return _coingecko_id_map_cache

    print("  Fetching CoinGecko list for ID validation...")
    url = "https://api.coingecko.com/api/v3/coins/list"
    try:
        coingecko_key = os.environ.get('COINGECKO_API_KEY', '')
        headers = {}
        if coingecko_key: headers["x-cg-api-key"] = coingecko_key

        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        coins_list = response.json()

        # Build a set of all valid CoinGecko IDs from the list for quick checking
        valid_coingecko_ids = {coin.get('id') for coin in coins_list if coin.get('id')}
        # Build a map from official symbol (uppercase) to ID for secondary lookups
        official_symbol_to_id = {coin.get('symbol', '').upper(): coin.get('id') for coin in coins_list if coin.get('symbol') and coin.get('id')}


        # Define the primary mapping from YOUR asset symbols to preferred CoinGecko IDs
        # This is the source of truth for which CoinGecko ID corresponds to YOUR symbol
        # ADDED 'BTC-USD' mapping here:
        primary_symbol_to_coingecko_id = {
            'AAPL': None, # Not crypto, but included for completeness if this map was used for all types
            'MSFT': None, # Not crypto
            'BTC': 'bitcoin',
            'BTC-USD': 'bitcoin', # <--- Map BTC-USD directly to 'bitcoin'
            'ETH': 'ethereum',
            'ETH-USD': 'ethereum', # Add common USD pairs if needed
            'XRP': 'ripple',
            # ... add all YOUR asset symbols (uppercase) and their desired CoinGecko IDs here ...
        }

        refined_symbol_to_id = {}

        # Build the final map by taking primary mappings and validating the target ID
        for symbol, target_coingecko_id in primary_symbol_to_coingecko_id.items():
             if target_coingecko_id is None:
                  # This symbol is not a crypto that needs CoinGecko mapping
                  continue

             if target_coingecko_id in valid_coingecko_ids:
                 # The target ID from our primary map is a valid CoinGecko ID
                 refined_symbol_to_id[symbol] = target_coingecko_id
                 # print(f"Debug: Added mapping '{symbol}': '{target_coingecko_id}' (Validated)") # Optional debug
             else:
                 # This indicates an issue with our primary_symbol_to_coingecko_id map
                 # The ID we thought was valid isn't in the latest CoinGecko list
                 print(f"Error: Target CoinGecko ID '{target_coingecko_id}' for symbol '{symbol}' not found in CoinGecko /coins/list. Cannot map.")


        # Optional: Add mappings from the CoinGecko list for symbols NOT in our primary map
        # This catches other cryptos you might add that weren't explicitly listed above
        # This might pick less common IDs if a symbol has multiple listings
        for official_symbol, official_id in official_symbol_to_id.items():
             if official_symbol not in refined_symbol_to_id: # Only add if not already mapped
                  # Add the official symbol -> official ID mapping
                  refined_symbol_to_id[official_symbol] = official_id
                  # print(f"Debug: Added official mapping '{official_symbol}': '{official_id}'") # Optional debug


        _coingecko_id_map_cache = refined_symbol_to_id

        print(f"  Successfully built refined CoinGecko ID map with {len(refined_symbol_to_id)} entries.")
        return refined_symbol_to_id

    except requests.exceptions.RequestException as req_err:
        print(f"--- Error fetching CoinGecko /coins/list API: {req_err} ---")
        return None

    except Exception as e:
        print(f"--- Error processing CoinGecko /coins/list data: {e} ---")
        return None


def fetch_coingecko_simple_price(coin_id: str, vs_currency: str = "usd") -> float | None:
    """
    Fetch just the current price for a given CoinGecko ID via /simple/price.
    Returns a float if successful, or None otherwise.
    """
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": coin_id,
        "vs_currencies": vs_currency
    }
    headers = {}
    if COINGECKO_API_KEY:
        headers["X-Cg-Pro-Api-Key"] = COINGECKO_API_KEY

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        price = data.get(coin_id, {}).get(vs_currency)
        return float(price) if price is not None else None

    except Exception as e:
        print(f"  CoinGecko simple-price fetch error for {coin_id}: {e}")
        return None

# --- Helper functions for fetching data ---
def map_alpha_vantage_type(av_type):
    if not av_type:
        return 'Unknown'
    av_type_lower = av_type.lower()
    if av_type_lower in ['equity', 'stock', 'common stock', 'preferred stock']:
        return 'stock'
    elif av_type_lower == 'etf':
        return 'etf'
    elif av_type_lower in ['fund', 'mutual fund']:
        return 'fund'
    elif av_type_lower == 'cryptocurrency':
        return 'crypto'
    elif av_type_lower == 'index':
        return 'index'
    return 'Unknown'

# Similarly in map_yfinance_type function
def map_yfinance_type(yf_type):
    if not yf_type: return 'Unknown'
    yf_type_lower = yf_type.lower()
    if yf_type_lower in ['equity', 'stock', 'mutualfund']:
         return 'stock' # Map these to 'stock'
    elif yf_type_lower == 'etf':
         return 'etf' # Map ETF to 'etf'
    elif yf_type_lower == 'index':
         return 'stock' # Or 'index' if you have a dedicated type - yfinance might label indices differently

    return 'Unknown'


# Add known type mappings for manual overrides (ensure these lists are comprehensive)
KNOWN_CRYPTO_SYMBOLS = ["BTC", "ETH", "BTC-USD", "XRP", "ADA", "DOGE", "DOT", "UNI"] # Example list
KNOWN_BOND_SYMBOLS = ["DGS10", "US10Y", "DGS5", "US5Y", "DGS30", "US30Y", "IEF", "TLT"] # Example list

# --- New helper function to fetch Company Overview from Alpha Vantage ---
def fetch_alpha_vantage_overview(symbol, api_key):
    """
    Fetches company overview data from Alpha Vantage, including sector and industry.
    Returns a dictionary of details or None on failure.
    """
    if not api_key:
        # print("Alpha Vantage API key not set for overview.") # Avoid spamming logs
        return None

    print(f"  Trying Alpha Vantage OVERVIEW for full details for {symbol}...")
    url = f"https://www.alphavantage.co/query?function=OVERVIEW&symbol={symbol}&apikey={api_key}"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status() # Raise HTTPError for bad responses (like 429)
        data = response.json()

        if "Error Message" in data:
            print(f"  Alpha Vantage API Error Message for {symbol} (OVERVIEW): {data['Error Message']}")
            return None
        if "Note" in data and "API call frequency" in data["Note"]:
            print(f"  Alpha Vantage API Limit reached Note for {symbol} (OVERVIEW): {data['Note']}")
            # Implement a delay or retry logic here if hitting rate limits
            # time.sleep(16)
            return None

        # Extract relevant details from the overview response
        # Check if the response is empty or indicates no data found for the symbol
        if not data or (isinstance(data, dict) and not data.keys()):
             print(f"  Alpha Vantage OVERVIEW returned no data for {symbol}. Data: {data}")
             return None # Return None if no data

        overview_details = {
            'symbol': data.get('Symbol', symbol),
            'name': data.get('Name', symbol),
            'type': data.get('AssetType'), # Use 'AssetType' from AV overview
            'sector': data.get('Sector'),
            'industry': data.get('Industry'),
            'exchange': data.get('Exchange'),
            'currency': data.get('Currency'),
            'country': data.get('Country'),
            'market_cap': data.get('MarketCapitalization'), # Add Market Cap
            # Add other fields from OVERVIEW response if needed
        }
        print(f"  Successfully fetched Alpha Vantage OVERVIEW for {symbol}. Sector: {overview_details.get('sector')}")
        return overview_details

    except requests.exceptions.RequestException as req_err:
        print(f"  Alpha Vantage API Request error during OVERVIEW fetch for {symbol}: {req_err}")
        if isinstance(req_err, requests.exceptions.HTTPError) and req_err.response.status_code == 429:
             print("  Alpha Vantage OVERVIEW rate limit hit. Consider waiting or using a premium key.")
        return None

    except Exception as e:
        print(f"  Alpha Vantage OVERVIEW general error for {symbol}: {e}")
        # traceback.print_exc() # Optional: print traceback for debug
        return None

# --- Modified fetch_and_map_asset_details function to prioritize Alpha Vantage OVERVIEW ---
def fetch_and_map_asset_details(symbol):
    """
    Fetches comprehensive asset details (type, name, sector, financials) from multiple sources.
    Prioritizes Alpha Vantage OVERVIEW, then yfinance.info, then Alpha Vantage SYMBOL_SEARCH, then manual overrides.
    """
    details = {
        'symbol': symbol.strip().upper(), # Normalize symbol early
        'type': 'Unknown',
        'name': symbol.strip().upper(), # Default name
        'sector': None, # Initialize sector
        'industry': None, # Initialize industry
        'expense_ratio': None,
        'yield': None,
        'pe': None,
        'exchange': None,
        'currency': None,
        'country': None,
        'market_cap': None,
        # Add other fields as needed
    }
    print(f"--- Fetching and Mapping Details for {details['symbol']} ---")

    av_api_key = os.environ.get('ALPHA_VANTAGE_API_KEY')

    # --- 1. Try Alpha Vantage OVERVIEW first ---
    if av_api_key:
        overview_data = fetch_alpha_vantage_overview(details['symbol'], av_api_key)
        if overview_data:
            print(f"  Alpha Vantage OVERVIEW successful for {details['symbol']}. Populating details.")
            details['symbol'] = overview_data.get('symbol', details['symbol']) # Use fetched symbol
            details['name'] = overview_data.get('name', details['name'])
            details['type'] = map_alpha_vantage_type(overview_data.get('type')) # Map type
            details['sector'] = overview_data.get('sector')
            details['industry'] = overview_data.get('industry')
            details['exchange'] = overview_data.get('exchange')
            details['currency'] = overview_data.get('currency')
            details['country'] = overview_data.get('country')
            details['market_cap'] = overview_data.get('market_cap')

            # Alpha Vantage OVERVIEW is comprehensive, return if successful
            print(f"--- Returning details from Alpha Vantage OVERVIEW for {details['symbol']}. Type: {details['type']}, Sector: {details['sector']} ---")
            return details

        else:
             print(f"  Alpha Vantage OVERVIEW failed or returned no data for {details['symbol']}. Trying yfinance.")


    # --- 2. Fallback to yfinance.info ---
    try:
        print(f"  Trying yfinance.info for full details for {details['symbol']}...")
        stock = yf.Ticker(details['symbol'])
        info = stock.info
        if info:
            print(f"  Successfully fetched yfinance.info for {details['symbol']}. Populating details.")
            # Overwrite details from yfinance
            details['symbol'] = info.get('symbol', details['symbol']) # Use yfinance symbol
            details['name'] = info.get('shortName') or info.get('longName') or details['symbol']
            details['type'] = map_yfinance_type(info.get('quoteType')) # Map yfinance type
            details['sector'] = info.get('sector') # Get sector from yfinance
            # yfinance.info might not have industry directly, but often has sector
            # details['industry'] = info.get('industry') # Uncomment if yfinance provides industry
            details['exchange'] = info.get('exchange')
            details['currency'] = info.get('currency')
            details['country'] = info.get('country') # yfinance often has country
            details['market_cap'] = info.get('marketCap') # yfinance has marketCap

            # Get financial metrics (safely) - yfinance is a good source for these
            details['expense_ratio'] = info.get('expenseRatio')
            details['yield'] = info.get('yield') or info.get('dividendYield')
            details['pe'] = info.get('regularMarketPE') or info.get('trailingPE')

            # If yfinance provided a mapped type, a name different from symbol, or a sector, use these details
            if details['type'] != 'Unknown' or details['name'] != details['symbol'] or details['sector'] is not None:
                print(f"--- Returning details from yfinance.info for {details['symbol']}. Type: {details['type']}, Sector: {details['sector']} ---")
                return details

            else:
                 print(f"  yfinance.info returned empty or insufficient info for {details['symbol']}. Continuing to fallback.")

        else:
             print(f"  yfinance.info returned empty info for {details['symbol']}. Continuing to fallback.")


    except Exception as e:
        print(f"Warning: Could not fetch details for {details['symbol']} from yfinance.info: {e}. Trying fallback.")
        # Continue to fallback


    # --- 3. Fallback to Alpha Vantage SYMBOL_SEARCH for Type and Name (if AV key available) ---
    # This endpoint is less comprehensive but can confirm basic symbol/name/type
    if av_api_key:
        print(f"  Trying Alpha Vantage SYMBOL_SEARCH for details for {details['symbol']}...")
        search_url = f"https://www.alphavantage.co/query?function=SYMBOL_SEARCH&keywords={details['symbol']}&apikey={av_api_key}"
        try:
            search_response = requests.get(search_url, timeout=10)
            search_response.raise_for_status()
            search_data = search_response.json()

            if 'bestMatches' in search_data and search_data['bestMatches']:
                best_match = None
                # Find the most relevant match (exact symbol, relevant type)
                for match in search_data['bestMatches']:
                    # Prioritize matches that map to a known type and have the exact symbol
                    if match.get('1. symbol', '').upper() == details['symbol'].upper() and map_alpha_vantage_type(match.get('3. type')) != 'Unknown':
                        best_match = match
                        break
                # If no exact match of a known type, take the first best match if available
                if best_match is None and search_data['bestMatches']:
                    best_match = search_data['bestMatches'][0]

                if best_match:
                    print(f"  Found details for {details['symbol']} via Alpha Vantage search. Populating details.")
                    # Update details from Alpha Vantage search result - sector is NOT available here
                    details['symbol'] = best_match.get('1. symbol', details['symbol']).upper() # Use AV symbol if available
                    details['name'] = best_match.get('2. name') or details['symbol'] # Get name, default to symbol
                    details['type'] = map_alpha_vantage_type(best_match.get('3. type')) # Map AV type
                    details['exchange'] = best_match.get('4. region') # SYMBOL_SEARCH has region, not exchange code directly
                    details['currency'] = best_match.get('8. currency') # SYMBOL_SEARCH has currency

                    # SYMBOL_SEARCH doesn't provide financial metrics or sector directly, they remain None/default

                    print(f"--- Returning details from Alpha Vantage SYMBOL_SEARCH for {details['symbol']}. Determined type: {details['type']}, Sector: {details['sector']} ---")
                    return details


            else:
                print(f"  Alpha Vantage search found no matches for {details['symbol']}. Continuing to fallback.")

        except requests.exceptions.RequestException as req_err:
            print(f"  Alpha Vantage API Request error during SYMBOL_SEARCH details fetch for {details['symbol']}: {req_err}")
            if isinstance(req_err, requests.exceptions.HTTPError) and req_err.response.status_code == 429:
                 print("  Alpha Vantage SYMBOL_SEARCH rate limit hit during details fetch.")
            # Continue to final fallback


    # --- 4. Final fallback: Manual overrides and default details ---
    print(f"--- Could not fetch details for {details['symbol']} from external APIs. Applying manual overrides/defaults. ---")

    # Apply manual overrides if the symbol is in known lists
    if details['symbol'] in KNOWN_CRYPTO_SYMBOLS: details['type'] = 'crypto'
    # Need to add manual sector overrides here if you have specific symbols not covered by APIs
    # Example:
    # if details['symbol'] == 'AGG': details['sector'] = 'Fixed Income'
    # elif details['symbol'] == 'TLT': details['sector'] = 'Fixed Income'


    # Ensure type is one of the expected internal values before saving (if it's still Unknown)
    if details['type'] == 'Unknown' or details['type'] not in ["stock", "etf", "crypto", "bond", "fund", "index"]: # Added 'fund', 'index' based on map_av_type
         print(f"Warning: Final determined asset type '{details['type']}' for {details['symbol']}' is not one of the expected types. Applying manual type mapping or defaulting.")
         # Try to map known symbols to type and sector here if type is still unknown
         if details['symbol'] in KNOWN_BOND_SYMBOLS:
              details['type'] = 'bond'
              # Add specific sector for bond types if you classify them by sector
              # details['sector'] = 'Fixed Income' # Example manual sector for bonds
         elif details['symbol'] in KNOWN_CRYPTO_SYMBOLS:
              details['type'] = 'crypto'
              # Crypto might not have a traditional sector
         else:
              # Default to 'stock' or 'Unknown' if manual mapping doesn't apply
              details['type'] = 'stock' # Default type if still Unknown after checks

    # Ensure a default name is set if still the symbol itself and no name was found
    if details['name'] == details['symbol']:
        # Could try other name sources here if available, or just use a better default
        details['name'] = f"{details['symbol']}" # Keep the symbol as name if no other name found


    print(f"--- Returning final determined details for {details['symbol']}. Type: {details['type']}, Name: {details['name']}, Sector: {details['sector']} ---")
    return details

# Modified function signature and logic for date range fetching
def fetch_yahoo_data(symbol, start_date=None, end_date=None, period=None, interval="1d"):
    """
    Fetch data from Yahoo Finance for a specific date range or latest price.
    Prioritizes start/end dates if provided.

    Args:
        symbol: Stock/ETF symbol
        start_date: Start date for data (YYYY-MM-DD string). Required for historical fetching.
        end_date: End date for data (YYYY-MM-DD string). Required for historical fetching.
        period: Fallback period (e.g., "1y") if dates not provided. Only used if start/end are None.
        interval: Data interval (e.g., "1d")

    Returns:
        DataFrame with historical price data ('date', 'price') or a scalar price for latest ('current' period).
        Returns None on failure or if no data is found.
    """
    try:
        symbol = symbol.strip().upper()
        print(f"--- Fetching Yahoo Data for {symbol} ---")
        print(f"  Date Range: {start_date} to {end_date}, Period: {period}, Interval: {interval}")

        # Use yfinance to get data
        # import yfinance as yf # Import yfinance here if not already at the top
        ticker = yf.Ticker(symbol)

        # Handle fetching just the current price (using period='current')
        if period == "current":
            try:
                info = ticker.info
                if info and info.get('regularMarketPrice') is not None:
                    price = info['regularMarketPrice']
                    print(f"  [Fetched Info Price] {symbol}: ${price:.2f}")
                    return price # Return the scalar price
                elif info and info.get('currentPrice') is not None: # Another possible key
                     price = info['currentPrice']
                     print(f"  [Fetched Info Price] {symbol}: ${price:.2f} (currentPrice)")
                     return price

                hist_latest = ticker.history(period="1d", interval="1m", prepost=True)
                if not hist_latest.empty:
                    latest_price = hist_latest['Close'].iloc[-1]
                    print(f"  [Fetched] {symbol}: ${latest_price:.2f} (from Yahoo Finance 1m history)")
                    return latest_price # Return the scalar price
                else:
                    print(f"  Yahoo 'current' failed for {symbol}. No price found in info or history.")
                    return None # Return None if no recent price found
            except Exception as latest_e:
                 print(f"  Error fetching Yahoo 'current' price for {symbol} from Yahoo Finance info/history: {latest_e}")
                 return None


        # Handle fetching historical data using start and end dates (prioritized)
        print(f"  Fetching historical data from Yahoo Finance for {symbol}...")

        # Use start and end dates if provided, otherwise fallback to period
        if start_date and end_date:
            print(f"  Using start={start_date}, end={end_date}")
            hist = ticker.history(start=start_date, end=end_date, interval=interval,
                                 actions=True, prepost=True)
        elif period:
             print(f"  Using period={period}, interval={interval} (dates not provided)")
             hist = ticker.history(period=period, interval=interval,
                                 actions=True, prepost=True)
        else:
             print(f"  No start/end dates or period provided for historical fetch for {symbol}. Skipping.")
             return None


        if hist.empty:
            print(f"  No historical data found for {symbol} from Yahoo Finance for the specified range/period.")
            return None

        print(f"  Successfully fetched {len(hist)} data points for {symbol} from Yahoo Finance.")
        print(f"  First date: {hist.index.min()}, Last date: {hist.index.max()}")

        # Ensure index is datetime
        hist.index = pd.to_datetime(hist.index)

        # Return the DataFrame with the 'Close' column
        if 'Close' in hist.columns:
             # Rename index to 'date' for consistency with MarketData model
             hist = hist.rename_axis('date')
             # Return DataFrame subset with 'price' column
             return hist[['Close']].rename(columns={'Close': 'price'})
        else:
             print(f"  Warning: 'Close' column not found in Yahoo data for {symbol}. Columns: {hist.columns.tolist()}")
             return None


    except Exception as e:
        print(f"--- Error in fetch_yahoo_data for {symbol}: {e} ---")
        # traceback.print_exc() # Uncomment for detailed error during development
        return None

# Modified function signature and logic for date range fetching
def fetch_alpha_vantage_data(symbol, function, start_date=None, end_date=None):
    """
    Fetch data from Alpha Vantage for a specific function. Filters by date range if provided for time series.
    
    Args:
        symbol: Stock/ETF symbol
        function: Alpha Vantage API function (TIME_SERIES_DAILY, GLOBAL_QUOTE, etc.)
        start_date: Start date for data (YYYY-MM-DD string) - used for filtering time series
        end_date: End date for data (YYYY-MM-DD string) - used for filtering time series
        
    Returns:
        DataFrame with historical price data ('date', 'price') for time series, or a scalar price for GLOBAL_QUOTE.
        Returns None on failure or if no data is found.
    """
    if not ALPHA_VANTAGE_API_KEY:
         # print("Alpha Vantage API key not set.") # Avoid spamming logs if this is a fallback
         return None

    print(f"--- Fetching Alpha Vantage Data for {symbol} ---")
    print(f"  Function: {function}, Filter Dates: {start_date} to {end_date}")

    try:
        # --- Handle GLOBAL_QUOTE (single price) ---
        if function == "GLOBAL_QUOTE":
            url = f"https://www.alphavantage.co/query?function={function}&symbol={symbol}&apikey={ALPHA_VANTAGE_API_KEY}"
            print(f"  Requesting URL: {url}")
            response = requests.get(url, timeout=20)
            response.raise_for_status() # Raise HTTPError for bad responses (like 429)
            data = response.json()

            if "Error Message" in data:
                 print(f"--- Alpha Vantage API Error Message for {symbol} ({function}): {data['Error Message']} ---")
                 return None
            if "Note" in data and "API call frequency" in data["Note"]:
                 print(f"--- Alpha Vantage API Limit reached Note for {symbol} ({function}): {data['Note']} ---")
                 # time.sleep(16)
                 return None

            quote_data = data.get("Global Quote", {})
            price = quote_data.get("05. price")
            print(f"  Global Quote Price ('05. price'): {price}")
            if price is not None:
                 try:
                      return float(price)
                 except ValueError:
                      print(f"  Could not convert Alpha Vantage price '{price}' to float for {symbol}.")
                      return None
            else:
                 print(f"  Price '05. price' not found or None in AV Global Quote for {symbol}. Data: {data}")
                 return None

        # --- Handle Time Series Functions ---
        time_series_key = None
        if function == "TIME_SERIES_DAILY":
            time_series_key = "Time Series (Daily)"
        elif function == "TIME_SERIES_WEEKLY":
            time_series_key = "Weekly Time Series"
        elif function == "TIME_SERIES_MONTHLY":
            time_series_key = "Monthly Time Series"
        # Add other time series functions if needed

        if not time_series_key:
            print(f"  Unknown Alpha Vantage time series function: {function}")
            return None

        # For historical time series, request full output size
        url = f"https://www.alphavantage.co/query?function={function}&symbol={symbol}&apikey={ALPHA_VANTAGE_API_KEY}&outputsize=full"
        print(f"  Requesting URL: {url}")

        response = requests.get(url, timeout=20)
        response.raise_for_status()
        data = response.json()

        if "Error Message" in data:
             print(f"--- Alpha Vantage API Error Message for {symbol} ({function}): {data['Error Message']} ---")
             return None
        if "Note" in data and "API call frequency" in data["Note"]:
             print(f"--- Alpha Vantage API Limit reached Note for {symbol} ({function}): {data['Note']} ---")
             # time.sleep(16)
             return None


        time_series_data = data.get(time_series_key, {})

        if not time_series_data:
            print(f"  No time series data available from Alpha Vantage for {symbol} ({function}).")
            return None

        # Convert to DataFrame
        df = pd.DataFrame(time_series_data).T
        df.index.name = 'date' # Name the index column 'date'
        # Convert index to datetime
        df.index = pd.to_datetime(df.index)
        # Convert string values to float
        for col in df.columns:
            try:
                df[col] = df[col].astype(float)
            except ValueError:
                 pass # Ignore columns that can't be float


        # Rename 'close' column to 'price'
        close_cols = [c for c in df.columns if c.lower().endswith("close")]
        if close_cols:
            df = df.rename(columns={close_cols[0]: 'price'})[['price']]
        else:
            print("No close column found:", df.columns.tolist())
            return None

        # --- Filter DataFrame by start_date and end_date ---
        if start_date or end_date:
             print(f"  Filtering Alpha Vantage data by date range: {start_date} to {end_date}")
             # Convert date strings to datetime objects for filtering
             start_dt = pd.to_datetime(start_date) if start_date else df.index.min()
             end_dt = pd.to_datetime(end_date) if end_date else df.index.max()

             # Apply filter (inclusive of start and end dates)
             df_filtered = df[(df.index >= start_dt) & (df.index <= end_dt)].copy() # Use .copy() to avoid SettingWithCopyWarning
             print(f"  Filtered down to {len(df_filtered)} data points.")
             df = df_filtered

        if df.empty:
             print(f"  No data points remaining after date filtering for {symbol}.")
             return None

        # Sort by date just in case
        df = df.sort_index()

        print(f"  Successfully parsed {len(df)} filtered data points from Alpha Vantage for {symbol} ({function}).")
        print(f"  Returning DataFrame for {symbol} with shape {df.shape}")

        return df[['price']] # Return DataFrame with date (index) and price column


    except requests.exceptions.RequestException as req_err:
         print(f"--- Alpha Vantage API Request error for {symbol} ({function}): {req_err} ---")
         # traceback.print_exc()
         if isinstance(req_err, requests.exceptions.HTTPError) and req_err.response.status_code == 429:
              print("  Alpha Vantage rate limit exceeded. Consider waiting or using a premium key.")
         return None

    except Exception as e:
        print(f"--- Alpha Vantage general error for {symbol} ({function}): {e} ---")
        # traceback.print_exc()
        return None

# Modified function signature and logic for date range filtering
def fetch_alpha_vantage_bond_yield(maturity="10year", start_date=None, end_date=None):
    """
    Fetch Treasury yield data from Alpha Vantage for a maturity. Filters by date range if provided.
    ... (docstring) ...
    """
    if not ALPHA_VANTAGE_API_KEY:
         # print("Alpha Vantage API key not set for bond yield.")
         return None
         
    print(f"--- Fetching Alpha Vantage Bond Yield for {maturity} ---")
    print(f"  Filter Dates: {start_date} to {end_date}")

    try:
        # The API URL doesn't support date range filtering directly
        url = (
            f"https://www.alphavantage.co/query?"
            f"function=TREASURY_YIELD&interval=daily&maturity={maturity}&apikey={ALPHA_VANTAGE_API_KEY}"
        )
        print(f"  Requesting URL: {url}")
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        yields_data = data.get("data", [])

        if not yields_data:
            print(f"  No bond yield data available from Alpha Vantage for maturity {maturity}. Data: {data}")
            return None

        # Convert to DataFrame consistent with others
        df = pd.DataFrame(yields_data)
        df['date'] = pd.to_datetime(df['date'])
        df['value'] = pd.to_numeric(df['value'], errors='coerce') # Handle 'NaN' strings or other non-numeric
        df = df.dropna(subset=['date', 'value']) # Drop rows where value couldn't be converted
        df = df.rename(columns={'value': 'price'}) # Rename for consistency
        df = df.sort_values('date')
        df = df.set_index('date') # Set date as index for consistency


        # --- Filter DataFrame by start_date and end_date ---
        if start_date or end_date:
             print(f"  Filtering Alpha Vantage Bond Yield data by date range: {start_date} to {end_date}")
             start_dt = pd.to_datetime(start_date) if start_date else df.index.min()
             end_dt = pd.to_datetime(end_date) if end_date else df.index.max()

             df_filtered = df[(df.index >= start_dt) & (df.index <= end_dt)].copy() # Use .copy() to avoid SettingWithCopyWarning
             print(f"  Filtered down to {len(df_filtered)} data points.")
             df = df_filtered


        if df.empty:
             print(f"  No bond yield data points remaining after date filtering for {maturity}.")
             return None

        print(f"  Successfully parsed {len(df)} filtered data points for maturity {maturity}.")
        print(f"  Returning DataFrame for {maturity} with shape {df.shape}")

        return df[['price']] # Return DataFrame with date (index) and price column


    except requests.exceptions.RequestException as req_err:
        print(f"--- Alpha Vantage API Request error for bond yield {maturity}: {req_err} ---")
        if isinstance(req_err, requests.exceptions.HTTPError) and req_err.response.status_code == 429:
             print("  Alpha Vantage bond yield rate limit exceeded.")
        return None
    except Exception as e:
        print(f"--- Bond yield fetch error for {maturity}: {e} ---")
        # traceback.print_exc()
        return None

# Function signature already accepts start_date and end_date
def fetch_fred_data(series_id, start_date=None, end_date=None):
    """
    Fetch economic data from FRED (Federal Reserve Economic Data) for a specific date range.
    ... (docstring) ...
    """
    if not FRED_API_KEY:
         # print("FRED API key not set.")
         return None

    print(f"--- Fetching FRED Data for {series_id} ---")
    print(f"  Date Range: {start_date} to {end_date}")

    try:
        # FRED API URL supports start_date and end_date directly
        url = (
            f"https://api.stlouisfed.org/fred/series/observations?"
            f"series_id={series_id}&api_key={FRED_API_KEY}&file_type=json&"
            f"observation_start={start_date if start_date else ''}&observation_end={end_date if end_date else ''}" # Use provided dates or empty string if None
        )
        print(f"  Requesting URL: {url}")

        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        observations = data.get("observations", [])

        if not observations:
            print(f"  No data available from FRED for {series_id} for the specified range.")
            return None

        # Convert to DataFrame
        df = pd.DataFrame(observations)
        df["date"] = pd.to_datetime(df["date"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce") # Handle missing values like '.'
        df = df.dropna(subset=['date', 'value']) # Drop rows where value couldn't be converted
        df = df.sort_values("date")
        df = df.set_index('date') # Set date as index

        print(f"  Successfully parsed {len(df)} data points from FRED for {series_id}.")
        print(f"  Returning DataFrame for {series_id} with shape {df.shape}")

        return df.rename(columns={'value': 'price'})[['price']] # Return DataFrame with date (index) and price


    except requests.exceptions.RequestException as req_err:
         print(f"--- FRED API Request error for {series_id}: {req_err} ---")
         return None
    except Exception as e:
        print(f"--- FRED error for {series_id}: {e} ---")
        # traceback.print_exc()
        return None

# Replace your existing fetch_coingecko_data function with this one
def fetch_coingecko_data(crypto_id, vs_currency="usd", days=None, start_date=None, end_date=None, interval="daily"):
    """
    Fetch cryptocurrency data from CoinGecko for a specific date range or latest price.
    Prioritizes start/end dates if provided over 'days'.
    Includes comprehensive debugging prints for API key, headers, response data, and errors.

    Args:
        crypto_id: CoinGecko crypto ID (e.g., 'bitcoin', 'ethereum') - THIS IS CRITICAL
        vs_currency: Conversion currency (default 'usd')
        days: Fallback number of days ('1', '7', '14', '30', '90', '180', '365', 'max') if dates not provided. Use '0' for current price.
        start_date: Start date for data (YYYY-MM-DD string) - prioritizes range fetch
        end_date: End date for data (YYYY-MM-DD string) - prioritizes range fetch
        interval: Data interval ('daily' is default for >= 1 day data).
                  'hourly' for < 30 days, 'minutely' for < 2 days. Used for range fetch.
                  Ignored for date range fetch as API determines it.

    Returns:
        DataFrame with historical data ('date', 'price') for historical, or a scalar price for latest.
        Returns None on failure or if no data is found.
    """
    print(f"--- Fetching CoinGecko Data for ID: {crypto_id} ---")
    print(f"  Date Range: {start_date} to {end_date}, Days: {days}, Interval: {interval}")

    coingecko_key = os.environ.get('COINGECKO_API_KEY', '')


    headers = {}
    # Ensure the API key is added to the header if available
    if coingecko_key:
        # Note: CoinGecko's Free API uses "x-cg-pro-api-key" for paid endpoints,
        # but the documentation sometimes uses "x-cg-api-key". Check your plan docs
        # and dashboard for the correct header name if issues persist.
        # Let's stick to "x-cg-api-key" for now as it worked in curl, but be aware.
        headers["x-cg-api-key"] = coingecko_key

    try:
        # --- Handle fetching by date range (prioritized) ---
        if start_date and end_date:
            print(f"  Fetching CoinGecko data by date range: {start_date} to {end_date}")
            try:
                start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                start_ts = int(start_dt.timestamp())
                end_ts = int(end_dt.timestamp())
                url = (
                    f"https://api.coingecko.com/api/v3/coins/{crypto_id}/market_chart/range?"
                    f"vs_currency={vs_currency}&from={start_ts}&to={end_ts}"
                )
            except ValueError as ve:
                 print(f"  Error converting date strings to timestamps for {crypto_id}: {ve}")
                 return None


        # --- Handle fetching by 'days' or 'current' (fallback if range not used) ---
        elif days is not None:
            # Simplified URL construction for days/max requests
            url = (
                f"https://api.coingecko.com/api/v3/coins/{crypto_id}/market_chart?"
                f"vs_currency={vs_currency}&days={days}"
                # Adding interval param only if it's not None and makes sense for the endpoint/days value
                # if days != 'max' and interval: f"&interval={interval}" else "" # Optional: conditional interval
            )
            print(f"  Fetching CoinGecko market chart by days='{days}' for ID: {crypto_id}...")


        else:
             print("  No date range or 'days' parameter provided for CoinGecko fetch.")
             return None # No valid parameters provided

        # --- Execute the HTTP request ---
        print(f"  Requesting URL: {url}") # Print the final URL being requested
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status() # Raise HTTPError for bad responses (like 404, 429, 401)
        data = response.json()

        # Extract price data (key is 'prices' for both market_chart and market_chart/range)
        prices_data = data.get("prices", [])
        if not prices_data:
            print(f"  No price data available from CoinGecko for ID: {crypto_id} at URL: {url}. Response data keys: {data.keys()}")
            # Check for common error messages in the response body if prices is empty
            if "error" in data:
                 print(f"  CoinGecko API returned error: {data['error']}")
            return None

        # Convert to DataFrame
        # The error 'date' likely happens when df is created or processed
        df = pd.DataFrame(prices_data, columns=["timestamp", "price"])
        # Convert timestamp to datetime (timestamp is in milliseconds)
        df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
        # Drop original timestamp column and set date as index
        df = df.drop("timestamp", axis=1)
        df = df.set_index('date')
        # Ensure price column is float and drop rows with invalid prices
        df['price'] = pd.to_numeric(df['price'], errors='coerce')
        # The dropna line below might be problematic if 'date' needs to be a column for it to work correctly
        # df = df.dropna(subset=['date', 'price']) # Consider if this is causing issues with 'date' index

        # Let's ensure we only keep valid numeric prices and rely on the date index
        df = df[df['price'].notna()].copy() # Keep rows where price is not NaN, ensure copy

        # Sort by date just in case
        df = df.sort_index()

        print(f"  Successfully parsed {len(df)} data points from CoinGecko for ID: {crypto_id}.")

        # Return the DataFrame with the date index and price column
        return df[['price']]


    except requests.exceptions.RequestException as req_err:
         print(f"--- CoinGecko API Request error for ID: {crypto_id}: {req_err} ---")
         if isinstance(req_err, requests.exceptions.HTTPError):
              if req_err.response.status_code == 404:
                   print(f"  404 Error: CoinGecko ID '{crypto_id}' not found or endpoint invalid for this ID.")
              elif req_err.response.status_code == 429:
                   print("  429 Error: CoinGecko rate limit exceeded. Consider waiting or using a premium key.")
              elif req_err.response.status_code == 401:
                   print("  401 Error: Unauthorized. Check your API key and plan access for this endpoint.")
              else:
                   print(f"  HTTP Error details: {req_err.response.status_code} - {req_err.response.text}")
         else:
              # Non-HTTP Request Error (network, timeout, etc.)
              print(f"  Request error details: {req_err}")
         # traceback.print_exc() # Uncomment for detailed error during development
         return None

    except Exception as e:
        print(f"--- CoinGecko general error for ID: {crypto_id}: {e} ---")
        # traceback.print_exc() # Uncomment for detailed error during development
        return None

def store_market_data(asset, price=None, prices_df=None):
    """
    Store market data in database. Requires an active application context.

    Args:
        asset: Asset object
        price: Latest price (float, for single price update)
        prices_df: DataFrame with historical prices (for bulk update), must have 'date' (datetime) and 'price' (float) columns.
    """
    # This function NEEDS an application context
    try:
        from flask import current_app
        try: current_app.name # Check context
        except RuntimeError:
            print(f"Error: Attempted to use db.session outside application context for asset {asset.symbol}. Cannot store data.")
            return
    except Exception as e:
         print(f"Error during context check import/access: {e}")
         return


    try: # Wraps storage logic
        if price is not None:
            # Store single price point - Ensure price is float/int and not None/NaN/Inf
            # Replace pd.api.types.is_finite(price) with np.isfinite(price)
            if isinstance(price, (int, float)) and not pd.isna(price) and np.isfinite(price): # <-- MODIFIED LINE
                 # Check if a price for today (UTC date) already exists for this asset
                 today_utc_date = datetime.now(UTC).date()
                 # Query within the active session/context
                 existing_entry = MarketData.query.filter(
                     MarketData.asset_id == asset.id,
                     db.func.date(MarketData.date) == today_utc_date # Compare date parts
                 ).first()

                 if existing_entry:
                     print(f"[DB] Updating today's price for {asset.symbol} from ${existing_entry.price:.2f} to ${price:.2f}")
                     existing_entry.price = price
                     existing_entry.date = datetime.now(UTC)
                 else:
                     print(f"[DB] Saving new price for {asset.symbol}: ${price:.2f}")
                     entry = MarketData(asset_id=asset.id, price=price, date=datetime.now(UTC))
                     db.session.add(entry)

                 # Defer commit to fetch_market_data
                 pass

            else:
                 print(f"[DB Skipped] {asset.symbol}: Invalid single price value: {price}")


        elif prices_df is not None and isinstance(prices_df, pd.DataFrame) and not prices_df.empty:
            # Store historical price data (DataFrame) - This section also needs to use np.isfinite if it uses pd.api.types.is_finite
            # Looking at your previous code for this part, it *does* use pd.api.types.is_finite here as well.
            # So, update this line in your code too:
            # df_to_store = df_to_store[pd.api.types.is_finite(df_to_store['price'])].copy() # <-- Also change this line to np.isfinite

            # Ensure DataFrame has 'date' (index or column) and 'price' columns and they are the correct types
            if 'price' in prices_df.columns and (prices_df.index.name == 'date' and pd.api.types.is_datetime64_any_dtype(prices_df.index)) or ('date' in prices_df.columns and pd.api.types.is_datetime64_any_dtype(prices_df['date'])):
                 # Case 1: 'date' is index, 'price' is column OR Case 2: 'date' and 'price' are columns
                 if prices_df.index.name == 'date':
                     df_to_store = prices_df.reset_index()[['date', 'price']]
                 else:
                     df_to_store = prices_df[['date', 'price']].copy()

                 # Ensure price column is numeric before checking for finite values
                 df_to_store['price'] = pd.to_numeric(df_to_store['price'], errors='coerce')

                 # Filter out rows with invalid price values (None, NaN, Inf)
                 # Replace pd.api.types.is_finite(df_to_store['price']) with np.isfinite(df_to_store['price'])
                 df_to_store = df_to_store[np.isfinite(df_to_store['price'])].copy() # <-- MODIFIED LINE


            else:
                print(f"[DB Error] DataFrame for {asset.symbol} has incorrect structure or column types for storage.")
                return

            # ... (rest of historical data storage logic - check for existing dates, bulk save, etc.) ...
            if df_to_store.empty:
                print(f"[DB Skipped] {asset.symbol}: No valid historical price data points found after filtering.")
                return

            entries_to_add = []
            existing_dates_utc = {md.date.replace(tzinfo=None) for md in MarketData.query.filter_by(asset_id=asset.id).all()}

            for index, row in df_to_store.iterrows():
                 entry_date_utc = row['date'].replace(tzinfo=None)
                 if entry_date_utc not in existing_dates_utc:
                      entries_to_add.append(MarketData(
                          asset_id=asset.id,
                          price=float(row['price']),
                          date=entry_date_utc
                      ))

            if entries_to_add:
                 print(f"[DB] Saving {len(entries_to_add)} new historical data points for {asset.symbol}...")
                 try:
                     db.session.bulk_save_objects(entries_to_add)
                     print(f"[DB] {len(entries_to_add)} historical data points added to session for {asset.symbol}.")
                 except Exception as bulk_save_err:
                     db.session.rollback()
                     print(f"Database bulk save error for {asset.symbol}: {bulk_save_err}")

            else:
                 print(f"[DB Skipped] {asset.symbol}: No new historical data points to save.")


        elif prices_df is not None: # It was a DataFrame but empty
             print(f"[DB Skipped] {asset.symbol}: Received an empty DataFrame for historical data storage.")
             pass


    except Exception as e: # Catches storage errors for THIS asset
        db.session.rollback()
        print(f"Database error storing data for {asset.symbol}: {e}")
        import traceback
        print(traceback.format_exc()) # Print traceback for debug


def fetch_market_data(historical=False):
    """
    Fetch market data for all assets in database. Requires an active application context.
    When historical=True, limits the fetch to approximately the last year of data.

    Args:
        historical: Whether to fetch historical data (last year) or just latest prices (current).
                    Does NOT use purchase dates when called directly by scheduler.
    """
    # This function MUST be called within an application context
    try:
        from flask import current_app
        current_app.name # Check if context is active
    except RuntimeError:
        print("Error: Attempted to run fetch_market_data outside application context.")
        return # Cannot proceed without context

    print(f"\n[Fetching market data - historical={historical}]")
    # Query assets within the application context
    # Ensure we query for assets that belong to *any* user
    all_assets = Asset.query.all() # Get all asset objects first

    if not all_assets:
        print("No assets found in the database to fetch data for.")
        return # Exit if no assets

    # --- Normalize and Deduplicate Tickers ---
    # Create a set of unique, uppercase symbols
    unique_symbols = sorted(list({asset.symbol.upper() for asset in all_assets}))

    if not unique_symbols:
        print("No unique ticker symbols found in the database assets after normalization.")
        return # Exit if no unique symbols

    print(f"Found {len(all_assets)} assets, processing {len(unique_symbols)} unique symbols.")

    # Create a mapping from normalized symbol back to the original Asset object (or one of them if duplicates exist)
    # This assumes one Asset object per unique symbol is sufficient for fetching
    asset_map = {asset.symbol.upper(): asset for asset in all_assets}

    # --- Loop through unique symbols instead of all_assets ---
    for i, symbol in enumerate(unique_symbols):
        # Get the original Asset object associated with this unique symbol
        
        asset = asset_map.get(symbol)
        if not asset:
            print(f"Error: Could not find asset object for normalized symbol {symbol}. Skipping.")
            continue

        asset_type = asset.asset_type.lower() if asset.asset_type else "unknown"
        if asset_type == "unknown":
            print(f"Warning: asset type is Unknown for {asset.symbol}. Assuming 'stock' as fallback.")
            asset_type = "stock"

        if not asset:
            # This should ideally not happen if asset_map is built correctly from all_assets
            print(f"Error: Could not find asset object for normalized symbol {symbol}. Skipping.")
            continue # Skip this symbol if asset object not found

        # Use the asset object for logging and type checking
        print(f"Processing symbol {i+1}/{len(unique_symbols)}: {asset.symbol} (Type: {asset.asset_type})")

        try:
            # Add a delay between API calls to respect rate limits
            sleep_time = 10 if historical else 5 # Default delay

            if i > 0: # Don't delay before the first symbol
                 print(f"  Sleeping for {sleep_time} seconds...")
                 time.sleep(sleep_time)


            price_or_df = None # Variable for historical data (DataFrame)
            price = None       # Variable for latest price (scalar)

            if historical:
                # --- Historical Fetch Logic (Limited to Last Year) ---

                # Calculate date range: Last Year up to Today (UTC)
                end_date = datetime.now(UTC)
                start_date = end_date - timedelta(days=365) # Approximately 1 year ago

                # Format dates as YYYY-MM-DD strings for API calls/filtering
                start_date_str = start_date.strftime('%Y-%m-%d')
                end_date_str = end_date.strftime('%Y-%m-%d')

                print(f"  Fetching historical data for range: {start_date_str} to {end_date_str}")

                if asset.asset_type and asset_type in ["stock", "etf"]:
                    # Try Yahoo Finance for the specific date range
                    print(f"  Trying Yahoo Finance for data for {asset.symbol}...")
                    # Pass calculated start and end dates INSTEAD OF period="max"
                    price_or_df = fetch_yahoo_data(asset.symbol, start_date=start_date_str, end_date=end_date_str, interval="1d", period=None)

                    # If Yahoo fails or is empty, try Alpha Vantage daily
                    if price_or_df is None or (isinstance(price_or_df, pd.DataFrame) and price_or_df.empty):
                         print(f"  Yahoo data failed for {asset.symbol} for range {start_date_str} to {end_date_str}. Trying Alpha Vantage daily.")
                         # Pass calculated start and end dates INSTEAD OF None
                         price_or_df = fetch_alpha_vantage_data(asset.symbol, function="TIME_SERIES_DAILY", start_date=start_date_str, end_date=end_date_str)


                elif asset.asset_type and asset_type == "crypto":
                    print(f"  Trying CoinGecko for historical data for {asset.symbol}...")
                    
                    # --- Get CoinGecko ID map and look up the ID ---
                    coingecko_map = _get_coingecko_id_map() # Fetches/uses cached map
                
                    if coingecko_map:
                         symbol_to_lookup = asset.symbol.upper()
                         coingecko_id = coingecko_map.get(symbol_to_lookup)
                         print(f"  Direct lookup result for symbol '{symbol_to_lookup}' in coingecko_map: {coingecko_map.get(symbol_to_lookup)}")

                         print(f"  Looking up symbol '{symbol_to_lookup}' in CoinGecko map. Found ID: {coingecko_id}")
                         
                         if coingecko_id:
                             # --- Call fetch_coingecko_data with the correct ID and date range (Last Year) ---
                             # Pass calculated start and end dates - this uses the /range endpoint
                             # Set days=None to ensure start_date/end_date is prioritized
                             price_or_df = fetch_coingecko_data(coingecko_id, start_date=start_date_str, end_date=end_date_str, days=None) # Use dates, not days="max"
                             
                             # Check if CoinGecko returned a DataFrame
                             if price_or_df is None or not isinstance(price_or_df, pd.DataFrame) or price_or_df.empty:
                                 print(f"  CoinGecko historical fetch failed or returned no data for {asset.symbol} (ID: {coingecko_id}) for range {start_date_str} to {end_date_str}.")
                                 price_or_df = None
                             else:
                                 print(f"  Successfully fetched CoinGecko historical data for {asset.symbol} (ID: {coingecko_id}) for range {start_date_str} to {end_date_str}.")
                         else:
                             print(f"  No CoinGecko ID found in map for symbol {asset.symbol}. Skipping crypto historical fetch.")
                             price_or_df = None

                    else:
                         print("  Could not get CoinGecko ID map. Skipping crypto fetch.")
                         price_or_df = None


                elif asset.asset_type and asset_type == "bond":
                    # Try FRED first for the specific date range
                    print(f"  Trying FRED for historical data for {asset.symbol}...")
                    fred_series_id = None
                    if asset.symbol.upper() == "DGS10" or asset.symbol.upper() == "US10Y":
                         fred_series_id = "DGS10"
                    elif asset.symbol.upper() == "DGS5" or asset.symbol.upper() == "US5Y":
                         fred_series_id = "DGS5"
                    elif asset.symbol.upper() == "DGS30" or asset.symbol.upper() == "US30Y":
                         fred_series_id = "DGS30"

                    if fred_series_id:
                         # Pass calculated start and end dates
                         price_or_df = fetch_fred_data(fred_series_id, start_date=start_date_str, end_date=end_date_str)


                    # Alpha Vantage fallback for bonds if FRED isn't used or fails
                    if (price_or_df is None or (isinstance(price_or_df, pd.DataFrame) and price_or_df.empty)):
                         print(f"  FRED data failed for {asset.symbol} for range {start_date_str} to {end_date_str}. Trying Alpha Vantage bond yield.")
                         maturity = None
                         if asset.symbol.upper() == "US10Y": maturity = "10year"
                         elif asset.symbol.upper() == "US5Y": maturity = "5year"
                         elif asset.symbol.upper() == "US30Y": maturity = "30year"

                         if maturity:
                               # Pass calculated start and end dates
                               price_or_df = fetch_alpha_vantage_bond_yield(maturity, start_date=start_date_str, end_date=end_date_str)
                               # No specific sleep needed here, main loop delay handles it.


                    if price_or_df is None and not fred_series_id and not maturity: # Handle unknown bond types that weren't mapped
                         print(f"Unknown bond symbol {asset.symbol} for historical fetch in fetch_market_data.")
                         price_or_df = None


                else:
                    # Handle assets with no asset_type or unknown type
                    print(f"Unknown asset type '{asset.asset_type}' for historical fetch for {asset.symbol} in fetch_market_data. Skipping.")
                    price_or_df = None # Ensure None for unknown types

                # --- Store the fetched DataFrame (if valid) ---
                if price_or_df is not None and isinstance(price_or_df, pd.DataFrame) and not price_or_df.empty:
                    print(f"  Successfully fetched historical data for {asset.symbol}. Storing...")
                    store_market_data(asset, prices_df=price_or_df)
                elif price_or_df is not None:
                    print(f"Warning: Historical fetch for {asset.symbol} returned non-DataFrame or empty after fetch attempt: {type(price_or_df)}. Not storing.")
                else:
                    print(f"Failed to get historical data for {asset.symbol} from any source in fetch_market_data after all attempts for range {start_date_str} to {end_date_str}.") # Update message

            else: # --- Latest Price Fetch Logic (historical=False) ---
                 price = None # Reset price variable for latest fetch

                 if asset.asset_type and asset_type in ["stock", "etf"]:
                     # Try Yahoo Finance for latest price
                     print(f"  Trying Yahoo Finance for latest price for {asset.symbol}...")
                     price = fetch_yahoo_data(asset.symbol, period="current", start_date=None, end_date=None)

                     if price is None or isinstance(price, pd.DataFrame): # Ensure it's a scalar price
                          print(f"  Yahoo latest price failed for {asset.symbol} or returned DataFrame. Trying Alpha Vantage GLOBAL_QUOTE.")
                          # Fallback to Alpha Vantage GLOBAL_QUOTE
                          price = fetch_alpha_vantage_data(asset.symbol, function="GLOBAL_QUOTE", start_date=None, end_date=None)
                          if price is not None:
                               print(f"Got latest price for {asset.symbol}: {price} (from Alpha Vantage GLOBAL_QUOTE)")
                          else:
                               print(f"Failed to get latest price for {asset.symbol} from Alpha Vantage GLOBAL_QUOTE.")


                 elif asset.asset_type and asset_type == "crypto":
                     print(f"  Trying CoinGecko for latest price for {asset.symbol}...")
                     # --- Get CoinGecko ID map and look up the ID ---
                     coingecko_map = _get_coingecko_id_map()

                     if coingecko_map:
                         symbol_to_lookup = asset.symbol.upper()
                         coingecko_id = coingecko_map.get(symbol_to_lookup)
                         print(f"  Direct lookup result for symbol '{symbol_to_lookup}' in coingecko_map: {coingecko_map.get(symbol_to_lookup)}")

                         print(f"  Looking up symbol '{symbol_to_lookup}' in CoinGecko map. Found ID: {coingecko_id}")

                         if coingecko_id:
                             # --- Call fetch_coingecko_data with the correct ID for latest price ---
                             # Pass days="0" for latest
                             price_df_latest = fetch_coingecko_data(coingecko_id, days="0", start_date=None, end_date=None)

                             # CoinGecko days=0 returns a DataFrame with a single row, extract scalar price
                             # Ensure price_df_latest is a DataFrame and has the 'price' column before trying to extract
                             if price_df_latest is not None and isinstance(price_df_latest, pd.DataFrame) and not price_df_latest.empty and 'price' in price_df_latest.columns:
                                price_scalar = price_df_latest['price'].iloc[-1]
                                print(f"Got latest price for crypto {asset.symbol} (ID: {coingecko_id}): {price_scalar} (from CoinGecko)")
                                price = price_scalar # Set the price variable to the scalar value for storing
                             else:
                                price = None # Ensure price is None if fetch failed or returned empty or missing data
                                print(f"Failed to get latest price for crypto {asset.symbol} (ID: {coingecko_id}) from CoinGecko.")
                         else:
                             # No CoinGecko ID found in map for this symbol
                             print(f"  No CoinGecko ID found in map for symbol {asset.symbol}. Skipping crypto latest fetch.")
                             price = None # Ensure result is None
                     else:
                         # Could not get the CoinGecko ID map itself
                         print("  Could not get CoinGecko ID map. Skipping crypto latest fetch.")
                         price = None # Ensure result is None


                 elif asset.asset_type and asset_type == "bond":
                     # Try Alpha Vantage bond yield quote
                     print(f"  Trying Alpha Vantage for latest bond yield for {asset.symbol}...")
                     maturity = None
                     if asset.symbol.upper() == "DGS10" or asset.symbol.upper() == "US10Y":
                         maturity = "10year"
                     elif asset.symbol.upper() == "DGS5" or asset.symbol.upper() == "US5Y":
                         maturity = "5year"
                     elif asset.symbol.upper() == "DGS30" or asset.symbol.upper() == "US30Y":
                         maturity = "30year"

                     if maturity:
                          # fetch_alpha_vantage_bond_yield returns a DataFrame
                          price_df = fetch_alpha_vantage_bond_yield(maturity, start_date=None, end_date=None) # Pass None for dates here
                          if price_df is not None and isinstance(price_df, pd.DataFrame) and not price_df.empty:
                               price = price_df['price'].iloc[-1] # Get latest price from DataFrame
                               print(f"Got latest price for bond {asset.symbol}: {price} (from AV Bond Yield)")
                          else:
                               price = None
                               print(f"Failed to get latest price for bond {asset.symbol} from AV Bond Yield.")

                     if price is None and not maturity: # Handle unknown bond types that weren't mapped
                         print(f"Unknown bond symbol {asset.symbol} for latest fetch in fetch_market_data.")
                         price = None

                 else:
                     # Handle assets with no asset_type or unknown type
                     print(f"Unknown asset type '{asset.asset_type}' for latest fetch for {asset.symbol} in fetch_market_data. Skipping.")
                     price = None # Ensure price is None for unknown types


                 # --- Store the fetched scalar price (if valid) ---
                 # store_market_data will check if price is valid (float/int, not NaN/Inf)
                 if price is not None:
                      print(f"  Successfully fetched latest price for {asset.symbol}. Storing...")
                      store_market_data(asset, price=price)
                 else:
                     print(f"Failed to get latest price for {asset.symbol} from any source in fetch_market_data after all attempts.")


        except Exception as e:
            # Catch unexpected errors during processing a single symbol fetch
            print(f"Unexpected error processing symbol {symbol} in fetch_market_data: {e}")
            # traceback.print_exc() # Uncomment for detailed error during development

    try:
        db.session.commit()
        print("[Market data session committed.]")
    except Exception as commit_err:
        db.session.rollback()
        print(f"CRITICAL DATABASE COMMIT ERROR during market data fetch: {commit_err}")
        # traceback.print_exc()


    print("[Market data fetching completed.]")
    
def get_historical_data_for_asset(asset_id, start_date=None, end_date=None):
    """
    Get historical data for a specific asset from database.
    Ensures fetched dates are timezone-aware UTC.
    ... (rest of docstring) ...
    """
    # ... (context check and initial print) ...

    try:
        # Set default dates if not provided (using datetime.now(UTC))
        if end_date is None:
            end_date = datetime.now(UTC) # <--- Ensure using datetime.now(UTC) here
        if start_date is None:
            # Default to 1 year of data (using datetime.now(UTC))
            start_date = end_date - timedelta(days=365)


        # Query database - returns MarketData objects
        query = MarketData.query.filter(
            MarketData.asset_id == asset_id,
            MarketData.date >= start_date,
            MarketData.date <= end_date
        ).order_by(MarketData.date)


        data = query.all()

        if not data:
            start_date_str = start_date.strftime('%Y-%m-%d') if start_date else 'None'
            end_date_str = end_date.strftime('%Y-%m-%d') if end_date else 'None'
            print(f"No historical data found in DB for asset ID {asset_id} between {start_date_str} and {end_date_str}.")
            return None

        # Convert data to DataFrame
        df = pd.DataFrame([(item.date, item.price) for item in data], columns=["date", "price"])

        # Ensure date is datetime
        df['date'] = pd.to_datetime(df['date'])

        # --- Make fetched dates timezone-aware UTC if they are naive ---
        # Dates saved with datetime.utcnow() are naive but represent UTC.
        # Localize them as UTC if they don't have timezone info.
        if df['date'].iloc[0].tzinfo is None: # Check if the first datetime is naive
             df['date'] = df['date'].dt.tz_localize(UTC) # Localize naive dates as UTC
             print(f"  Localized fetched DB dates for asset ID {asset_id} to UTC.")

        # Set date as index
        df = df.set_index('date')


        # Ensure price is float and drop rows with invalid prices
        df['price'] = pd.to_numeric(df['price'], errors='coerce')
        # Drop rows where price is NaN or Inf, keep rows where index (date) is valid
        df = df[df['price'].notna()].copy() # Keep rows where price is not NaN, ensure copy


        # Sort by date just in case
        df = df.sort_index()

        print(f"Fetched {len(df)} historical data points from DB for asset ID {asset_id}.")
        return df[['price']] # Return DataFrame with date (index) and price column

    except Exception as e:
        print(f"Error fetching historical data from DB for asset {asset_id}: {e}")
        traceback.print_exc() # Print traceback for debug
        db.session.rollback() # Safeguard
        return None
# --- Scheduler Initialization ---

def initialize_scheduler(app):
    """Initialize the background scheduler for market data updates"""
    # Pass the app instance to the scheduler setup if needed later,
    # e.g., if scheduler jobs need to manually push context.
    # This function should be called ONCE during app startup in run.py.
    print("Initializing background scheduler...")
    scheduler = BackgroundScheduler()

    # Schedule data updates
    # Use lambda functions to wrap the job call within an app context
    # This is crucial for jobs that access db.session
    @scheduler.scheduled_job('interval', hours=1, id='fetch_latest_market_data', misfire_grace_time=600) # Added misfire_grace_time
    def scheduled_fetch_latest():
        with app.app_context():
            print("[Running scheduled job: Fetch Latest Market Data]")
            try:
                fetch_market_data(historical=False)
                print("[Scheduled job finished: Fetch Latest Market Data - Success]")
            except Exception as e:
                 print(f"[Scheduled job finished: Fetch Latest Market Data - Failed] Error: {e}")
                 # traceback.print_exc()


    # Once a day, update historical data
    @scheduler.scheduled_job('cron', hour=1, minute=0, id='fetch_historical_market_data', misfire_grace_time=3600) # Added misfire_grace_time
    def scheduled_fetch_historical():
         with app.app_context():
            print("[Running scheduled job: Fetch Historical Market Data]")
            try:
                fetch_market_data(historical=True)
                print("[Scheduled job finished: Fetch Historical Market Data - Success]")
            except Exception as e:
                 print(f"[Scheduled job finished: Fetch Historical Market Data - Failed] Error: {e}")
                 # traceback.print_exc()

    print("Background scheduler jobs added.")
    # The scheduler will be started in the init() function called by run.py

    return scheduler

scheduler = None # Global variable to hold the scheduler instance

def init(app):
    """Initialize the market fetcher module and start the scheduler"""
    global scheduler
    if scheduler is None:
        # Pass the app instance to initialize_scheduler
        print("Initializing market fetcher with app and starting scheduler...")
        scheduler = initialize_scheduler(app)
        # Start the scheduler here after it's initialized
        try:
             scheduler.start()
             print("Market data scheduler started.")
        except Exception as e:
             print(f"CRITICAL ERROR starting market data scheduler: {e}")
             # traceback.print_exc()
             scheduler = None # Reset scheduler if it failed to start
             print("Market data scheduler could not be started.")
    else:
        print("Market fetcher init called, but scheduler already initialized.")

    return scheduler

# The __main__ block is for testing the script directly, not used when imported by Flask
if __name__ == "__main__":
    print("Running market_fetcher.py directly.")
    # To run fetch_market_data directly, you need to set up a minimal Flask app context
    # as database operations require it.
    # Example:
    from flask import Flask
    print("Setting up test Flask app context...")
    test_app = Flask(__name__)
    # Load config (replace with your actual config loading if complex)
    test_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:////home/lx94/test/portfolio_optimization_tool/instance/portfolio.db"
    test_app.secret_key = "test_secret_key" # Set a dummy secret key if session is needed

    # Need to import the Asset model to add assets
    from app.models import Asset # <--- Import Asset model here

    db.init_app(test_app) # Initialize db with test app

    with test_app.app_context():
        print("Test app context created.")
        print("Checking/creating database tables...")
        db.create_all() # Create tables if they don't exist
        print("Database tables checked/created in test context.")

        # --- Add test assets if the asset table is empty ---
        if Asset.query.count() == 0:
            print("Asset table is empty. Adding test assets...")
            test_assets_to_add = [
                # User ID is required by your Asset model based on its definition
                # Assuming a User with ID 1 exists or is created elsewhere for testing,
                # or you might need to create a dummy user first if required.
                # If your Asset model links to User, ensure a User exists with ID 1 for this test.
                Asset(symbol='AAPL', company_name='Apple Inc.', asset_type='stock', user_id=1),
                Asset(symbol='MSFT', company_name='Microsoft Corp.', asset_type='stock', user_id=1),
                Asset(symbol='BTC-USD', company_name='Bitcoin', asset_type='crypto', user_id=1), # Example Crypto
                # Add more assets as needed for testing
            ]
            db.session.bulk_save_objects(test_assets_to_add)
            db.session.commit()
            print(f"Added {len(test_assets_to_add)} test assets.")
        else:
            print("Asset table is not empty. Skipping adding test assets.")
        # --- End Add test assets ---


        # Initialize and start the scheduler (optional for testing immediate fetch)
        # scheduler = initialize_scheduler(test_app)
        # try:
        #     scheduler.start()
        #     print("Test scheduler started.")
        # except Exception as e:
        #      print(f"Error starting test scheduler: {e}")

        # Fetch data immediately for testing
        print("Fetching market data immediately for testing...")
        # fetch_market_data(historical=False) # Fetch latest - commented out as per previous suggestion
        fetch_market_data(historical=True) # Fetch historical
        print("Market data fetcher test completed.")

        # If you started the scheduler, keep the script alive
        # try:
        #     while True:
        #         time.sleep(1)
        # except (KeyboardInterrupt, SystemExit):
        #     if scheduler:
        #         scheduler.shutdown()
        #     print("Test scheduler shut down.")

    print("Exiting market_fetcher.py __main__ block.")
    
    if __name__ == "__main__":
        print("Running market_fetcher.py directly.")
        from flask import Flask
        print("Setting up test Flask app context...")
        test_app = Flask(__name__)
        test_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:////home/lx94/test/portfolio_optimization_tool/instance/portfolio.db"
        test_app.secret_key = "test_secret_key"

        from app.models import Asset
        db.init_app(test_app)

        with test_app.app_context():
            print("Test app context created.")
            print("Checking/creating database tables...")
            db.create_all()
            print("Database tables checked/created in test context.")

            if Asset.query.count() == 0:
                print("Asset table is empty. Adding test assets...")
                test_assets_to_add = [
                    Asset(symbol='AAPL', company_name='Apple Inc.', asset_type='stock', user_id=1),
                    Asset(symbol='MSFT', company_name='Microsoft Corp.', asset_type='stock', user_id=1),
                    Asset(symbol='BTC-USD', company_name='Bitcoin', asset_type='crypto', user_id=1),
                ]
                db.session.bulk_save_objects(test_assets_to_add)
                db.session.commit()
                print(f"Added {len(test_assets_to_add)} test assets.")
            else:
                print("Asset table is not empty. Skipping adding test assets.")

            # --- NEW PATCH: Update assets with Unknown type ---
            from app.market_fetcher import fetch_and_map_asset_details
            unknown_assets = Asset.query.filter_by(asset_type="Unknown").all()
            for asset in unknown_assets:
                print(f"Fixing type for unknown asset: {asset.symbol}...")
                details = fetch_and_map_asset_details(asset.symbol)
                if details and details.get("type") != "Unknown":
                    print(f"  -> Updating {asset.symbol} to type: {details['type']}")
                    asset.asset_type = details["type"]
                else:
                    print(f"  -> Could not identify type for {asset.symbol}. Leaving as Unknown.")
            db.session.commit()
            print("Asset type fix patch complete.\n")

            print("Fetching market data immediately for testing...")
            fetch_market_data(historical=True)
            print("Market data fetcher test completed.")

    print("Exiting market_fetcher.py __main__ block.")
