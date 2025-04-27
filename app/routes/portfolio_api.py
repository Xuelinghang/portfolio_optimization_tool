import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
import requests
# Import Flask-Login decorator and proxy object
from flask_login import login_required, current_user, login_required
from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template, send_file, flash, current_app # Import necessary Flask modules
from werkzeug.utils import secure_filename
import traceback
import time
from io import StringIO # Import StringIO for CSV reading
from sqlalchemy.orm import joinedload

from app import db # Assuming db is initialized in app/__init__.py
from app.models import User, Portfolio, Asset, MarketData, PortfolioAsset, Transaction, CalculationResult
# Import fetcher functions needed in this file
from app.market_fetcher import (
    fetch_yahoo_data, # Used in get_market_data_by_ticker fallback
    fetch_alpha_vantage_data, # Used in get_market_data_by_ticker fallback
    fetch_alpha_vantage_bond_yield, # Not used in this file, can remove import if not used elsewhere
    fetch_fred_data, # Not used in this file, can remove import if not used elsewhere
    fetch_coingecko_data, # Not used directly, but might be used by fetch_and_map_asset_details or simple_price
    fetch_and_map_asset_details, # Used in create/update/upload
    _get_coingecko_id_map, # Used in get_market_data_by_ticker fallback for crypto
    fetch_coingecko_simple_price,
    get_historical_data_for_asset# Used in get_market_data_by_ticker fallback for crypto
)

# Assuming market_fetcher has necessary functions like _get_coingecko_id_map and fetch_coingecko_simple_price

# Define the Blueprint
# Set template_folder for relative paths to templates
portfolio_bp = Blueprint("portfolio_api", __name__, template_folder='templates')

# --- Routes now part of the 'portfolio_api' Blueprint ---

@portfolio_bp.route('/saved', methods=['GET']) # Changed route from /saved-portfolios
@login_required # <--- ADDED Flask-Login decorator to require login
def saved_portfolios():
    """Display the saved portfolios page for the logged-in user."""
    # The @login_required decorator handles authentication
    # Access user ID via current_user from Flask-Login
    user_id = current_user.id # <--- CHANGED from session.get('user_id')
    username = current_user.username # Access username via current_user

    # Fetch portfolios + their assets for the dropdown
    # Use joinedload for efficiency when accessing holdings and asset relationships
    try:
        portfolios = (Portfolio.query
                      .filter_by(user_id=user_id)
                      .options(joinedload(Portfolio.holdings).joinedload(PortfolioAsset.asset))
                      .all())
        print(f"Efficient Frontier page: Found {len(portfolios)} portfolios for user {user_id}.")

    except Exception as e:
        current_app.logger.error(f"Error fetching portfolios for Saved Portfolios page (user {user_id}): {str(e)}")
        traceback.print_exc() # Uncomment for debug
        flash('Error loading portfolios. Please try again.', 'danger')
        portfolios = []

    return render_template('saved-portfolios.html',
                           username=username,
                           portfolios=portfolios) # Pass portfolios list

# Route for the data entry page (Create/Edit Portfolio)
@portfolio_bp.route('/data-entry', methods=['GET'])
@login_required # <--- ADDED Flask-Login decorator to require login
def data_entry():
    # The @login_required decorator handles authentication
    # Access user ID via current_user from Flask-Login
    user_id = current_user.id
    username = current_user.username # Access username via current_user
    portfolio_id = request.args.get('portfolio_id')

    portfolio = None
    if portfolio_id:
        try:
            # Get portfolio for editing - ensure it belongs to the logged-in user
            # Convert portfolio_id to int safely
            portfolio = Portfolio.query.filter_by(id=int(portfolio_id), user_id=user_id).first()
            if not portfolio:
                print(f"Attempted to edit non-existent or unauthorized portfolio ID: {portfolio_id} for user {user_id}")
                return redirect(url_for('portfolio_api.saved_portfolios')) # Redirect if not found or unauthorized
            print(f"Editing portfolio ID {portfolio_id} for user {user_id}.")
        except (ValueError, TypeError): # Catch both ValueError and TypeError for int conversion
             print(f"Invalid portfolio_id received: {portfolio_id}. Must be an integer.")
             return redirect(url_for('portfolio_api.saved_portfolios'))


    return render_template('data-entry.html', username=username, portfolio=portfolio)

