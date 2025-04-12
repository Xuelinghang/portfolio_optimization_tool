import os
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
import requests
from alpha_vantage.fundamentaldata import FundamentalData
from alpha_vantage.timeseries import TimeSeries

# Import app, models and db from app package
from app import create_app, db
from app.models import User, Portfolio, Asset, MarketData
from app.market_fetcher import fetch_market_data

# Create Flask application
app = create_app()
bcrypt = Bcrypt(app)

from app.routes.portfolio_api import portfolio_bp

# Create all database tables if they don't exist
with app.app_context():
    db.create_all()

# Routes
@app.route('/')
def index():
    username = session.get('username')
    return render_template('index.html', username=username)

@app.route('/login-page')
def login_page():
    return render_template('login.html')

@app.route('/register-page')
def register_page():
    return render_template('register.html')

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    
    # Check if username or email already exists
    existing_user = User.query.filter(
        (User.username == data['username']) | 
        (User.email == data['email'])
    ).first()
    
    if existing_user:
        return jsonify({"error": "Username or email already exists"}), 400
    
    # Create new user
    hashed_password = bcrypt.generate_password_hash(data['password']).decode('utf-8')
    new_user = User(
        username=data['username'],
        email=data['email'],
        password_hash=hashed_password
    )
    
    db.session.add(new_user)
    db.session.commit()
    
    return jsonify({"message": "Registration successful"}), 201

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    
    # Check if login identifier is username or email
    user = User.query.filter(
        (User.username == data['username']) | 
        (User.email == data['username'])
    ).first()
    
    if not user or not bcrypt.check_password_hash(user.password_hash, data['password']):
        return jsonify({"error": "Invalid credentials"}), 401
    
    # Create session
    session['user_id'] = user.id
    session['username'] = user.username
    
    return jsonify({
        "message": "Login successful",
        "username": user.username
    }), 200

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"message": "Logout successful"}), 200

@app.route('/data-entry')
def data_entry():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    
    username = session.get('username')
    portfolio_id = request.args.get('portfolio_id')
    
    if portfolio_id:
        # Get portfolio for editing
        portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=session['user_id']).first()
        if not portfolio:
            return redirect(url_for('auth.data_entry'))
    else:
        portfolio = None
    
    return render_template('data-entry.html', username=username, portfolio=portfolio)

@app.route('/saved-portfolios')
def saved_portfolios():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    
    username = session.get('username')
    
    # Get user's portfolios
    portfolios = Portfolio.query.filter_by(user_id=session['user_id']).all()
    
    # Enhance portfolio data for display
    enhanced_portfolios = []
    for portfolio in portfolios:
        try:
            portfolio_entries = json.loads(portfolio.portfolio_data) if portfolio.portfolio_data else []
        except Exception as e:
            print(f"Error parsing portfolio data for portfolio {portfolio.id}: {e}")
            portfolio_entries = []
        valid_entries = [entry for entry in portfolio_entries if entry.get("ticker")]
        enhanced_portfolios.append({
            "id": portfolio.id,
            "portfolio_name": portfolio.portfolio_name,
            "num_assets": len(valid_entries),
            "created_at": portfolio.purchase_date
        })
    
    return render_template('saved-portfolios.html', username=username, portfolios=enhanced_portfolios)

@app.route('/portfolio-analysis')
def portfolio_analysis_selection():
    """Show the portfolio analysis selection page"""
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    
    username = session.get('username')
    
    # Get user's portfolios
    portfolios = Portfolio.query.filter_by(user_id=session['user_id']).all()
    
    return render_template('portfolio_analysis_selection.html', 
                           portfolios=portfolios,
                           username=username)

@app.route('/save-portfolio', methods=['POST'])
def save_portfolio():
    if 'user_id' not in session:
        return jsonify({"error": "Authentication required"}), 401
    
    data = request.get_json()
    
    # Create new portfolio with the complete data (including start and end dates if provided)
    new_portfolio = Portfolio(
        user_id=session['user_id'],
        portfolio_name=data['portfolioName'],
        portfolio_data=json.dumps(data['portfolioData'])
    )
    
    db.session.add(new_portfolio)
    db.session.commit()
    
    return jsonify({"message": "Portfolio saved", "portfolio_id": new_portfolio.id}), 201

