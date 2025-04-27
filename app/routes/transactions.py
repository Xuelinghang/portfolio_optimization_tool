# app/routes/transactions.py

import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date, UTC
import requests
from flask_login import login_required, current_user
from flask import (
    Blueprint, request, jsonify, abort,
    render_template, current_app, flash
)
from werkzeug.utils import secure_filename
import traceback
import time
from io import StringIO
from app import db
from app.models import (
    User, Portfolio, Asset, MarketData,
    PortfolioAsset, Transaction, CalculationResult
)
from sqlalchemy.orm import joinedload
from app.market_fetcher import fetch_and_map_asset_details, validate_and_fetch_asset_data

transactions_bp = Blueprint('transactions', __name__, url_prefix='/transactions')

@transactions_bp.route('/', methods=['GET'])
@login_required
def get_transactions():
    """Render the transaction history page for the logged-in user."""
    user_id = current_user.id
    username = current_user.username

    try:
        # Just fetch the user's transactions; no joinedload on non-existent attributes
        transactions_from_db = (
            Transaction.query
                       .filter_by(user_id=user_id)
                       .order_by(Transaction.transaction_date.desc())
                       .all()
        )

        transaction_list_for_template = []
        for tx in transactions_from_db:
            # Manually look up portfolio and asset
            portfolio = Portfolio.query.get(tx.portfolio_id)
            asset     = Asset.query.get(tx.asset_id)

            transaction_list_for_template.append({
                'id': tx.id,
                'transaction_type': tx.transaction_type,
                'quantity': float(tx.quantity or 0.0),
                'price': float(tx.price or 0.0),
                'transaction_date': tx.transaction_date.isoformat() if tx.transaction_date else None,
                'fees': float(tx.fees or 0.0),
                'notes': tx.notes,
                'portfolio_id': tx.portfolio_id,
                'portfolio_name': portfolio.portfolio_name if portfolio else "Unknown",
                'asset_id': tx.asset_id,
                'ticker': asset.symbol if asset else "Unknown",
                'total_value': (
                    float(tx.quantity or 0.0) * float(tx.price or 0.0)
                ) + float(tx.fees or 0.0)
            })

    except Exception as e:
        current_app.logger.error(f"Error fetching transactions for user {user_id}: {e}")
        traceback.print_exc()
        db.session.rollback()
        flash('Error loading transactions. Please try again.', 'danger')
        transaction_list_for_template = []

    # Pass the list into the template as `transactions`
    now_date = datetime.utcnow().date().isoformat()
    return render_template(
        'transactions.html',
        transactions=transaction_list_for_template,
        username=username,
        now_date=now_date
    )

# --- Transaction Management API Routes ---

@transactions_bp.route('/<int:transaction_id>', methods=['GET'])
@login_required
def get_transaction(transaction_id):
    """Fetch a single transaction for the logged-in user."""
    user_id = current_user.id

    tx = (
        Transaction.query
            .filter_by(id=transaction_id, user_id=user_id)
            .options(joinedload(Transaction.portfolio))
            .first()
    )

    if not tx:
        abort(404)

    asset = Asset.query.get(tx.asset_id)
    return jsonify({
        'id': tx.id,
        'asset_id': tx.asset_id,
        'portfolio_id': tx.portfolio_id,
        'transaction_type': tx.transaction_type,
        'quantity': float(tx.quantity or 0.0),
        'price': float(tx.price or 0.0),
        'transaction_date': tx.transaction_date.isoformat() if tx.transaction_date else None,
        'fees': float(tx.fees or 0.0),
        'notes': tx.notes,
        'portfolio_name': tx.portfolio.portfolio_name if tx.portfolio else "Unknown",
        'ticker': asset.symbol if asset else "Unknown"
    })