# Route to handle saving a NEW portfolio (manual entry form submit)
@portfolio_bp.route('/portfolios', methods=['POST'])
@login_required # <--- ADDED Flask-Login decorator to require login
def create_portfolio():
    """
    Handles the creation of a new portfolio with assets from a manual form submission.
    Expects JSON payload with 'portfolioName' and 'portfolioData' (list of asset entries).
    Saves Portfolio, Asset (if new, with determined type), and PortfolioAsset records (with purchase date).
    """
    # The @login_required decorator handles authentication
    # Access user ID via current_user from Flask-Login
    user_id = current_user.id
    data = request.get_json()

    portfolio_name = data.get('portfolioName')
    portfolio_data = data.get('portfolioData', [])

    print(f"Attempting to create new portfolio for user {user_id}. Name: '{portfolio_name}'. Data entries received: {len(portfolio_data)}")

    if not portfolio_name:
        print("Create portfolio failed: No portfolio name provided.")
        return jsonify({"error": "Portfolio name is required"}), 400

    if not isinstance(portfolio_data, list):
        print(f"Create portfolio failed: 'portfolioData' is not a list. Received type: {type(portfolio_data)}")
        return jsonify({"error": "Invalid data format for portfolio assets"}), 400

    # --- Process and Validate incoming asset data, including purchase date ---
    total_value = 0.0
    valid_portfolio_entries_with_date = []

    for entry in portfolio_data:
        if not isinstance(entry, dict):
             print(f"Skipping invalid entry (not a dict) in incoming data: {entry}")
             continue

        ticker = entry.get('ticker')
        amount_str = entry.get('amount')
        purchase_date_str = entry.get('purchase_date')

        if not ticker or amount_str is None:
            print(f"Skipping entry (missing ticker or amount) in incoming data: {entry}")
            continue

        try:
            amount = float(amount_str)
            if amount < 0:
                 print(f"Skipping entry with negative amount: {entry}")
                 continue

        except ValueError:
            print(f"Skipping entry (invalid amount format): {entry}")
            continue

        # --- Parse Purchase Date String ---
        purchase_date_obj = None
        if purchase_date_str:
             try:
                 purchase_date_obj = datetime.strptime(purchase_date_str, '%Y-%m-%d').date()
             except ValueError:
                  print(f"Warning: Invalid date format received for ticker {ticker}: '{purchase_date_str}'. Expected %Y-%m-%d. Storing as None.")


        valid_portfolio_entries_with_date.append({
            'ticker': ticker.strip().upper(),
            'amount': amount,
            'purchase_date': purchase_date_obj
        })

        total_value += amount

    if not valid_portfolio_entries_with_date:
         print(f"Create portfolio failed: No valid assets with non-negative amounts were provided for '{portfolio_name}'. Total value calculated: {total_value}")
         return jsonify({"error": "No valid assets with non-negative amounts were provided"}), 400

    if total_value <= 0:
        print(f"Warning: Total portfolio value is {total_value} for portfolio '{portfolio_name}'. Allocations will be 0%.")


    # --- Create new Portfolio object and add to session ---
    new_portfolio = Portfolio(
        user_id=user_id, # Link to the current_user ID
        portfolio_name=portfolio_name,
        total_value=total_value
    )
    db.session.add(new_portfolio)

    try:
        db.session.flush() # Flush to get the portfolio ID
        print(f"Created new Portfolio object in session: '{new_portfolio.portfolio_name}' (ID will be {new_portfolio.id} after commit) with calculated total value {new_portfolio.total_value}.")
    except Exception as flush_err:
         db.session.rollback()
         print(f"Error during portfolio flush for '{new_portfolio.portfolio_name}': {flush_err}")
         traceback.print_exc()
         return jsonify({"error": "Database error preparing portfolio"}), 500


    # --- Add PortfolioAsset entries for the validated data, including the purchase date and Asset type ---
    for entry in valid_portfolio_entries_with_date:
        try:
             ticker = entry['ticker'] # Already normalized and uppercase
             amount = entry['amount']
             purchase_date_obj = entry['purchase_date'] # This is the datetime.date object or None

             # --- Asset Finding/Creation ---
             # Find the Asset record by normalized symbol and user_id
             asset = Asset.query.filter_by(symbol=ticker, user_id=user_id).first()
             if not asset:
                 print(f"Asset '{ticker}' not found for user {user_id}. Creating new Asset.")

                 # --- Fetch full details using the helper function ---
                 # Ensure fetch_and_map_asset_details is imported
                 # from ..market_fetcher import fetch_and_map_asset_details # Example import - already imported
                 asset_full_details = fetch_and_map_asset_details(ticker)

                 # --- Use details from the helper function to create the Asset record ---
                 determined_asset_type = asset_full_details.get('type', 'stock')
                 determined_company_name = asset_full_details.get('name', f"{ticker} Company")

                 asset = Asset(symbol=ticker, asset_type=determined_asset_type, user_id=user_id, company_name=determined_company_name)
                 db.session.add(asset)

                 # Flush the asset addition to ensure asset.id is set for the foreign key reference
                 try:
                     db.session.flush()
                     print(f"Created new Asset: {asset.symbol} (ID: {asset.id}, Type: {asset.asset_type}, Name: {asset.company_name}) for user {user_id}")
                 except Exception as asset_flush_err:
                      print(f"Error flushing new Asset {ticker}: {asset_flush_err}. Skipping this asset entry.")
                      traceback.print_exc()
                      db.session.rollback()
                      continue # Skip creating PortfolioAsset for this entry


             # --- PortfolioAsset Creation ---
             if asset and asset.id:
                 allocation_pct = (amount / total_value) * 100 if total_value > 0 else 0.0

                 portfolio_asset = PortfolioAsset(
                     portfolio_id=new_portfolio.id,
                     asset_id=asset.id,
                     dollar_amount=amount,
                     allocation_pct=allocation_pct,
                     purchase_date=purchase_date_obj
                 )
                 db.session.add(portfolio_asset)
                 print(f"Added PortfolioAsset for {ticker} ({amount}, date: {purchase_date_obj}, Asset Type: {asset.asset_type}) to session for portfolio ID {new_portfolio.id}. Allocation: {allocation_pct:.2f}%")


        except Exception as e:
             print(f"Unexpected error processing portfolio entry {entry}: {e}. Skipping this asset.")
             traceback.print_exc()
             continue

    # --- Final Commit ---
    new_portfolio.total_value = total_value # Recalculate total value based on processed valid entries


    try:
        db.session.commit()
        print(f"Portfolio '{new_portfolio.portfolio_name}' (ID: {new_portfolio.id}) and its assets committed successfully.")
        return jsonify({"message": "Portfolio saved", "portfolio_id": new_portfolio.id}), 201
    except Exception as commit_err:
        db.session.rollback()
        print(f"CRITICAL ERROR during final commit for portfolio '{new_portfolio.portfolio_name}': {commit_err}")
        traceback.print_exc()
        return jsonify({"error": "Database error saving portfolio"}), 500