@app.route('/update-portfolio/<int:portfolio_id>', methods=['POST'])
def update_portfolio(portfolio_id):
    if 'user_id' not in session:
        return jsonify({"error": "Authentication required"}), 401
    
    portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=session['user_id']).first()
    
    if not portfolio:
        return jsonify({"error": "Portfolio not found"}), 404
    
    data = request.get_json()
    
    portfolio.portfolio_name = data['portfolioName']
    portfolio.portfolio_data = json.dumps(data['portfolioData'])
    
    db.session.commit()
    
    return jsonify({"message": "Portfolio updated"}), 200

@app.route('/portfolio/delete/<int:portfolio_id>', methods=['POST'])
def delete_portfolio(portfolio_id):
    if 'user_id' not in session:
        return jsonify({"error": "Authentication required"}), 401
    
    portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=session['user_id']).first()
    
    if not portfolio:
        return jsonify({"error": "Portfolio not found"}), 404
    
    db.session.delete(portfolio)
    db.session.commit()
    
    return jsonify({"message": "Portfolio deleted"}), 200

# Streamlit Dashboard integration routes
@app.route('/portfolio/<int:portfolio_id>/dashboard')
def view_dashboard(portfolio_id):
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
        
    portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=session['user_id']).first()
    
    if not portfolio:
        return redirect(url_for('saved_portfolios'))
    
    # Render the portfolio analysis template directly
    username = session.get('username')
    return render_template('portfolio_analysis.html', portfolio=portfolio, username=username)

