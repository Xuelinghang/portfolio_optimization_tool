# app/routes/portfolio_api.py

import os
import json
import io
import csv
from flask import (Blueprint, request, jsonify, session, redirect, url_for,
                   render_template, abort, send_file)
from werkzeug.utils import secure_filename
import pandas as pd

from app import db
from app.models import Portfolio, Asset

portfolio_bp = Blueprint("portfolio", __name__)

# --- Portfolio API Endpoints (Session-based) ---


@portfolio_bp.route("/manual", methods=["POST"])
def submit_manual_entry():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user_id = session["user_id"]
    data = request.get_json()
    symbol = data.get("asset_symbol")
    quantity = data.get("quantity")
    purchase_price = data.get("purchase_price")
    asset_type = data.get("asset_type", "Stock")  # default type

    if not symbol or not quantity or not purchase_price:
        return jsonify({"error": "Missing fields"}), 400

    asset = Asset.query.filter_by(symbol=symbol, user_id=user_id).first()
    if not asset:
        asset = Asset(symbol=symbol, asset_type=asset_type, user_id=user_id)
        db.session.add(asset)
        db.session.commit()

    # Create portfolio entry with proper data structure
    # For simplicity, we'll just add this to the portfolio_data JSON
    portfolio = Portfolio.query.filter_by(user_id=user_id).first()
    if not portfolio:
        portfolio = Portfolio(user_id=user_id, portfolio_name="My Portfolio")
        portfolio_data = []
    else:
        try:
            portfolio_data = json.loads(
                portfolio.portfolio_data) if portfolio.portfolio_data else []
        except:
            portfolio_data = []

    # Add new entry
    portfolio_data.append({
        "ticker": symbol,
        "allocation": float(quantity) * float(purchase_price)
    })

    # Update portfolio
    portfolio.portfolio_data = json.dumps(portfolio_data)
    db.session.add(portfolio)
    db.session.commit()

    return jsonify({"message": "Asset added to portfolio"}), 201


@portfolio_bp.route("/upload", methods=["POST"])
def upload_csv():
    # Check if user is logged in
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    user_id = session["user_id"]

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join("uploads", filename)
    os.makedirs("uploads", exist_ok=True)

    try:
        file.save(filepath)
        df = pd.read_csv(filepath)

        # Process the CSV file into portfolio_data structure
        portfolio_data = []
        invalid_tickers = []

        # Check if the CSV has the expected structure
        if 'Symbol' in df.columns and ('Weight' in df.columns
                                       or 'Balance' in df.columns):
            for _, row in df.iterrows():
                ticker = str(row['Symbol']).strip().upper()
                if not ticker or ticker.lower() in ['nan', '']:
                    continue

                # Validate ticker using Yahoo Finance
                try:
                    import yfinance as yf
                    stock = yf.Ticker(ticker)
                    info = stock.info

                    # Check if we got back a valid ticker object with meaningful info
                    if not info or 'symbol' not in info:
                        invalid_tickers.append({
                            'ticker':
                            ticker,
                            'reason':
                            'Invalid ticker symbol'
                        })
                        continue
                except Exception as e:
                    print(f"Error validating ticker {ticker}: {str(e)}")
                    # Try validating with Alpha Vantage if Yahoo fails
                    try:
                        alpha_vantage_key = os.environ.get(
                            'ALPHA_VANTAGE_API_KEY')
                        if alpha_vantage_key:
                            url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker}&apikey={alpha_vantage_key}"
                            response = requests.get(url, timeout=10)
                            data = response.json()

                            if 'Global Quote' not in data or not data[
                                    'Global Quote'] or '01. symbol' not in data[
                                        'Global Quote']:
                                invalid_tickers.append({
                                    'ticker':
                                    ticker,
                                    'reason':
                                    'Could not validate ticker with either Yahoo Finance or Alpha Vantage'
                                })
                                continue
                    except Exception as av_error:
                        print(
                            f"Alpha Vantage validation error for {ticker}: {str(av_error)}"
                        )
                        # Add to invalid tickers but continue processing
                        invalid_tickers.append({
                            'ticker':
                            ticker,
                            'reason':
                            'Failed validation with both services'
                        })
                        continue

                # Check for allocation
                if 'Weight' in df.columns:
                    # Parse percentage to decimal (remove % sign if present)
                    weight_str = str(row['Weight']).replace('%', '')
                    try:
                        weight = float(weight_str) / 100 if '%' in str(
                            row['Weight']) else float(weight_str)
                    except:
                        weight = 0

                    # Skip entries with zero or negative weight
                    if weight <= 0:
                        continue

                    portfolio_data.append({
                        "ticker": ticker,
                        "allocation": weight
                    })
                elif 'Balance' in df.columns:
                    # If balance is provided, will convert to allocation later
                    balance_str = str(row['Balance']).replace('$', '').replace(
                        ',', '')
                    try:
                        balance = float(balance_str)
                    except:
                        balance = 0

                    # Skip entries with zero or negative balance
                    if balance <= 0:
                        continue

                    # Store temporarily
                    portfolio_data.append({
                        "ticker": ticker,
                        "balance": balance
                    })

            # If no valid entries found
            if len(portfolio_data) == 0:
                # If we have invalid tickers, return a helpful error
                if invalid_tickers:
                    os.remove(filepath)  # Clean up
                    error_message = "No valid tickers found in the CSV. Invalid tickers: "
                    error_message += ", ".join(
                        [item['ticker'] for item in invalid_tickers[:5]])
                    if len(invalid_tickers) > 5:
                        error_message += f" and {len(invalid_tickers) - 5} more"
                    return jsonify({"error": error_message}), 400
                else:
                    os.remove(filepath)  # Clean up
                    return jsonify({
                        "error":
                        "No valid portfolio entries found in the CSV"
                    }), 400

            # If using balance, convert to allocation percentages
            if 'Balance' in df.columns:
                total_balance = sum(
                    entry.get("balance", 0) for entry in portfolio_data)
                if total_balance > 0:
                    for entry in portfolio_data:
                        entry["allocation"] = entry.get("balance",
                                                        0) / total_balance
                        entry.pop("balance", None)
            else:
                # Normalize allocation to ensure they sum to 1.0
                total_allocation = sum(
                    entry.get("allocation", 0) for entry in portfolio_data)
                if total_allocation > 0:
                    for entry in portfolio_data:
                        entry["allocation"] = entry.get("allocation",
                                                        0) / total_allocation

            # Create the portfolio
            portfolio_name = request.form.get('portfolioName',
                                              f"Imported Portfolio")

            # Create assets for each ticker in the portfolio
            for entry in portfolio_data:
                asset = Asset.query.filter_by(symbol=entry["ticker"],
                                              user_id=user_id).first()
                if not asset:
                    asset_type = 'Stock'  # Default to Stock
                    if 'Type' in df.columns:
                        # See if we can get the asset type from the CSV
                        matching_row = df[df['Symbol'] ==
                                          entry["ticker"]].iloc[0]
                        if 'Type' in matching_row:
                            asset_type = matching_row['Type']

                    asset = Asset(symbol=entry["ticker"],
                                  asset_type=asset_type,
                                  user_id=user_id)
                    db.session.add(asset)

            # Save to database
            portfolio = Portfolio(user_id=user_id,
                                  portfolio_name=portfolio_name,
                                  portfolio_data=json.dumps(portfolio_data))
            db.session.add(portfolio)
            db.session.commit()

            # Return a successful response, but include warnings about invalid tickers if any
            response_data = {
                "message": "Portfolio created successfully",
                "id": portfolio.id
            }
            if invalid_tickers:
                warning_message = f"Note: {len(invalid_tickers)} invalid ticker(s) were skipped: "
                warning_message += ", ".join(
                    [item['ticker'] for item in invalid_tickers[:3]])
                if len(invalid_tickers) > 3:
                    warning_message += f" and {len(invalid_tickers) - 3} more"
                response_data["warning"] = warning_message

            os.remove(filepath)  # Clean up the uploaded file
            return jsonify(response_data), 201
        else:
            os.remove(filepath)  # Clean up
            return jsonify({
                "error":
                "CSV must contain Symbol and either Weight or Balance columns"
            }), 400

    except Exception as e:
        import traceback
        print(f"CSV upload error: {str(e)}")
        print(traceback.format_exc())

        if os.path.exists(filepath):
            os.remove(filepath)  # Clean up in case of error
        return jsonify({"error": f"Error processing CSV: {str(e)}"}), 500