# Route to handle updating an EXISTING portfolio (manual entry form submit)
@portfolio_bp.route('/portfolios/<int:portfolio_id>', methods=['PUT', 'POST'])
@login_required # <--- ADDED Flask-Login decorator to require login
def update_portfolio(portfolio_id):
    """
    Handles the update of an existing portfolio with assets from a manual form submission.
    Expects JSON payload with 'portfolioName' and 'portfolioData' (list of asset entries).
    Deletes old PortfolioAsset records and saves new ones (with determined Asset type if new, and purchase date).
    """
    # The @login_required decorator handles authentication
    # Access user ID via current_user from Flask-Login
    user_id = current_user.id

    data = request.get_json()
    portfolio_name = data.get('portfolioName')
    portfolio_data = data.get('portfolioData', [])

    portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=user_id).first()
    if not portfolio:
        print(f"Update portfolio failed: Portfolio ID {portfolio_id} not found or unauthorized for user {user_id}")
        return jsonify({"error": "Portfolio not found"}), 404

    print(f"Attempting to update portfolio ID {portfolio_id} for user {user_id}. Name: '{portfolio_name}'. Data entries received: {len(portfolio_data)}")

    if not portfolio_name:
        print(f"Update portfolio failed: No portfolio name provided for ID {portfolio_id}")
        return jsonify({"error": "Portfolio name is required"}), 400

    if not isinstance(portfolio_data, list):
         print(f"Update portfolio failed: portfolioData is not a list for ID {portfolio_id}. Received type: {type(portfolio_data)}")
         return jsonify({"error": "Invalid data format for portfolio assets"}), 400


    # Update name early
    portfolio.portfolio_name = portfolio_name
    print(f"Updated portfolio ID {portfolio_id} name to '{portfolio_name}' in session.")


    # --- Process and Validate incoming asset data for update ---
    total_value = 0.0
    valid_portfolio_entries_with_date = []

    for entry in portfolio_data:
        if not isinstance(entry, dict):
             print(f"Skipping invalid entry (not a dict) in update data: {entry}")
             continue

        ticker = entry.get('ticker')
        amount_str = entry.get('amount')
        purchase_date_str = entry.get('purchase_date') # <-- Get the purchase_date string

        if not ticker or amount_str is None:
            print(f"Skipping invalid entry (missing ticker or amount) in update data: {entry}")
            continue

        try:
            amount = float(amount_str)
            if amount < 0:
                 print(f"Skipping entry with negative amount in update data: {entry}")
                 continue

        except ValueError:
            print(f"Skipping entry with invalid amount format (could not convert to float) in update data: {entry}")
            continue

        # --- Parse Purchase Date String ---
        purchase_date_obj = None # Initialize parsed date to None
        if purchase_date_str: # Check if the date string is provided and not empty
             try:
                  # Attempt to parse the date string. Assuming %Y-%m-%d format from HTML date input.
                  purchase_date_obj = datetime.strptime(purchase_date_str, '%Y-%m-%d').date() # .date() gets just the date part
             except ValueError:
                  # If parsing fails (invalid format), log a warning and keep purchase_date_obj as None
                  print(f"Warning: Invalid date format received for ticker {ticker} during update: '{purchase_date_str}'. Expected %Y-%m-%d. Storing as None.")


        # Store the successfully validated and parsed entry (including the date object or None)
        valid_portfolio_entries_with_date.append({
            'ticker': ticker.strip().upper(), # Store ticker normalized
            'amount': amount,
            'purchase_date': purchase_date_obj # <-- Store the parsed date object (or None)
        })

        total_value += amount # Add valid amount to total value


    # Decide what to do if no valid data is received for update
    # If valid_portfolio_entries_with_date is empty, it means all assets were removed or invalid
    if not valid_portfolio_entries_with_date and portfolio_data:
        # User sent data, but none was valid. Return an error.
        print(f"Update portfolio failed: No valid assets with non-negative amounts were provided for ID {portfolio_id}. Total value: {total_value}")
        # Rollback name change and any other session changes before returning error
        db.session.rollback()
        return jsonify({"error": "No valid assets with non-negative amounts were provided for update"}), 400
    # If valid_portfolio_entries_with_date is empty because portfolio_data was empty, it means empty the portfolio.


    # --- Clear old assets associated with this portfolio ---
    # This should be done within the transaction before adding new ones
    try:
        print(f"Deleting old PortfolioAssets for portfolio ID {portfolio_id}...")
        # Using delete with synchronize_session='fetch' is often safer with relationships
        num_deleted = PortfolioAsset.query.filter_by(portfolio_id=portfolio_id).delete(synchronize_session='fetch')
        print(f"Deleted {num_deleted} old PortfolioAssets.")
        # Flush the delete operation to ensure it's processed before adding new ones
        db.session.flush()
        print("Old PortfolioAssets deleted and session flushed.")
    except Exception as delete_err:
         # This is a critical failure for an update
         print(f"CRITICAL ERROR deleting old PortfolioAssets for portfolio ID {portfolio_id}: {delete_err}")
         traceback.print_exc()
         # Rollback the entire transaction, including the name change
         db.session.rollback()
         return jsonify({"error": "Database error clearing old assets for update"}), 500


    # --- Add new PortfolioAsset entries from the validated data, including the purchase date and Asset type ---
    for entry in valid_portfolio_entries_with_date:
         try:
             ticker = entry['ticker'] # Already normalized and uppercase
             amount = entry['amount'] # Already float
             purchase_date_obj = entry['purchase_date'] # This is the datetime.date object or None

             # --- Asset Finding/Creation ---
             # Find the Asset record by normalized symbol and user_id
             asset = Asset.query.filter_by(symbol=ticker, user_id=user_id).first()
             if not asset:
                 print(f"Asset '{ticker}' not found for user {user_id}. Creating new Asset.")

                 # --- Fetch full details using the helper function ---
                 # Ensure fetch_and_map_asset_details is imported
                 # from ..market_fetcher import fetch_and_map_asset_details # Example import - already imported

                 asset_full_details = fetch_and_map_asset_details(ticker)

                 # --- Use details from the helper function to create the Asset record ---
                 determined_asset_type = asset_full_details.get('type', 'stock')
                 determined_company_name = asset_full_details.get('name', f"{ticker} Company")

                 asset = Asset(symbol=ticker, asset_type=determined_asset_type, user_id=user_id, company_name=determined_company_name)
                 db.session.add(asset)

                 # Flush the asset addition to ensure asset.id is set for the foreign key reference
                 try:
                     db.session.flush()
                     print(f"Created new Asset: {asset.symbol} (ID: {asset.id}, Type: {asset.asset_type}, Name: {asset.company_name}) for user {user_id}")
                 except Exception as asset_flush_err:
                      print(f"Error flushing new Asset from CSV {ticker}: {asset_flush_err}. Skipping this asset entry.")
                      traceback.print_exc()
                      db.session.rollback()
                      continue # Skip creating PortfolioAsset for this entry


             # --- PortfolioAsset Creation ---
             if asset and asset.id:
                 allocation_pct = (amount / total_value) * 100 if total_value > 0 else 0.0

                 portfolio_asset = PortfolioAsset(
                     portfolio_id=portfolio_id, # Link to the existing portfolio ID
                     asset_id=asset.id, # Link to the Asset ID (found or newly created)
                     dollar_amount=amount,
                     allocation_pct=allocation_pct,
                     purchase_date=purchase_date_obj # <-- Assign the parsed date object (or None)
                 )
                 db.session.add(portfolio_asset)
                 print(f"Added new PortfolioAsset for {ticker} ({amount}, date: {purchase_date_obj}, Asset Type: {asset.asset_type}) to session for portfolio ID {portfolio_id} during update. Allocation: {allocation_pct:.2f}%")

         except Exception as e:
             print(f"Unexpected error processing portfolio entry during update {entry}: {e}. Skipping this asset.")
             traceback.print_exc()
             continue


    # --- Final Commit ---
    portfolio.total_value = total_value # Update total value based on the new set of holdings

    try:
        db.session.commit()
        print(f"Portfolio '{portfolio.portfolio_name}' (ID: {portfolio_id}) updated and its assets committed successfully.")
        return jsonify({"message": "Portfolio updated"}), 200
    except Exception as commit_err:
        db.session.rollback()
        print(f"CRITICAL ERROR during final commit for portfolio '{portfolio.portfolio_name}' (update): {commit_err}")
        traceback.print_exc()
        return jsonify({"error": "Database error during update"}), 500