@app.route('/dashboard/data/<int:portfolio_id>')
def get_portfolio_data(portfolio_id):
    # In production, you would check authentication here
    
    portfolio = Portfolio.query.filter_by(id=portfolio_id).first()
    
    if not portfolio:
        return jsonify({"error": "Portfolio not found"}), 404
    
    try:
        # Parse portfolio data (contains tickers, allocations, and start/end dates)
        portfolio_data = json.loads(portfolio.portfolio_data)
        
        # Import the market fetcher for real data
        from app.market_fetcher import fetch_yahoo_data, fetch_alpha_vantage_data, fetch_coingecko_data
        
        # Create a DataFrame with holdings data
        holdings = []
        
        # Helper to get asset details
        def get_asset_details(ticker):
            try:
                import yfinance as yf
                stock = yf.Ticker(ticker)
                info = stock.info
                category = 'ETF' if 'ETF' in info.get('quoteType', 'Stock') else info.get('quoteType', 'Stock')
                name = info.get('shortName', ticker) 
                pe_ratio = info.get('trailingPE', 0.0) or 0.0
                div_yield = info.get('dividendYield', 0.0) or 0.0
                expense_ratio = info.get('annualReportExpenseRatio', 0.0) or 0.0
                return {
                    'Category': category,
                    'Name': name,
                    'PE': pe_ratio,
                    'Yield': div_yield,
                    'Expense_Ratio': expense_ratio
                }
            except:
                return {
                    'Category': 'Stock',
                    'Name': ticker,
                    'PE': 0.0,
                    'Yield': 0.0,
                    'Expense_Ratio': 0.0
                }
        
        # Ensure assets exist in database and build holdings including investment dates
        for entry in portfolio_data:
            ticker = entry['ticker']
            user_id = portfolio.user_id
            asset = Asset.query.filter_by(symbol=ticker, user_id=user_id).first()
            if not asset:
                asset_type = 'Stock'
                if ticker.startswith('BTC') or ticker.startswith('ETH') or ticker.lower() in ['bitcoin', 'ethereum']:
                    asset_type = 'Crypto'
                elif ticker in ['10YEAR', '5YEAR', '30YEAR', 'AGG', 'BND']:
                    asset_type = 'Bond'
                elif ticker in ['SPY', 'QQQ', 'VTI', 'VOO']:
                    asset_type = 'ETF'
                asset = Asset(symbol=ticker, asset_type=asset_type, user_id=user_id)
                db.session.add(asset)
                db.session.commit()
            
            asset_details = get_asset_details(ticker)
            holdings.append({
                "ticker": ticker,
                'Weight': float(entry['allocation']) if entry.get('allocation') not in [None, ''] else 0.0,
                'Category': asset_details['Category'],
                'Name': asset_details['Name'],
                'Expense_Ratio': asset_details['Expense_Ratio'],
                'Yield': asset_details['Yield'],
                'PE': asset_details['PE'],
                'start_date': entry.get("start_date", ""),
                'end_date': entry.get("end_date", "")
            })
        
        # Get market data for portfolio values
        prices = {}
        today = datetime.now()
        asset_market_data = {}
        all_dates = set()
        
        for entry in portfolio_data:
            ticker = entry['ticker']
            asset = Asset.query.filter_by(symbol=ticker, user_id=portfolio.user_id).first()
            if asset:
                market_data = MarketData.query.filter_by(asset_id=asset.id).order_by(MarketData.date).all()
                if market_data and len(market_data) > 30:
                    dates = [data.date for data in market_data]
                    ticker_prices = [data.price for data in market_data]
                    for date in dates:
                        all_dates.add(date.strftime('%Y-%m-%d'))
                    prices[ticker] = ticker_prices
                    asset_market_data[ticker] = list(zip([d.strftime('%Y-%m-%d') for d in dates], ticker_prices))
                else:
                    if asset.asset_type.lower() in ['stock', 'etf']:
                        df = fetch_yahoo_data(ticker, period="1y", interval="1d")
                        if isinstance(df, pd.DataFrame) and not df.empty and 'Close' in df.columns:
                            dates = df.index.tolist()
                            ticker_prices = df['Close'].tolist()
                            print(f"Ticker {ticker}: Got {len(dates)} data points from Yahoo Finance")
                            for date in dates:
                                all_dates.add(date.strftime('%Y-%m-%d'))
                            prices[ticker] = ticker_prices
                            asset_market_data[ticker] = list(zip([d.strftime('%Y-%m-%d') for d in dates], ticker_prices))
                            for i, date in enumerate(dates):
                                existing_data = MarketData.query.filter_by(asset_id=asset.id, date=date).first()
                                if not existing_data:
                                    market_data = MarketData(asset_id=asset.id, date=date, price=ticker_prices[i])
                                    db.session.add(market_data)
                            db.session.commit()
        
        if all_dates:
            dates = sorted(list(all_dates))
            for ticker in asset_market_data:
                ticker_data_dict = dict(asset_market_data[ticker])
                complete_prices = []
                last_price = None
                for date in dates:
                    if date in ticker_data_dict:
                        price = ticker_data_dict[date]
                        last_price = price
                    elif last_price is not None:
                        price = last_price
                    else:
                        price = 100.0
                    complete_prices.append(price)
                prices[ticker] = complete_prices
        else:
            dates = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(365, 0, -1)]
            for entry in portfolio_data:
                ticker = entry['ticker']
                if ticker not in prices:
                    try:
                        df = fetch_yahoo_data(ticker, period="1y", interval="1d")
                        if isinstance(df, pd.DataFrame) and not df.empty and 'Close' in df.columns:
                            ticker_prices = []
                            date_dict = {date.strftime('%Y-%m-%d'): price for date, price in zip(df.index, df['Close'])}
                            for date in dates:
                                if date in date_dict:
                                    ticker_prices.append(date_dict[date])
                                else:
                                    ticker_prices.append(ticker_prices[-1] if ticker_prices else 100.0)
                            prices[ticker] = ticker_prices
                        else:
                            prices[ticker] = [100.0] * len(dates)
                    except:
                        prices[ticker] = [100.0] * len(dates)
        
        failed_tickers = []
        for entry in portfolio_data:
            ticker = entry['ticker']
            if ticker not in prices or (len(prices[ticker]) < len(dates) * 0.9):
                failed_tickers.append(ticker)
        
        return jsonify({
            'portfolio_name': portfolio.portfolio_name,
            'holdings': holdings,
            'prices': prices,
            'dates': dates,
            'failed_tickers': failed_tickers
        })
    
    except Exception as e:
        import traceback
        print(f"Error in get_portfolio_data: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route('/portfolio/upload', methods=['POST'])
def upload_csv():
    if 'user_id' not in session:
        return jsonify({"error": "Authentication required"}), 401
    
    portfolio_name = request.form.get('portfolioName')
    file = request.files.get('file')
    
    if not file or not portfolio_name:
        return jsonify({"error": "Missing file or portfolio name"}), 400
    
    try:
        df = pd.read_csv(file)
        
        # Check for required columns; allow optional Start Date and End Date columns
        if not all(col in df.columns for col in ['Symbol', 'Weight']):
            if not all(col in df.columns for col in ['Symbol', 'Balance']):
                return jsonify({"error": "CSV must contain Symbol column and either Weight or Balance columns"}), 400
        
        portfolio_entries = []
        if 'Weight' in df.columns:
            for _, row in df.iterrows():
                weight_str = str(row['Weight']).replace('$', '').replace(',', '').replace('%', '')
                try:
                    weight = float(weight_str)
                except:
                    weight = 0
                start_date = row['Start Date'] if 'Start Date' in df.columns and pd.notnull(row['Start Date']) else ""
                end_date = row['End Date'] if 'End Date' in df.columns and pd.notnull(row['End Date']) else ""
                portfolio_entries.append({
                    'ticker': row['Symbol'],
                    'allocation': weight,
                    'start_date': start_date,
                    'end_date': end_date
                })
        else:
            for _, row in df.iterrows():
                balance_str = str(row['Balance']).replace('$', '').replace(',', '')
                try:
                    balance = float(balance_str)
                except:
                    balance = 0
                start_date = row['Start Date'] if 'Start Date' in df.columns and pd.notnull(row['Start Date']) else ""
                end_date = row['End Date'] if 'End Date' in df.columns and pd.notnull(row['End Date']) else ""
                portfolio_entries.append({
                    'ticker': row['Symbol'],
                    'allocation': balance,
                    'start_date': start_date,
                    'end_date': end_date
                })
        
        new_portfolio = Portfolio(
            user_id=session['user_id'],
            portfolio_name=portfolio_name,
            portfolio_data=json.dumps(portfolio_entries)
        )
        
        db.session.add(new_portfolio)
        db.session.commit()
        
        return jsonify({"message": "Portfolio uploaded", "portfolio_id": new_portfolio.id}), 201
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/validate-ticker')
def validate_ticker():
    ticker = request.args.get('ticker', '')
    if not ticker or len(ticker) < 1:
        return jsonify({"valid": False, "message": "Ticker symbol is required"}), 400
    
    ticker = ticker.strip().upper()
    
    try:
        import yfinance as yf
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            if info and 'symbol' in info and info['symbol']:
                return jsonify({
                    "valid": True,
                    "info": {
                        "symbol": info.get('symbol'),
                        "name": info.get('shortName') or info.get('longName'),
                        "exchange": info.get('exchange'),
                        "type": info.get('quoteType')
                    }
                })
        except Exception as e:
            print(f"Yahoo validation error for {ticker}: {str(e)}")
            
        alpha_vantage_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
        if alpha_vantage_key:
            url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker}&apikey={alpha_vantage_key}"
            response = requests.get(url, timeout=10)
            data = response.json()
            if 'Global Quote' in data and data['Global Quote'] and '01. symbol' in data['Global Quote']:
                return jsonify({
                    "valid": True,
                    "info": {
                        "symbol": data['Global Quote']['01. symbol'],
                        "source": "Alpha Vantage"
                    }
                })
            search_url = f"https://www.alphavantage.co/query?function=SYMBOL_SEARCH&keywords={ticker}&apikey={alpha_vantage_key}"
            search_response = requests.get(search_url, timeout=10)
            search_data = search_response.json()
            if 'bestMatches' in search_data and search_data['bestMatches']:
                suggested_tickers = []
                for match in search_data['bestMatches'][:3]:
                    suggested_tickers.append(match['1. symbol'])
                return jsonify({
                    "valid": False,
                    "message": f"Could not find exact match for {ticker}",
                    "suggested_tickers": suggested_tickers
                })
        
        return jsonify({
            "valid": False,
            "message": f"Could not validate ticker: {ticker}"
        })
    
    except Exception as e:
        print(f"Ticker validation error: {str(e)}")
        return jsonify({"valid": False, "message": "Error during validation"}), 500