@transactions_bp.route('/', methods=['POST'])
@login_required
def create_transaction():
    """Create a new transaction for the logged-in user."""
    user_id = current_user.id
    data = request.get_json() or {}

    # ... (validation logic) ...

    portfolio = Portfolio.query.filter_by(
        user_id=user_id,
        portfolio_name=data['portfolio_name'].strip()
    ).first()
    if not portfolio:
        return jsonify({'error': f'Portfolio "{data["portfolio_name"]}" not found'}), 400

    ticker = data['ticker'].strip().upper()
    asset = Asset.query.filter_by(symbol=ticker, user_id=user_id).first()

    if not asset:
        # Asset does not exist, create a new one
        print(f"Creating new asset for ticker: {ticker}") # Optional print
        asset = Asset(symbol=ticker, user_id=user_id) # Create the new asset object

        # --- Fetch asset details (including sector) using the fetcher function ---
        details = fetch_and_map_asset_details(ticker) # Call the fetcher

        if details:
            # Populate asset details from the fetched data
            asset.company_name = details.get('name', ticker) # Use fetched name, default to ticker
            asset.asset_type = details.get('type', 'Unknown') # Use fetched type, default to Unknown
            asset.sector = details.get('sector', None) # <--- Populate the sector field!
            # You can add other fields here too (exchange, currency, etc.)
            print(f"Fetched details for {ticker}: Name={asset.company_name}, Type={asset.asset_type}, Sector={asset.sector}") # Optional print
        else:
            # If fetching details failed, set default values (asset.symbol and user_id are already set)
            asset.company_name = ticker # Default name
            asset.asset_type = 'Unknown' # Default type
            asset.sector = None # Ensure sector is None if fetch failed
            print(f"Failed to fetch details for {ticker}. Using defaults: Name={asset.company_name}, Type={asset.asset_type}, Sector={asset.sector}") # Optional print

        db.session.add(asset) # Add the new asset object to the session
        db.session.flush() # Flush to get the asset.id

        # Immediately validate and fetch historical data
        validate_and_fetch_asset_data(asset.symbol, asset.asset_type)



    fees = float(data.get('fees') or 0.0)
    notes = data.get('notes', '').strip()

    # Begin: Patch inserting missing Transaction creation
    quantity = float(data.get('quantity') or 0.0)
    price = float(data.get('price') or 0.0)
    transaction_type = data.get('transaction_type', '').lower()
    transaction_date = datetime.strptime(data['transaction_date'], "%Y-%m-%d")

    tx = Transaction(
        user_id=user_id,
        portfolio_id=portfolio.id,
        asset_id=asset.id,
        transaction_type=transaction_type,
        quantity=quantity,
        price=price,
        fees=fees,
        notes=notes,
        transaction_date=transaction_date
    )
    db.session.add(tx)
    # End: Patch
    # --- Update or Create PortfolioAsset holding after a transaction ---

    holding = PortfolioAsset.query.filter_by(
    portfolio_id=portfolio.id,
    asset_id=asset.id
    ).first()

    if holding:
    # Update the existing holding
        if transaction_type == 'buy':
            holding.dollar_amount = (holding.dollar_amount or 0) + (quantity * price)
        elif transaction_type == 'sell':
            holding.dollar_amount = (holding.dollar_amount or 0) - (quantity * price)
    else:
    # Create new holding
        holding = PortfolioAsset(
            portfolio_id=portfolio.id,
            asset_id=asset.id,
            dollar_amount=(quantity * price),
            allocation_pct=0.0,  # Optional: recalculate later
            purchase_date=transaction_date
        )
        db.session.add(holding)

    # --- Update Portfolio total value ---
    if transaction_type == 'buy':
        portfolio.total_value = (portfolio.total_value or 0) + (quantity * price)
    elif transaction_type == 'sell':
        portfolio.total_value = (portfolio.total_value or 0) - (quantity * price)


    # ... (rest of the transaction creation and portfolio/holding update logic) ...

    try:
        db.session.commit()
        print(f"Transaction created and asset {asset.symbol} saved/updated.") # Optional print
        return jsonify({
            'message': 'Transaction created successfully',
            'transaction': {
                'id': tx.id,
                'transaction_type': tx.transaction_type,
                'quantity': tx.quantity,
                'price': tx.price,
                'transaction_date': tx.transaction_date.isoformat(),
                'fees': tx.fees,
                'notes': tx.notes,
                'portfolio_id': tx.portfolio_id,
                'portfolio_name': portfolio.portfolio_name,
                'asset_id': tx.asset_id,
                'ticker': ticker,
                'total_value': (quantity * price) + fees, # Note: total_value calculation might need review (includes fees?)
                'asset_name': asset.company_name, # Add asset name to response
                'asset_type': asset.asset_type, # Add asset type to response
                'asset_sector': asset.sector # Add asset sector to response
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating transaction: {e}")
        traceback.print_exc()
        return jsonify({'error': 'Database error saving transaction.'}), 500

@transactions_bp.route('/<int:transaction_id>', methods=['DELETE'])
@login_required
def delete_transaction(transaction_id):
    """Delete a transaction by ID."""
    user_id = current_user.id
    try:
        tx = Transaction.query.filter_by(id=transaction_id, user_id=user_id).first()
        if not tx:
            return jsonify({'error': 'Transaction not found'}), 404

        db.session.delete(tx)
        db.session.commit()
        return jsonify({'message': 'Transaction deleted successfully'}), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting transaction {transaction_id}: {e}")
        traceback.print_exc()
        return jsonify({'error': 'Database error deleting transaction.'}), 500