# Route to handle CSV upload for a NEW portfolio
@portfolio_bp.route('/upload', methods=['POST'])
@login_required # <--- ADDED Flask-Login decorator to require login
def upload_csv():
    """
    Handles the creation of a new portfolio by uploading a CSV file.
    Expects form-data with 'portfolioName' and 'file' (CSV).
    CSV should have 'Symbol', an amount column ('DollarAmount' or 'Balance'), and optionally 'PurchaseDate'.
    Saves Portfolio, Asset (if new, with determined type), and PortfolioAsset records (with purchase date).
    """
    # The @login_required decorator handles authentication
    # Access user ID via current_user from Flask-Login
    user_id = current_user.id
    portfolio_name = request.form.get('portfolioName')
    file = request.files.get('file')

    print(f"Attempting CSV upload for user {user_id}. Name: '{portfolio_name}'. File: {file.filename if file else 'None'}")

    if not file or not portfolio_name:
        print("CSV upload failed: Missing file or portfolio name.")
        return jsonify({"error": "Missing file or portfolio name"}), 400

    if not file.filename.lower().endswith('.csv'):
        print(f"CSV upload failed: Invalid file type ({file.filename}).")
        return jsonify({"error": "Invalid file type. Please upload a CSV file."}), 400

    try:
        # Use StringIO to read the file content as a string, then parse with pandas
        from io import StringIO # Ensure StringIO is imported

        # Read file content and handle decoding errors
        try:
            file.seek(0) # Ensure we read from the beginning of the file stream
            # Attempt to decode as UTF-8 first, fallback to 'latin-1' or 'cp1252' if common errors
            file_content = file.read().decode('utf-8')
        except UnicodeDecodeError:
             try:
                 file.seek(0) # Reset position before trying another decode
                 file_content = file.read().decode('latin-1') # Or 'cp1252'
             except Exception as decode_err:
                  print(f"Error decoding CSV file with fallback: {decode_err}")
                  return jsonify({"error": f"Error decoding CSV file. Ensure it's UTF-8. {decode_err}"}), 400
        except Exception as decode_err:
             print(f"Error decoding CSV file: {decode_err}")
             return jsonify({"error": f"Error decoding CSV file. Ensure it's a valid text file. {decode_err}"}), 400


        # Attempt to read CSV, handle potential parsing errors
        try:
            # Use comma as delimiter, handle potential extra whitespace
            df = pd.read_csv(StringIO(file_content)).dropna(how='all') # Drop entirely empty rows
            # Strip whitespace from column names
            df.columns = df.columns.str.strip()
            print(f"Successfully read CSV file. Columns: {df.columns.tolist()}. Rows: {len(df)}")
        except Exception as csv_read_err:
             print(f"Error reading CSV file: {csv_read_err}")
             return jsonify({"error": f"Error reading CSV file. Please check format and delimiter. {csv_read_err}"}), 400

        # --- Define expected columns including PurchaseDate ---
        expected_symbol_col = 'Symbol'
        amount_cols = ['DollarAmount', 'Balance', 'Weight'] # Prioritize DollarAmount > Balance > Weight
        expected_date_col = 'PurchaseDate' # Expected purchase date column name

        amount_col = None
        for col in amount_cols:
            if col in df.columns:
                amount_col = col
                break

        # Check for required columns
        if expected_symbol_col not in df.columns or amount_col is None:
            missing_cols = [f"'{expected_symbol_col}'"] + [f"'{col}'" for col in amount_cols]
            print(f"CSV upload failed: Missing required columns. Expected one of {', '.join(missing_cols)}, found {df.columns.tolist()}.")
            return jsonify({"error": f"CSV must contain a '{expected_symbol_col}' column and one of {', '.join(amount_cols)} columns."}), 400

        # Check if the optional PurchaseDate column exists
        date_col_exists = expected_date_col in df.columns
        if not date_col_exists:
            print(f"Warning: '{expected_date_col}' column not found in CSV. Purchase dates will not be saved.")


        processed_entries = []
        # Process rows with validation and date parsing
        for index, row in df.iterrows():
            try:
                # Get symbol safely and ensure it's not empty
                symbol_raw = row.get(expected_symbol_col, "")
                if pd.isna(symbol_raw) or not str(symbol_raw).strip():
                    print(f"Warning: Skipping CSV row {index+1} due to empty or missing symbol.")
                    continue
                symbol = str(symbol_raw).strip().upper()

                # Get amount string safely and clean it
                amount_raw = row.get(amount_col, 0)
                # Handle potential NaNs from pandas read_csv for empty amount cells
                if pd.isna(amount_raw): amount_raw = 0

                amount_str = str(amount_raw).replace('$', '').replace(',', '').replace('%', '').strip() # Clean string

                # Convert amount to float and validate
                amount = float(amount_str)

                if amount < 0:
                    print(f"Warning: Skipping CSV row {index+1} ({symbol}) due to negative amount: {amount_raw}")
                    continue

                if amount == 0:
                    print(f"Warning: Skipping CSV row {index+1} ({symbol}) with zero amount.")
                    continue

                # --- Get and Parse Purchase Date from CSV ---
                purchase_date_obj = None
                if date_col_exists: # Only attempt to get date if the column exists
                     date_raw = row.get(expected_date_col)
                     if pd.notna(date_raw) and str(date_raw).strip(): # Check if the cell is not empty or NaN
                         date_str = str(date_raw).strip()
                         try:
                              # Attempt to parse the date string. Try common formats.
                              # pandas to_datetime is flexible, try using it first
                              parsed_date = pd.to_datetime(date_str, errors='coerce') # coerce invalid dates to NaT
                              if pd.notna(parsed_date):
                                   purchase_date_obj = parsed_date.date() # Get Python date object
                              else:
                                   print(f"Warning: CSV row {index+1} ({symbol}): Invalid date format for '{expected_date_col}': '{date_str}'. Storing as None.")

                         except Exception as date_parse_err: # Catch other potential errors during parsing
                              print(f"Warning: CSV row {index+1} ({symbol}): Error parsing date '{date_str}': {date_parse_err}. Storing as None.")


                # Store the processed entry including the parsed date object (will be None if invalid/missing)
                processed_entries.append({
                    'ticker': symbol, # Ticker is already normalized and uppercase
                    'amount': amount,
                    'purchase_date': purchase_date_obj # <-- Include the parsed date object (or None)
                })

            except ValueError: # Catch error during float conversion for amount
                print(f"Warning: Skipping CSV row {index+1} ({row.get(expected_symbol_col, 'N/A')}) due to invalid numeric format in '{amount_col}': {row.get(amount_col, 'N/A')}")
                continue
            except KeyError as e:
                # Should not happen if amount_col is determined, but as a safeguard
                print(f"Error accessing column during row processing '{e}': Skipping row {index+1}.")
                continue
            except Exception as e: # Catch any other unexpected error during row processing
                 print(f"Unexpected error processing CSV row {index+1}: {e}. Skipping row.")
                 traceback.print_exc()
                 continue


        if not processed_entries:
             print(f"CSV upload failed: No valid portfolio entries found after processing file for '{portfolio_name}'.")
             return jsonify({"error": f"No valid portfolio entries found in the CSV after processing. Ensure '{expected_symbol_col}' and a valid amount column are present and rows are not empty."}), 400

        # Calculate total value from the now guaranteed-to-be-dollar-amount entries
        total_value = sum(entry['amount'] for entry in processed_entries)

        if total_value <= 0:
             print(f"Error: Calculated total portfolio value is zero or negative based on CSV data ({total_value}) for '{portfolio_name}'.")
             return jsonify({"error": "Calculated total portfolio value is zero or negative based on CSV data."}), 400


        # --- Create new Portfolio object and add to session ---
        new_portfolio = Portfolio(
            user_id=user_id, # Link to the current_user ID
            portfolio_name=portfolio_name,
            total_value=total_value
        )
        db.session.add(new_portfolio)

        try:
            db.session.flush() # Flush to get the portfolio ID
            print(f"Created new Portfolio object in session from CSV: '{portfolio_name}' with total value {total_value}. ID will be {new_portfolio.id} after commit.")
        except Exception as flush_err:
             db.session.rollback()
             print(f"Error during portfolio flush for CSV upload '{portfolio_name}': {flush_err}")
             traceback.print_exc()
             return jsonify({"error": "Database error preparing portfolio from CSV"}), 500


        # --- Add PortfolioAsset entries from processed data (including date and determined Asset type) ---
        for entry in processed_entries:
             try:
                 ticker = entry['ticker'] # Already normalized and uppercase
                 amount = entry['amount'] # Already float
                 purchase_date_obj = entry['purchase_date'] # This is the datetime.date object or None

                 # --- Asset Finding/Creation ---
                 # Find the Asset record by normalized symbol and user_id
                 asset = Asset.query.filter_by(symbol=ticker, user_id=user_id).first()
                 if not asset:
                     print(f"Asset '{ticker}' not found for user {user_id}. Creating new Asset.")

                     # --- Fetch full details using the helper function ---
                     # Ensure fetch_and_map_asset_details is imported
                     # from ..market_fetcher import fetch_and_map_asset_details # Example import - already imported

                     asset_full_details = fetch_and_map_asset_details(ticker)

                     # --- Use details from the helper function to create the Asset record ---
                     determined_asset_type = asset_full_details.get('type', 'stock')
                     determined_company_name = asset_full_details.get('name', f"{ticker} Company")

                     asset = Asset(symbol=ticker, asset_type=determined_asset_type, user_id=user_id, company_name=determined_company_name)
                     db.session.add(asset)

                     # Flush the asset addition to ensure asset.id is set for the foreign key reference
                     try:
                         db.session.flush()
                         print(f"Created new Asset from CSV: {asset.symbol} (ID: {asset.id}, Type: {asset.asset_type}, Name: {asset.company_name}) for user {user_id}")
                     except Exception as asset_flush_err:
                          print(f"Error flushing new Asset from CSV {ticker}: {asset_flush_err}. Skipping this asset entry.")
                          traceback.print_exc()
                          db.session.rollback() # Rollback the failed asset addition attempt
                          continue # Skip creating PortfolioAsset for this entry


                 # --- PortfolioAsset Creation ---
                 if asset and asset.id:
                     allocation_pct = (amount / total_value) * 100 if total_value > 0 else 0.0

                     portfolio_asset = PortfolioAsset(
                         portfolio_id=new_portfolio.id, # Link to the newly created portfolio ID
                         asset_id=asset.id, # Link to the Asset ID (found or newly created)
                         dollar_amount=amount,
                         allocation_pct=allocation_pct,
                         purchase_date=purchase_date_obj # <-- Assign the parsed date object (or None)
                     )
                     db.session.add(portfolio_asset)
                     print(f"Added PortfolioAsset from CSV for {ticker} ({amount}, date: {purchase_date_obj}, Asset Type: {asset.asset_type}) to session for portfolio ID {new_portfolio.id}. Allocation: {allocation_pct:.2f}%")

             except Exception as e:
                 print(f"Unexpected error processing CSV entry for {ticker}: {e}. Skipping this asset.")
                 traceback.print_exc()
                 continue

        # --- Final Commit ---
        # Recalculate total value from the database holdings just added to ensure accuracy
        # This might be needed if some assets were skipped during processing
        committed_holdings = PortfolioAsset.query.filter_by(portfolio_id=new_portfolio.id).all()
        final_total_value = sum(h.dollar_amount for h in committed_holdings)
        new_portfolio.total_value = final_total_value # Update total value based on saved holdings

        # Recalculate and update allocations based on the final total value
        for h in committed_holdings:
             h.allocation_pct = h.dollar_amount / final_total_value if final_total_value > 0 else 0.0
             db.session.add(h) # Add updated holding to session


        try:
            db.session.commit()
            print(f"Portfolio '{portfolio_name}' (ID: {new_portfolio.id}) from CSV upload committed successfully.")
            # The frontend JS needs to handle the redirect after receiving the 201 response
            return jsonify({"message": "Portfolio uploaded", "portfolio_id": new_portfolio.id}), 201
        except Exception as commit_err:
            db.session.rollback()
            print(f"CRITICAL ERROR during final commit for CSV upload '{portfolio_name}': {commit_err}")
            traceback.print_exc()
            return jsonify({"error": "Database error saving portfolio from CSV"}), 500


    except Exception as e:
        # Catch errors during file reading or initial processing not caught above
        print(f"General error during CSV upload processing for '{portfolio_name}': {e}")
        traceback.print_exc()
        # Rollback any session changes that might have started before the specific error
        db.session.rollback()
        return jsonify({"error": f"An unexpected error occurred during CSV upload: {str(e)}"}), 500