@app.route('/search-ticker')
def search_ticker():
    keyword = request.args.get('keyword', '')
    if not keyword or len(keyword) < 2:
        return jsonify([])
    
    try:
        alpha_vantage_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
        yahoo_finance_key = os.environ.get('YAHOO_FINANCE_API_KEY')
        
        if alpha_vantage_key:
            url = f"https://www.alphavantage.co/query?function=SYMBOL_SEARCH&keywords={keyword}&apikey={alpha_vantage_key}"
            response = requests.get(url, timeout=10)
            data = response.json()
            if 'bestMatches' in data and data['bestMatches']:
                results = []
                for match in data['bestMatches'][:3]:
                    results.append({
                        'symbol': match['1. symbol'],
                        'name': match['2. name']
                    })
                return jsonify(results)
        
        try:
            import yfinance as yf
            matches = []
            try:
                ticker = yf.Ticker(keyword.upper())
                info = ticker.info
                if 'symbol' in info and 'shortName' in info:
                    matches.append({
                        'symbol': info['symbol'],
                        'name': info['shortName']
                    })
            except:
                pass
            if len(matches) < 5:
                common_tickers = {
                    'AAPL': 'Apple Inc.',
                    'MSFT': 'Microsoft Corporation',
                    'AMZN': 'Amazon.com Inc.',
                    'GOOGL': 'Alphabet Inc.',
                    'META': 'Meta Platforms Inc.',
                    'TSLA': 'Tesla Inc.',
                    'NVDA': 'NVIDIA Corporation',
                    'JPM': 'JPMorgan Chase & Co.',
                    'V': 'Visa Inc.',
                    'JNJ': 'Johnson & Johnson',
                    'WMT': 'Walmart Inc.',
                    'SPY': 'SPDR S&P 500 ETF Trust',
                    'QQQ': 'Invesco QQQ Trust',
                    'VTI': 'Vanguard Total Stock Market ETF',
                    'VEA': 'Vanguard FTSE Developed Markets ETF',
                    'VWO': 'Vanguard FTSE Emerging Markets ETF',
                    'BND': 'Vanguard Total Bond Market ETF',
                    'AGG': 'iShares Core U.S. Aggregate Bond ETF'
                }
                for symbol, name in common_tickers.items():
                    if keyword.upper() in symbol or keyword.lower() in name.lower():
                        if not any(match['symbol'] == symbol for match in matches):
                            matches.append({'symbol': symbol, 'name': name})
            return jsonify(matches[:10])
            
        except Exception as e:
            print(f"Yahoo Finance search error: {str(e)}")
            sample_results = []
            common_tickers = {
                'AAPL': 'Apple Inc.',
                'MSFT': 'Microsoft Corporation',
                'AMZN': 'Amazon.com Inc.',
                'GOOGL': 'Alphabet Inc.',
                'META': 'Meta Platforms Inc.',
                'TSLA': 'Tesla Inc.',
                'NVDA': 'NVIDIA Corporation',
                'JPM': 'JPMorgan Chase & Co.',
                'V': 'Visa Inc.',
                'JNJ': 'Johnson & Johnson',
                'WMT': 'Walmart Inc.',
                'SPY': 'SPDR S&P 500 ETF Trust',
                'QQQ': 'Invesco QQQ Trust',
                'VTI': 'Vanguard Total Stock Market ETF',
                'VEA': 'Vanguard FTSE Developed Markets ETF',
                'VWO': 'Vanguard FTSE Emerging Markets ETF',
                'BND': 'Vanguard Total Bond Market ETF',
                'AGG': 'iShares Core U.S. Aggregate Bond ETF'
            }
            for symbol, name in common_tickers.items():
                if keyword.upper() in symbol or keyword.lower() in name.lower():
                    sample_results.append({'symbol': symbol, 'name': name})
            return jsonify(sample_results[:10])
            
    except Exception as e:
        print(f"Ticker search error: {str(e)}")
        return jsonify([])

