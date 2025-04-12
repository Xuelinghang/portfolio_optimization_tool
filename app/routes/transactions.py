from flask import Blueprint, request, jsonify, session, abort
from app import db
from app.models import Transaction, Asset, Portfolio
from datetime import datetime

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
            'portfolio_name': transaction.portfolio.portfolio_name  # Added portfolio name
        }
        transaction_list.append(transaction_data)
    
    return jsonify(transaction_list)

@transactions_bp.route('/<int:transaction_id>', methods=['GET'])
def get_transaction(transaction_id):
    user_id = authenticate()
    transaction = Transaction.query.filter_by(id=transaction_id, user_id=user_id).first()
    if not transaction:
        abort(404)  # Not Found
    
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
        'portfolio_name': transaction.portfolio.portfolio_name # Added portfolio name
    }
    return jsonify(transaction_data)

@transactions_bp.route('/', methods=['POST'])
def create_transaction():
    user_id = authenticate()
    data = request.get_json()
    
    # Required fields: asset_id, portfolio_id, transaction_type, quantity, price, transaction_date
    required_fields = ['asset_id', 'portfolio_id', 'transaction_type', 'quantity', 'price', 'transaction_date']
    missing_fields = [field for field in required_fields if field not in data]
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
    
    # Parse transaction_date (expected format: YYYY-MM-DD)
    try:
        transaction_date = datetime.strptime(data['transaction_date'], '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'Invalid transaction_date format. Expected YYYY-MM-DD'}), 400
    
    # Validate portfolio_id: ensure the portfolio exists and belongs to the current user
    portfolio = Portfolio.query.filter_by(id=data['portfolio_id'], user_id=user_id).first()
    if not portfolio:
        return jsonify({'error': 'Invalid portfolio_id or the portfolio does not belong to the user'}), 400
    
    # Check if the asset exists
    asset = Asset.query.get(data['asset_id'])
    if not asset:
        return jsonify({'error': 'Asset not found'}), 404
    
    # Process optional fields: fees and notes
    fees = 0.0
    if 'fees' in data:
        try:
            fees = float(data['fees'])
        except ValueError:
            return jsonify({'error': 'Invalid fees value'}), 400
    notes = data.get('notes', None)
    
    new_transaction = Transaction(
        user_id=user_id,
        asset_id=data['asset_id'],
        portfolio_id=data['portfolio_id'],
        transaction_type=data['transaction_type'],
        quantity=quantity,
        price=price,
        transaction_date=transaction_date,
        fees=fees,
        notes=notes
    )
    
    db.session.add(new_transaction)
    db.session.commit()
    
    return jsonify({'message': 'Transaction created', 'transaction_id': new_transaction.id}), 201

@transactions_bp.route('/<int:transaction_id>', methods=['POST'])
def update_transaction(transaction_id):
    user_id = authenticate()
    transaction = Transaction.query.filter_by(id=transaction_id, user_id=user_id).first()
    if not transaction:
        abort(404)  # Not Found
    
    data = request.get_json()
    
    # Required fields: asset_id, portfolio_id, transaction_type, quantity, price, transaction_date
    required_fields = ['asset_id', 'portfolio_id', 'transaction_type', 'quantity', 'price', 'transaction_date']
    missing_fields = [field for field in required_fields if field not in data]
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
        return jsonify({'error': 'Invalid transaction_date format. Expected %Y-%m-%d'}), 400
    
    # Validate portfolio_id
    portfolio = Portfolio.query.filter_by(id=data['portfolio_id'], user_id=user_id).first()
    if not portfolio:
        return jsonify({'error': 'Invalid portfolio_id or the portfolio does not belong to the user'}), 400

    asset = Asset.query.get(data['asset_id'])
    if not asset:
        return jsonify({'error': 'Asset not found'}), 404
    
    transaction.asset_id = data['asset_id']
    transaction.portfolio_id = data['portfolio_id']
    transaction.transaction_type = data['transaction_type']
    transaction.quantity = quantity
    transaction.price = price
    transaction.transaction_date = transaction_date

    if 'fees' in data:
        try:
            transaction.fees = float(data['fees'])
        except ValueError:
            return jsonify({'error': 'Invalid fees value'}), 400
    else:
        transaction.fees = 0.0
    transaction.notes = data.get('notes', None)
    
    db.session.commit()
    
    return jsonify({'message': 'Transaction updated'}), 200

@transactions_bp.route('/<int:transaction_id>', methods=['DELETE'])
def delete_transaction(transaction_id):
    user_id = authenticate()
    transaction = Transaction.query.filter_by(id=transaction_id, user_id=user_id).first()
    if not transaction:
        abort(404)  # Not Found
    
    db.session.delete(transaction)
    db.session.commit()
    
    return jsonify({'message': 'Transaction deleted'}), 200