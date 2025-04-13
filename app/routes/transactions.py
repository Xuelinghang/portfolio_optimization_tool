from flask import Blueprint, request, jsonify, session, abort
from datetime import datetime
from app import db
from app.models import Transaction, Asset, Portfolio

transactions_bp = Blueprint('transactions', __name__, url_prefix='/transactions')

def authenticate():
    if 'user_id' not in session:
        abort(401)  # Unauthorized
    return session['user_id']

@transactions_bp.route('/', methods=['GET'])
def get_transactions():
    user_id = authenticate()
    transactions = Transaction.query.filter_by(user_id=user_id).all()
    
    transaction_list = []
    for transaction in transactions:
        # Look up the portfolio
        portfolio = Portfolio.query.get(transaction.portfolio_id)
        portfolio_name = portfolio.portfolio_name if portfolio else "Unknown"
        
        # Look up the asset
        asset = Asset.query.get(transaction.asset_id)
        ticker = asset.symbol if asset else "Unknown"
        
        transaction_data = {
            'id': transaction.id,
            'transaction_type': transaction.transaction_type,
            'quantity': transaction.quantity,
            'price': transaction.price,
            'transaction_date': transaction.transaction_date.isoformat(),
            'fees': transaction.fees,
            'notes': transaction.notes,
            
            'portfolio_id': transaction.portfolio_id,   # if you still need it
            'portfolio_name': portfolio_name,           # to display in the UI
            'asset_id': transaction.asset_id,           # if you still need it
            'ticker': ticker                            # to display in the UI
        }
        transaction_list.append(transaction_data)
    
    return jsonify(transaction_list)


@transactions_bp.route('/<int:transaction_id>', methods=['GET'])
def get_transaction(transaction_id):
    user_id = authenticate()
    transaction = Transaction.query.filter_by(id=transaction_id, user_id=user_id).first()
    if not transaction:
        abort(404)  # Not Found

    portfolio_obj = Portfolio.query.get(transaction.portfolio_id)
    portfolio_name = portfolio_obj.portfolio_name if portfolio_obj else "Unknown"
    
    transaction_data = {
        'id': transaction.id,
        'asset_id': transaction.asset_id,
        'portfolio_id': transaction.portfolio_id,
        'transaction_type': transaction.transaction_type,
        'quantity': transaction.quantity,
        'price': transaction.price,
        'transaction_date': transaction.transaction_date.isoformat(),
        'fees': transaction.fees,
        'notes': transaction.notes,
        'portfolio_name': portfolio_name
    }
    return jsonify(transaction_data)