# Route for Portfolio Analysis Selection Page
@portfolio_bp.route('/analysis-selection', methods=['GET'])
@login_required # <--- ADDED Flask-Login decorator to require login
def portfolio_analysis_selection():
    # The @login_required decorator handles authentication
    # Access user ID via current_user from Flask-Login
    user_id = current_user.id
    username = current_user.username # Access username via current_user

    try:
        # Get user's portfolios
        portfolios = Portfolio.query.filter_by(user_id=user_id).all()
        print(f"User {user_id} viewing analysis selection. Found {len(portfolios)} portfolios.")

        # Render template relative to the blueprint's template folder
        return render_template('portfolio_analysis_selection.html',
                               portfolios=portfolios,
                               username=username)

    except Exception as e:
        current_app.logger.error(f"Error fetching portfolios for Analysis Selection page (user {user_id}): {str(e)}")
        traceback.print_exc()
        # Rollback in case of DB error
        db.session.rollback()
        flash('Error loading portfolios. Please try again.', 'danger')
        # Redirect to a safe page
        return redirect(url_for('auth.index')) # Example: Redirect to home or login


# Route for a specific portfolio dashboard view
@portfolio_bp.route('/<int:portfolio_id>/dashboard', methods=['GET'])
@login_required # <--- ADDED Flask-Login decorator to require login
def view_dashboard(portfolio_id):
    # The @login_required decorator handles authentication
    # Access user ID via current_user from Flask-Login
    user_id = current_user.id
    portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=user_id).first()

    if not portfolio:
        print(f"Dashboard view failed: Portfolio ID {portfolio_id} not found or not authorized for user {user_id}")
        # Use flash message and redirect for user-facing error
        flash('Portfolio not found or not authorized.', 'danger')
        return redirect(url_for('portfolio_api.saved_portfolios')) # Redirect to saved list if not found

    username = current_user.username # Access username via current_user
    print(f"User {user_id} viewing dashboard for portfolio ID {portfolio_id}.")
    # Render template relative to the blueprint's template folder
    return render_template('portfolio_analysis.html', portfolio=portfolio, username=username)