@app.route('/portfolio/download/<int:portfolio_id>')
def download_portfolio(portfolio_id):
    if 'user_id' not in session:
        return jsonify({"error": "Authentication required"}), 401
    
    portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=session['user_id']).first()
    
    if not portfolio:
        return jsonify({"error": "Portfolio not found"}), 404
    
    try:
        portfolio_data = json.loads(portfolio.portfolio_data)
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Get current prices for each asset
        prices = {}
        for entry in portfolio_data:
            ticker = entry['ticker']
            asset = Asset.query.filter_by(symbol=ticker, user_id=session['user_id']).first()
            if asset:
                latest_price = MarketData.query.filter_by(asset_id=asset.id).order_by(MarketData.date.desc()).first()
                if latest_price:
                    prices[ticker] = latest_price.price
                else:
                    try:
                        from app.market_fetcher import fetch_yahoo_data
                        price = fetch_yahoo_data(ticker, period="1d")
                        if price is not None and isinstance(price, (int, float)):
                            prices[ticker] = float(price)
                        else:
                            prices[ticker] = 100.0
                    except:
                        prices[ticker] = 100.0
            else:
                prices[ticker] = 100.0
                
        format_type = request.args.get('format', 'csv').lower()
        
        if format_type == 'json':
            output_data = {
                "portfolio_name": portfolio.portfolio_name,
                "date": today,
                "holdings": []
            }
            for entry in portfolio_data:
                ticker = entry['ticker']
                allocation = float(entry['allocation'])
                price = prices.get(ticker, 100.0)
                output_data["holdings"].append({
                    "symbol": ticker,
                    "dollar_allocation": allocation,
                    "start_date": entry.get("start_date", ""),
                    "end_date": entry.get("end_date", ""),
                    "current_price": price
                })
            return jsonify(output_data)
        else:
            csv_content = "Symbol,Dollar Allocation,Start Date,End Date,Current_Price\n"
            for entry in portfolio_data:
                ticker = entry['ticker']
                price = prices.get(ticker, '')
                try:
                    allocation = float(entry['allocation'])
                except:
                    allocation = 0
                start_date = entry.get("start_date", "")
                end_date = entry.get("end_date", "")
                csv_content += f"{ticker},${allocation:,.2f},{start_date},{end_date},{price}\n"
            filename = f"portfolio_{portfolio.portfolio_name.replace(' ', '_')}_{today}.csv"
            return csv_content, 200, {
                'Content-Type': 'text/csv',
                'Content-Disposition': f'attachment; filename={filename}'
            }
    
    except Exception as e:
        import traceback
        print(f"Error in download_portfolio: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route('/transactions')
def transactions_page():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    
    username = session.get('username')
    now_date = date.today().strftime('%Y-%m-%d')
    return render_template('transactions.html', username=username, now_date=now_date)


# Initialize market data fetcher at startup
import threading

def init_market_data():
    try:
        from app.market_fetcher import fetch_market_data, init
        with app.app_context():
            scheduler = init()
            fetch_market_data(historical=False)
            print("Market data fetcher initialized successfully")
            return True
    except Exception as e:
        print(f"Warning: Could not initialize market data fetcher: {e}")
        return False

@app.route('/refresh-market-data', methods=['GET'])
def refresh_market_data():
    """Manually refresh market data to get the most current data"""
    if 'user_id' not in session:
        return jsonify({"error": "Authentication required"}), 401
    try:
        from app.market_fetcher import fetch_market_data
        fetch_market_data(historical=False)
        fetch_market_data(historical=True)
        return jsonify({
            "status": "success", 
            "message": "Market data refreshed successfully with the most recent data available",
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
    except Exception as e:
        print(f"Market data refresh error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    market_thread = threading.Thread(target=init_market_data)
    market_thread.daemon = True
    market_thread.start()

app.run(host='0.0.0.0', port=5050, debug=True)