@transactions_bp.route('/', methods=['POST'])
def create_transaction():
    """
    Expected JSON payload:
      - ticker: (string) asset ticker symbol (e.g., "AAPL")
      - portfolio_name: (string) name of the portfolio for this transaction
      - transaction_type: (string) "buy" or "sell"
      - quantity: (number) amount to trade
      - price: (number) price per unit
      - transaction_date: (string) in format "YYYY-MM-DD"
      - Optional: fees (number), notes (string)
    """
    user_id = authenticate()
    data = request.get_json()
    
    # Validate required fields
    required_fields = ['ticker', 'portfolio_name', 'transaction_type', 'quantity', 'price', 'transaction_date']
    missing_fields = [field for field in required_fields if field not in data or not data[field]]
    if missing_fields:
        return jsonify({'error': f'Missing required fields: {", ".join(missing_fields)}'}), 400
    
    if data['transaction_type'] not in ('buy', 'sell'):
        return jsonify({'error': 'Invalid transaction type'}), 400
    
    try:
        quantity = float(data['quantity'])
        price = float(data['price'])
    except ValueError:
        return jsonify({'error': 'Invalid quantity or price'}), 400
    
    if quantity <= 0 or price <= 0:
        return jsonify({'error': 'Quantity and price must be positive'}), 400
    
    try:
        transaction_date = datetime.strptime(data['transaction_date'], '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'Invalid transaction_date format. Expected YYYY-MM-DD'}), 400
    
    # Retrieve portfolio based on portfolio_name for the current user.
    portfolio_name = data['portfolio_name'].strip()
    portfolio = Portfolio.query.filter_by(user_id=user_id, portfolio_name=portfolio_name).first()
    if not portfolio:
        return jsonify({'error': 'Portfolio not found for this user (check portfolio name)'}), 400

    # Determine asset: lookup by ticker (create asset if not found)
    ticker = data['ticker'].strip().upper()
    asset = Asset.query.filter_by(symbol=ticker, user_id=user_id).first()
    if not asset:
        # Create new asset with default asset_type 'Stock'
        asset = Asset(symbol=ticker, asset_type='Stock', user_id=user_id)
        db.session.add(asset)
        db.session.commit()  # Commit to assign an ID
    asset_id = asset.id

    # Process optional fields: fees and notes
    fees = 0.0
    if 'fees' in data and data['fees'] != '':
        try:
            fees = float(data['fees'])
        except ValueError:
            return jsonify({'error': 'Invalid fees value'}), 400
    notes = data.get('notes')

    new_transaction = Transaction(
        user_id=user_id,
        asset_id=asset_id,
        portfolio_id=portfolio.id,
        transaction_type=data['transaction_type'],
        quantity=quantity,
        price=price,
        transaction_date=transaction_date,
        fees=fees,
        notes=notes
    )
    db.session.add(new_transaction)
    db.session.commit()
    
    return jsonify({'message': 'Transaction created successfully', 'transaction_id': new_transaction.id}), 201

@transactions_bp.route('/<int:transaction_id>', methods=['POST'])
def update_transaction(transaction_id):
    """
    Expected JSON payload for update:
      - ticker, portfolio_name, transaction_type, quantity, price, transaction_date
      - Optional: fees, notes
    """
    user_id = authenticate()
    transaction = Transaction.query.filter_by(id=transaction_id, user_id=user_id).first()
    if not transaction:
        abort(404)
    
    data = request.get_json()
    required_fields = ['ticker', 'portfolio_name', 'transaction_type', 'quantity', 'price', 'transaction_date']
    missing_fields = [field for field in required_fields if field not in data or not data[field]]
    if missing_fields:
        return jsonify({'error': f'Missing required fields: {", ".join(missing_fields)}'}), 400
    
    if data['transaction_type'] not in ('buy', 'sell'):
        return jsonify({'error': 'Invalid transaction type'}), 400

    try:
        quantity = float(data['quantity'])
        price = float(data['price'])
    except ValueError:
        return jsonify({'error': 'Invalid quantity or price'}), 400
    
    if quantity <= 0 or price <= 0:
        return jsonify({'error': 'Quantity and price must be positive'}), 400
    
    try:
        transaction_date = datetime.strptime(data['transaction_date'], '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'Invalid transaction_date format. Expected YYYY-MM-DD'}), 400
    
    # Retrieve portfolio by portfolio_name for current user
    portfolio_name = data['portfolio_name'].strip()
    portfolio = Portfolio.query.filter_by(user_id=user_id, portfolio_name=portfolio_name).first()
    if not portfolio:
        return jsonify({'error': 'Portfolio not found for this user'}), 400

    # Determine asset using the ticker
    ticker = data['ticker'].strip().toUpperCase()  # Correction: use .upper()
    ticker = data['ticker'].strip().upper()
    asset = Asset.query.filter_by(symbol=ticker, user_id=user_id).first()
    if not asset:
        asset = Asset(symbol=ticker, asset_type='Stock', user_id=user_id)
        db.session.add(asset)
        db.session.commit()
    asset_id = asset.id

    transaction.asset_id = asset_id
    transaction.portfolio_id = portfolio.id
    transaction.transaction_type = data['transaction_type']
    transaction.quantity = quantity
    transaction.price = price
    transaction.transaction_date = transaction_date

    if 'fees' in data and data['fees'] != '':
        try:
            transaction.fees = float(data['fees'])
        except ValueError:
            return jsonify({'error': 'Invalid fees value'}), 400
    else:
        transaction.fees = 0.0
    transaction.notes = data.get('notes')
    
    db.session.commit()
    
    return jsonify({'message': 'Transaction updated'}), 200

@transactions_bp.route('/<int:transaction_id>', methods=['DELETE'])
def delete_transaction(transaction_id):
    user_id = authenticate()
    transaction = Transaction.query.filter_by(id=transaction_id, user_id=user_id).first()
    if not transaction:
        abort(404)
    
    db.session.delete(transaction)
    db.session.commit()
    
    return jsonify({'message': 'Transaction deleted'}), 200