# API Route to get data for the dashboard
@portfolio_bp.route('/<int:portfolio_id>/data', methods=['GET'])
@login_required # <--- ADDED Flask-Login decorator to require login
def get_portfolio_data(portfolio_id):
    """
    Fetches live/recent market data from the DATABASE for the dashboard display.
    Determines date range based on earliest purchase date or a default (1 year).
    Processes data for interpolation and returns JSON response.
    """
    # The @login_required decorator handles authentication
    # Access user ID via current_user from Flask-Login
    user_id = current_user.id
    portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=user_id).first()

    if not portfolio:
        print(f"Dashboard data fetch failed: Portfolio ID {portfolio_id} not found or not authorized for user {user_id}")
        return jsonify({"error": "Portfolio not found or not authorized"}), 404

    try:
        print(f"Fetching dashboard data from DATABASE for portfolio ID {portfolio_id} for user {user_id}.")

        holdings_data = [] # List to store holding details for the response
        tickers_to_fetch_normalized = set() # Set to store unique, normalized ticker symbols
        earliest_purchase_date = None # Variable to track the earliest purchase date

        # Iterate through portfolio holdings to collect tickers and find earliest purchase date
        for holding in portfolio.holdings:
            # Basic validation for holdings
            if not holding.asset or holding.dollar_amount is None or not isinstance(holding.dollar_amount, (int, float)) or holding.dollar_amount < 0:
                 print(f"Warning: Skipping invalid holding ID {holding.id} for portfolio {portfolio_id}.")
                 continue

            # Prepare basic holding entry for the response
            holding_entry = {
                 "ticker": holding.asset.symbol, # Use the symbol from the linked Asset
                 "Name": holding.asset.company_name or h.asset.symbol,
                 "Category": holding.asset.asset_type or "Unknown",
                 "Sector": holding.asset.sector,
                 'Weight': (float(holding.allocation_pct) / 100.0) if holding.allocation_pct is not None else 0.0,
                 'DollarAmount': float(holding.dollar_amount),
                 'PurchaseDate': holding.purchase_date.strftime('%Y-%m-%d') if holding.purchase_date else None, # Format date
                 'start_date': "", # Placeholder (can be removed if not used by frontend)
                 'end_date': "" # Placeholder (can be removed if not used by frontend)
            }
            
            holdings_data.append(holding_entry)

            tickers_to_fetch_normalized.add(holding.asset.symbol.upper())

            # Update earliest_purchase_date if the current holding has an earlier purchase date
            if holding.purchase_date:
                 if earliest_purchase_date is None or holding.purchase_date < earliest_purchase_date:
                      earliest_purchase_date = holding.purchase_date

        # Convert the set of unique tickers to a sorted list for consistent processing order
        tickers_to_fetch_normalized = sorted(list(tickers_to_fetch_normalized))
        print(f"Unique normalized tickers to fetch data from DB for: {tickers_to_fetch_normalized}")

        # --- Determine the overall historical date range for data fetching from DB ---
        # Use the earliest purchase date if available, otherwise default to 1 year ago
        # The get_historical_data_for_asset function defaults to 1 year if start_date is None.
        start_date_for_db_fetch = earliest_purchase_date # Use earliest purchase date (datetime.date)
        end_date_for_db_fetch = datetime.utcnow() # End date is now (datetime)


        print(f"Fetching market data from DATABASE for range: {start_date_for_db_fetch.strftime('%Y-%m-%d') if start_date_for_db_fetch else 'Default (1 Year)'} to {end_date_for_db_fetch.date().strftime('%Y-%m-%d')}")

        prices_from_db = {} # Dictionary to store DataFrames fetched from the DB {ticker: DataFrame}
        all_dates_set = set() # Set to collect all unique dates from fetched dataframes (as datetime objects)

        # Fetch data for each ticker from the DATABASE
        for ticker in tickers_to_fetch_normalized:
             # Find the Asset object for this ticker (it must exist if it's in portfolio.holdings)
             asset = Asset.query.filter_by(symbol=ticker, user_id=user_id).first()

             if asset:
                  # Fetch historical data from the database for this asset within the calculation date range
                  # get_historical_data_for_asset already filters by asset_id and date range.
                  # It takes start_date (datetime.date or None) and end_date (datetime or None).
                  df_from_db = get_historical_data_for_asset(asset.id, start_date=start_date_for_db_fetch, end_date=end_date_for_db_fetch)

                  if df_from_db is not None and isinstance(df_from_db, pd.DataFrame) and not df_from_db.empty and df_from_db.index.name == 'date' and 'price' in df_from_db.columns:
                       # Store the price Series (DataFrame with date index and 'price' column)
                       prices_from_db[ticker] = df_from_db['price'] # Store the price Series for this ticker
                       # Collect dates from the fetched DataFrame's index (assuming it's datetime index)
                       for date in df_from_db.index:
                            all_dates_set.add(date) # Add date as datetime object
                       print(f"  Successfully fetched DataFrame from DB for {ticker}.")
                  else:
                       print(f"No historical data found in DB for ticker {ticker} for dashboard range.")


        # --- Prepare final sorted list of dates (as datetime objects) ---
        # If no dates were collected from any ticker, generate a default date range (1 year)
        if not all_dates_set:
             print("No historical dates collected from any ticker from DB. Generating date range from default (1 year ago) to now.")
             # Generate dates between default 1yr ago and now (inclusive) with daily frequency
             default_start_date = datetime.utcnow() - timedelta(days=365)
             dates = pd.date_range(start=default_start_date, end=datetime.utcnow(), freq='D').tolist() # List of datetime objects
             # Convert to date objects for interpolation key if needed
             # dates = [d.date() for d in dates] # If interpolation key is date object
        else:
            # Convert the set of unique dates (as datetime objects) to a sorted list
            dates = sorted(list(all_dates_set))
            print(f"Collected {len(dates)} unique dates from DB across all tickers.")
            if dates:
                 print(f"Full date range from {dates[0].date()} to {dates[-1].date()}.")
            else:
                 print("Date range is empty after sorting unique dates.")


        # --- Interpolate missing prices for each ticker across the full date range ---
        # This ensures all tickers have a price for every date in the combined date range for the dashboard plot

        interpolated_prices = {} # Dictionary {ticker: [price1, price2, ...]}
        # Convert sorted list of dates (datetime objects) to a pandas Index for reindexing
        full_date_index = pd.Index(dates, name='date')


        for ticker in tickers_to_fetch_normalized:
             if ticker in prices_from_db:
                 price_series = prices_from_db[ticker] # Get the price Series (date index, price values)
                 # Reindex the individual Series to the full combined date index
                 # This will introduce NaNs for missing dates
                 reindexed_series = price_series.reindex(full_date_index)

                 interpolated_series = reindexed_series.ffill()

                 interpolated_series = interpolated_series.bfill()

                 # Decide how to handle tickers that had NO data in DB at all for the range
                 if interpolated_series.isna().all():
                      print(f"Warning: After interpolation, ticker {ticker} has no valid prices for the date range. Skipping ticker from dashboard price data.")
                      # This ticker will not be included in the final 'prices' dictionary
                 else:
                      # Convert the interpolated Series to a list of prices
                      interpolated_prices[ticker] = interpolated_series.tolist()

             else:
                 # If the ticker wasn't found in prices_from_db at all, use a default price (like 100) for all dates
                 print(f"No data fetched from DB for {ticker}. Using default prices (100) for all dates in dashboard.")
                 # Create a list of default prices matching the length of the full date range
                 interpolated_prices[ticker] = [100.0] * len(dates) # Use default price for the full combined date range


        # Check if any tickers have interpolated data
        if not interpolated_prices:
             print("No price data available for dashboard after interpolation.")
             # Handle this case
             return jsonify({"error": "No price data available for dashboard after processing."}), 404


        # Convert dates (datetime objects) to 'YYYY-MM-DD' strings for the JSON response
        date_strings = [d.strftime('%Y-%m-%d') for d in dates]


        # Return the data structure expected by the dashboard frontend
        response_data = {
             'portfolio_name': portfolio.portfolio_name,
             'holdings': holdings_data, # This list should already be populated with basic holding info
             'prices': interpolated_prices, # Dictionary {ticker: [interpolated_price1, ...]}
             'dates': date_strings, # List of date strings ('YYYY-MM-DD') matching prices lists
             # You might want to add a list of tickers that were successfully included in prices
             'tickers_with_data': list(interpolated_prices.keys())
        }

        print("Returning dashboard data.")
        return jsonify(response_data), 200


    except Exception as e:
        import traceback
        print(f"CRITICAL ERROR in get_portfolio_data for portfolio ID {portfolio_id} (user {user_id}): {str(e)}")
        print(traceback.format_exc())
        db.session.rollback()
        return jsonify({"error": "An internal error occurred while fetching dashboard data."}), 500

