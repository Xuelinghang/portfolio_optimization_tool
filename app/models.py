from app import db
from datetime import datetime

class User(db.Model):
    """User model for storing user accounts."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(100), nullable=False)
    
    # Relationships
    assets = db.relationship("Asset", backref="user", lazy=True)
    portfolios = db.relationship("Portfolio", backref="user", lazy=True)  # renamed to plural

class Asset(db.Model):
    """Asset model representing a financial asset (Stock, ETF, Bond, Crypto)."""
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(10), nullable=False)
    asset_type = db.Column(db.String(10), nullable=False)  # e.g., Stock, ETF, Bond, Crypto
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    
    # Removed direct relationship to Portfolio; portfolios are stored separately.
    market_data = db.relationship("MarketData", backref="asset", lazy=True)

class Portfolio(db.Model):
    """Portfolio model to store an entire saved portfolio for a user."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    portfolio_name = db.Column(db.String(100), nullable=False)  # New field for portfolio name
    portfolio_data = db.Column(db.Text, nullable=True)  # Stores JSON of portfolio entries
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)

class MarketData(db.Model):
    """Unified MarketData model to store price data for assets."""
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("asset.id"), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    price = db.Column(db.Float, nullable=False)
    
class Transaction(db.Model):
    """Transaction model to store individual buy/sell orders."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    asset_id = db.Column(db.Integer, db.ForeignKey("asset.id"), nullable=False)
    portfolio_id = db.Column(db.Integer, db.ForeignKey("portfolio.id"), nullable=False)  # New field: portfolio_id
    transaction_type = db.Column(db.String(10), nullable=False)  # 'buy' or 'sell'
    quantity = db.Column(db.Float, nullable=False)
    price = db.Column(db.Float, nullable=False)
    transaction_date = db.Column(db.DateTime, default=datetime.utcnow)
    fees = db.Column(db.Float, nullable=True)   # New field: fees
    notes = db.Column(db.Text, nullable=True)     # New field: notes