@portfolio_bp.route("/open/<int:portfolio_id>", methods=["GET"])
def open_portfolio(portfolio_id):
    if "user_id" not in session:
        return redirect(url_for("auth.login_page"))

    # Verify ownership of the portfolio
    portfolio = Portfolio.query.filter_by(id=portfolio_id,
                                          user_id=session["user_id"]).first()
    if not portfolio:
        abort(404, description="Portfolio not found or unauthorized.")

    try:
        portfolio_data = json.loads(
            portfolio.portfolio_data) if portfolio.portfolio_data else []
    except Exception:
        portfolio_data = []

    # Redirect to Flask-based portfolio analysis page
    return redirect(url_for('view_dashboard', portfolio_id=portfolio_id))


@portfolio_bp.route("/edit/<int:portfolio_id>", methods=["GET"])
def edit_portfolio(portfolio_id):
    if "user_id" not in session:
        return redirect(url_for("auth.login_page"))

    # Verify ownership of the portfolio
    portfolio = Portfolio.query.filter_by(id=portfolio_id,
                                          user_id=session["user_id"]).first()
    if not portfolio:
        abort(404, description="Portfolio not found or unauthorized.")

    # Render the data-entry page pre-populated with portfolio data
    return render_template("data-entry.html",
                           portfolio=portfolio,
                           username=session.get("username"))


@portfolio_bp.route("/download/<int:portfolio_id>", methods=["GET"])
def download_portfolio(portfolio_id):
    if "user_id" not in session:
        abort(401)

    # Verify ownership
    portfolio = Portfolio.query.filter_by(id=portfolio_id,
                                          user_id=session["user_id"]).first()
    if not portfolio:
        abort(404, description="Portfolio not found or unauthorized.")

    try:
        portfolio_data = json.loads(
            portfolio.portfolio_data) if portfolio.portfolio_data else []
    except Exception:
        portfolio_data = []

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Symbol", "Weight"])
    for entry in portfolio_data:
        writer.writerow([
            entry.get("ticker", ""), f"{entry.get('allocation', 0) * 100:.2f}%"
        ])

    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode('utf-8')),
                     mimetype='text/csv',
                     as_attachment=True,
                     download_name=f"{portfolio.portfolio_name}.csv")