# Route to handle ticker validation
@portfolio_bp.route('/validate-ticker', methods=['GET'])
# @login_required # Decide if ticker search requires login (often public)
def validate_ticker():
    """
    Search for ticker symbols using Alpha Vantage and yfinance fallbacks for validation.
    This route is typically public for use in forms before login.
    Query Parameter:
      - ticker: The ticker symbol to validate.
    Returns validation status and basic info if found.
    """
    ticker = request.args.get('ticker', '')
    if not ticker or len(ticker) < 1:
        return jsonify({"valid": False, "message": "Ticker symbol is required"}), 200

    ticker = ticker.strip().upper()
    print(f"Validating ticker: {ticker}")

    try:
        asset_details = fetch_and_map_asset_details(ticker)

        if asset_details and asset_details.get('symbol'): # Check if the helper returned a valid structure with a symbol
             # The helper returns a default dict even on failure, check determined type
             determined_type = asset_details.get('type')
             # Consider it valid for validation if it's a known type or fetch_and_map_asset_details found something
             # Refine this validity check based on what constitutes a 'valid' ticker for your app
             # For example, maybe only allow 'stock', 'etf', 'crypto', 'bond'
             is_known_type = determined_type in ['stock', 'etf', 'crypto', 'bond']
             
             # Also check if the helper managed to get a name different from just the symbol, as a sign it found details
             found_meaningful_details = asset_details.get('name') != ticker # Check if name is more than just the symbol

             # Consider it valid if it's a known type OR if it found meaningful details
             if is_known_type or found_meaningful_details:
                  print(f"Ticker {ticker} validated successfully via fetch_and_map_asset_details. Type: {determined_type}")
                  return jsonify({
                      "valid": True,
                      "message": f"Ticker '{asset_details.get('symbol', ticker)}' found.",
                      "info": {
                          "symbol": asset_details.get('symbol', ticker),
                          "name": asset_details.get('name', ticker),
                          "type": determined_type,
                          # Include other relevant details if fetch_and_map_asset_details provides them
                          "exchange": asset_details.get('exchange'),
                          "currency": asset_details.get('currency'),
                          # Add financial metrics if available and desired for display
                          # "expense_ratio": asset_details.get('expense_ratio'),
                          # "yield": asset_details.get('yield'),
                          # "pe": asset_details.get('pe')
                      }
                  }), 200
             else:
                 # Helper returned a structure, but couldn't determine a known type or get meaningful details
                 print(f"Ticker {ticker} found by fetch_and_map_asset_details, but not a standard type or missing details.")
                 return jsonify({"valid": False, "message": f"Ticker '{ticker}' found, but not a standard type or missing details."}), 200

        else:
             # Helper returned None or an empty-like structure indicating it couldn't find the ticker at all
             print(f"Ticker {ticker} not found by fetch_and_map_asset_details.")
             return jsonify({
                 "valid": False,
                 "message": f"Ticker symbol '{ticker}' not found."
             }), 200 # Return 200 with valid=False for a client-side validation failure


    except Exception as e:
        # Catch any unexpected errors during validation (e.g., API errors not handled in fetch_and_map_asset_details)
        print(f"Unexpected error during ticker validation for '{ticker}': {str(e)}")
        traceback.print_exc()
        return jsonify({"valid": False, "message": "An internal error occurred during validation."}), 500

# Route to handle ticker search (autocomplete suggestions)
@portfolio_bp.route('/search-ticker', methods=['GET'])
def search_ticker():
    """
    Search for ticker symbols using Alpha Vantage for autocomplete suggestions.
    This route is typically public for use in forms before login.
    Query Parameter:
      - keyword: The search term with at least 2 characters
    Returns a list of matching symbols and names.
    """
    keyword = request.args.get('keyword', '')
    if not keyword or len(keyword) < 2:
        return jsonify([])

    print(f"Searching ticker keyword: {keyword}")

    try:
        alpha_vantage_key = os.environ.get('ALPHA_VANTAGE_API_KEY')

        # Prefer Alpha Vantage search as it's designed for this
        if alpha_vantage_key:
            url = f"https://www.alphavantage.co/query?function=SYMBOL_SEARCH&keywords={keyword}&apikey={alpha_vantage_key}"
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status() # Raise HTTPError for bad responses (like 429)
                data = response.json()
                suggestions = []
                if 'bestMatches' in data and data['bestMatches']:
                    # Filter results to include primarily Equity, ETF, Fund types
                    allowed_types = ['Equity', 'ETF', 'Fund', 'Cryptocurrency'] # Include Crypto for search suggestions
                    for match in data['bestMatches'][:15]: # Limit results to top 15 suggestions
                         symbol = match.get('1. symbol')
                         name = match.get('2. name')
                         type = match.get('3. type')
                         if symbol and name and type in allowed_types: # Filter by allowed types
                            suggestions.append({
                                 'symbol': symbol,
                                 'name': f"{name} ({symbol})", # Combine name and symbol for display
                                 'type': type # Include type in suggestion data
                            })
                    print(f"Alpha Vantage search for '{keyword}' found {len(suggestions)} relevant matches.")
                    return jsonify(suggestions), 200

                else:
                    print(f"Alpha Vantage search for '{keyword}' found no matches.")
                    return jsonify([]), 200 # Return empty list if no matches


            except requests.exceptions.RequestException as req_err:
                print(f"Alpha Vantage API Request error during ticker search for '{keyword}': {req_err}")
                # traceback.print_exc()
                if isinstance(req_err, requests.exceptions.HTTPError) and req_err.response.status_code == 429:
                    return jsonify({"error": "Rate limit exceeded for ticker search API. Please try again later."}), 429
                else:
                    # For other request errors from AV, return empty list but log
                    print(f"Other request error from AV during search: {req_err}. Returning empty results.")
                    return jsonify([]), 500

        print(f"No Alpha Vantage key available or search failed. Returning empty results for '{keyword}'.")
        return jsonify([]), 200

    except Exception as e:
        print(f"Unexpected error during ticker search for '{keyword}': {str(e)}")
        traceback.print_exc()
        return jsonify([]), 500

# Route to download portfolio data
@portfolio_bp.route('/<int:portfolio_id>/download', methods=['GET'])
@login_required # <--- ADDED Flask-Login decorator to require login
def download_portfolio(portfolio_id):
    """
    Downloads portfolio data for the logged-in user in CSV or JSON format.
    """
    user_id = current_user.id

    portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=user_id).first()

    if not portfolio:
        print(f"Download portfolio failed: Portfolio ID {portfolio_id} not found or unauthorized for user {user_id}")
        flash('Portfolio not found or not authorized.', 'danger')
        return redirect(url_for('portfolio_api.saved_portfolios'))

    try:
        today = datetime.now().strftime('%Y-%m-%d')
        print(f"Preparing download for portfolio ID {portfolio_id} for user {user_id}...")

        # Get current prices for each asset
        prices = {}
        # Collect tickers from holdings that have a valid asset
        tickers_to_fetch = [h.asset.symbol for h in portfolio.holdings if h.asset]
        print("Attempting to get latest prices for download data...")

        # Fetch Asset objects needed for DB lookup
        asset_map_by_symbol = {asset.symbol.upper(): asset for asset in Asset.query.filter(Asset.symbol.in_(tickers_to_fetch), Asset.user_id == user_id).all()}


        for ticker in tickers_to_fetch:
            ticker_upper = ticker.upper()
            asset = asset_map_by_symbol.get(ticker_upper)

            if asset:
                # Try getting latest price from DB first
                latest_price_entry = MarketData.query.filter_by(asset_id=asset.id).order_by(MarketData.date.desc()).first()
                if latest_price_entry:
                    prices[ticker] = latest_price_entry.price
                    print(f"Got latest DB price for {ticker}: {prices[ticker]}")
                    continue # Move to the next ticker if DB price found

                # Fallback to API fetching if not in DB
                print(f"DB price not found for {ticker} or asset not found. Attempting to fetch latest via API.")
                price_scalar = None # Variable to hold the scalar price from API fallbacks

                # Try Yahoo Finance for latest price (period="current" returns scalar or DF)
                price_or_df = fetch_yahoo_data(ticker, period="current")

                if price_or_df is None:
                    # Try Alpha Vantage GLOBAL_QUOTE
                    price_scalar = fetch_alpha_vantage_data(ticker, function="GLOBAL_QUOTE")
                elif isinstance(price_or_df, pd.DataFrame) and not price_or_df.empty:
                    if 'Close' in price_or_df.columns:
                        price_scalar = price_or_df['Close'].iloc[-1]
                    else:
                        current_app.logger.warning(f"'Close' column missing in Yahoo latest DF for {ticker}.")
                elif isinstance(price_or_df, (int, float)) and not pd.isna(price_or_df):
                    price_scalar = price_or_df

                # If price_scalar is still None, try CoinGecko simple price if it's crypto
                if price_scalar is None and asset and asset.asset_type.lower() == "crypto":
                     cg_map = _get_coingecko_id_map() # Get map
                     if cg_map and (cg_id := cg_map.get(asset.symbol.upper())):
                          price_scalar = fetch_coingecko_simple_price(cg_id, vs_currency="usd")
                          if price_scalar is not None:
                              print(f"Got latest price for crypto {ticker} = ${price_scalar:.2f} from CoinGecko simple-price (fallback)")
                          else:
                              current_app.logger.warning(f"CoinGecko simple-price failed for {ticker} (ID: {cg_id}).")


                if price_scalar is not None:
                    prices[ticker] = float(price_scalar)
                    print(f"Fetched latest API price for {ticker}: {prices[ticker]}")
                    if asset and not latest_price_entry: 
                        save_to_market_data(asset.id, price_scalar, datetime.utcnow())
                else:
                    prices[ticker] = 'N/A'
                    print(f"Warning: Could not fetch latest price for {ticker} via API after fallbacks. Setting to 'N/A'.")

            else:
                print(f"Asset not found in DB for symbol {ticker} for user {user_id}. Cannot fetch price. Setting to 'N/A'.")
                prices[ticker] = 'N/A' # Asset not in DB, cannot fetch price
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error saving latest prices during download: {e}")


        format_type = request.args.get('format', 'csv').lower()

        if format_type == 'json':
            output_data = {
                "portfolio_name": portfolio.portfolio_name,
                "date": today,
                "holdings": []
            }
            for holding in portfolio.holdings:
                 if not holding.asset: continue

                 ticker = holding.asset.symbol
                 dollar_allocation = float(holding.dollar_amount) if holding.dollar_amount is not None else 0.0
                 allocation_pct = float(holding.allocation_pct) if holding.allocation_pct is not None else 0.0
                 price = prices.get(ticker, 'N/A')
                 
                 try:
                     formatted_price = float(price) if price != 'N/A' else None
                 except (ValueError, TypeError):
                      formatted_price = None

                 output_data["holdings"].append({
                     "symbol": ticker,
                     "dollar_allocation": dollar_allocation,
                     "allocation_percent": allocation_pct,
                     "purchase_date": holding.purchase_date.strftime('%Y-%m-%d') if holding.purchase_date else None,
                     "current_price": formatted_price
                 })
            print(f"Prepared JSON data for portfolio ID {portfolio_id}.")
            return jsonify(output_data), 200

        else: # Default to CSV
             csv_content = "Symbol,Dollar Allocation,Allocation Percentage,Purchase Date,Current Price\n" # Added Purchase Date header
             for holding in portfolio.holdings:
                 if not holding.asset: continue

                 ticker = holding.asset.symbol
                 dollar_allocation = float(holding.dollar_amount) if holding.dollar_amount is not None else 0.0
                 formatted_allocation = f"${dollar_allocation:,.2f}"

                 allocation_pct = float(holding.allocation_pct) if holding.allocation_pct is not None else 0.0
                 formatted_pct = f"{allocation_pct:.2f}%"

                 purchase_date_str = holding.purchase_date.strftime('%Y-%m-%d') if holding.purchase_date else '' # Get formatted date or empty string

                 price = prices.get(ticker, 'N/A')
                 formatted_price = f"${price:,.2f}" if isinstance(price, (int, float)) else str(price)

                 # Use double quotes around fields that might contain commas or dollar signs
                 csv_content += f'"{ticker}","{formatted_allocation}","{formatted_pct}","{purchase_date_str}","{formatted_price}"\n' # Added purchase_date_str

             filename = f"portfolio_{portfolio.portfolio_name.replace(' ', '_')}_{today}.csv"
             print(f"Prepared CSV data for portfolio ID {portfolio_id}. Filename: {filename}")

             from flask import Response # Import Response class
             response = Response(csv_content, mimetype='text/csv')
             response.headers.set('Content-Disposition', 'attachment', filename=f'"{filename}"')
             return response

    except Exception as e:
        import traceback
        print(f"CRITICAL ERROR in download_portfolio for ID {portfolio_id} (user {user_id}): {str(e)}")
        print(traceback.format_exc())
        db.session.rollback()
        return jsonify({"error": "An internal error occurred while preparing portfolio data for download."}), 500

@portfolio_bp.route('/portfolios/<int:portfolio_id>', methods=['DELETE', 'POST'])
@login_required # <--- ADDED Flask-Login decorator to require login
def delete_portfolio(portfolio_id):
    """
    Deletes a portfolio for the logged-in user.
    Accepts DELETE or POST methods for flexibility.
    """
    user_id = current_user.id

    try:
        # Find the portfolio belonging to the logged-in user
        portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=user_id).first()

        if not portfolio:
            print(f"Delete portfolio failed: Portfolio ID {portfolio_id} not found or not authorized for user {user_id}")
            return jsonify({"error": "Portfolio not found"}), 404

        print(f"Deleting portfolio ID {portfolio_id} for user {user_id}...")
        db.session.delete(portfolio)

        db.session.commit()
        print(f"Portfolio ID {portfolio_id} deleted successfully.")

        return jsonify({"message": "Portfolio deleted successfully"}), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Database error during portfolio deletion for ID {portfolio_id} (user {user_id}): {e}")
        traceback.print_exc()
        return jsonify({"error": "An internal database error occurred during deletion."}), 500

@portfolio_bp.route('/api/portfolios', methods=['GET'])
@login_required # <--- ADDED Flask-Login decorator to require login
def get_portfolios_json():
    """
    Fetches the list of portfolios for the logged-in user and returns them as JSON.
    Used by frontend JS for dropdowns, etc.
    """
    user_id = current_user.id

    try:
        portfolios = Portfolio.query.filter_by(user_id=user_id).all()

        portfolio_list = []
        for portfolio in portfolios:
            portfolio_list.append({
                'id': portfolio.id,
                'portfolio_name': portfolio.portfolio_name
            })

        print(f"API: Returning {len(portfolio_list)} portfolios as JSON for user {user_id}.")
        return jsonify(portfolio_list), 200

    except Exception as e:
        current_app.logger.error(f"API Error in get_portfolios_json for user {user_id}: {str(e)}")
        traceback.print_exc()
        db.session.rollback()
        return jsonify({"error": "An internal error occurred while fetching portfolios."}), 500
    
@portfolio_bp.route('/api/update-profile/<int:portfolio_id>', methods=['POST'])
@login_required
def update_portfolio_profile(portfolio_id):
    """
    API endpoint to trigger portfolio recalculation after a transaction.
    This recalculates the portfolio's total_value and allocation percentages.
    """
    user_id = current_user.id

    portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=user_id).first()

    if not portfolio:
        return jsonify({"error": "Portfolio not found or not authorized"}), 404

    try:
        # Fetch all holdings for the portfolio
        holdings = PortfolioAsset.query.filter_by(portfolio_id=portfolio.id).all()

        # Recalculate total value
        total_value = sum(holding.dollar_amount for holding in holdings if holding.dollar_amount is not None)

        if total_value <= 0:
            total_value = 0.0  # Avoid division by zero

        portfolio.total_value = total_value

        # Update each holding's allocation percentage
        for holding in holdings:
            if holding.dollar_amount is not None and total_value > 0:
                holding.allocation_pct = (holding.dollar_amount / total_value)
            else:
                holding.allocation_pct = 0.0

            db.session.add(holding)  # Mark holding as dirty (even if unchanged)

        db.session.add(portfolio)
        db.session.commit()

        return jsonify({"message": "Portfolio profile updated successfully"}), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating portfolio profile for ID {portfolio_id}: {e}")
        traceback.print_exc()
        return jsonify({"error": "Internal server error during profile update."}), 500
