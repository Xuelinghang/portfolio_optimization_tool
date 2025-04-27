import uuid
# Import UTC timezone
from datetime import datetime, timedelta, date, UTC # <--- ADDED UTC
import json

# Import Flask-Login's UserMixin
from flask_login import UserMixin

from app import db # Assuming db is initialized in app/__init__.py
# Import the login_manager instance from where it was initialized
# This is needed to register the user_loader
from app import login_manager # <--- ADDED import for login_manager
from werkzeug.security import generate_password_hash, check_password_hash


# --- User Loader function for Flask-Login ---
# This function is required by Flask-Login to load a user from the database
# given their user ID stored in the session.
@login_manager.user_loader # <--- REGISTER THIS FUNCTION
def load_user(user_id):
    """
    Loads a user from the database given the user ID.
    Used by Flask-Login.
    """
    # Flask-Login passes the user ID as a string, ensure conversion if your ID is int
    if user_id is not None:
        # Query the User model by its primary key (id)
        return User.query.get(int(user_id)) # <--- Query the User model
    return None # Return None if user_id is None


class User(db.Model, UserMixin): # <--- ADDED UserMixin inheritance
    """User model for storing user accounts."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(100), nullable=False)

    # --- Added fields for Admin Functionality ---
    is_admin = db.Column(db.Boolean, default=False, nullable=False) # Flag if user is an administrator
    is_active = db.Column(db.Boolean, default=True, nullable=False) # Flag if account is active (can be disabled by admin)
    password_reset_required = db.Column(db.Boolean, default=False, nullable=False) # Flag to force password reset on next login

    # --- Relationships ---
    assets = db.relationship("Asset", backref="user", lazy=True)
    portfolios = db.relationship("Portfolio", backref="user", lazy=True)
    transactions = db.relationship('Transaction', backref='user', lazy=True) # Associate transactions with user

    # --- Password Hashing Methods ---
    def set_password(self, password):
        """Hashes and sets the user's password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Checks if the provided password matches the stored hash."""
        return check_password_hash(self.password_hash, password)

    # UserMixin provides these properties/methods automatically based on the columns:
    # is_authenticated, is_active, is_anonymous, get_id()
    # You don't need to redefine is_active if inheriting UserMixin and using a column named 'is_active'

    @property
    def is_authenticated(self):
        """Indicates if the user is authenticated."""
        # In most cases with Flask-Login and a properly loaded user, this should be True
        # as they wouldn't be loaded if not authenticated via session.
        return True

    @property
    def is_anonymous(self):
        """Indicates if the user is anonymous."""
        # A user loaded via Flask-Login is never anonymous
        return False

    def get_id(self):
        """Returns the user ID as a string."""
        # UserMixin requires returning a string ID
        return str(self.id)

    def __repr__(self):
        return f'<User {self.username}>'


class Asset(db.Model):
    """Asset model representing a financial asset."""
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(10), nullable=False)
    company_name = db.Column(db.String(100), nullable=True)
    asset_type = db.Column(db.String(10), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    sector = db.Column(db.String(50), nullable=True)

    market_data = db.relationship("MarketData", backref="asset", lazy=True)
    holdings    = db.relationship("PortfolioAsset", back_populates="asset", cascade="all, delete-orphan", lazy=True)

    def __repr__(self):
        return f"<Asset {self.symbol} ({self.asset_type})>"


class Portfolio(db.Model):
    """Portfolio model to store each saved portfolio."""
    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    portfolio_name  = db.Column(db.String(100), nullable=False)
    total_value     = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Use datetime.now(UTC) for timezone-aware UTC datetime
    purchase_date   = db.Column(db.DateTime, default=datetime.now(UTC))

    holdings = db.relationship("PortfolioAsset", back_populates="portfolio", cascade="all, delete-orphan", lazy="joined")

    def __repr__(self):
        return f"<Portfolio {self.id}: {self.portfolio_name} for User {self.user_id}>"


class MarketData(db.Model):
    """Unified MarketData model to store price data for assets."""
    id       = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("asset.id"), nullable=False)
    date     = db.Column(db.DateTime, default=datetime.now(UTC))
    price    = db.Column(db.Float, nullable=False)

    def __repr__(self):
        # Ensure date is not None before formatting
        date_str = self.date.strftime('%Y-%m-%d %H:%M') if self.date else 'N/A'
        return f"<MarketData ID: {self.id}, Asset ID: {self.asset_id}, Date: {date_str}, Price: {self.price}>"


class Transaction(db.Model):
    """Transaction model to store individual buy/sell orders."""
    id               = db.Column(db.Integer, primary_key=True)
    user_id          = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    asset_id         = db.Column(db.Integer, db.ForeignKey("asset.id"), nullable=False)
    portfolio_id     = db.Column(db.Integer, db.ForeignKey("portfolio.id"), nullable=False)
    transaction_type = db.Column(db.String(10), nullable=False)  # 'buy' or 'sell'
    quantity         = db.Column(db.Float, nullable=False)
    price            = db.Column(db.Float, nullable=False)
    transaction_date = db.Column(db.DateTime, default=datetime.now(UTC))
    fees             = db.Column(db.Float, nullable=True)
    notes            = db.Column(db.Text, nullable=True)

    # --- Added field for Admin Functionality ---
    is_system = db.Column(db.Boolean, default=False, nullable=False) # Flag for system-generated transactions

    def __repr__(self):
        # Ensure dates/IDs are handled if potentially None
        user_id_str = self.user_id if self.user_id is not None else 'N/A'
        asset_id_str = self.asset_id if self.asset_id is not None else 'N/A'
        type_str = self.transaction_type if self.transaction_type else 'N/A'
        date_str = self.transaction_date.strftime('%Y-%m-%d %H:%M') if self.transaction_date else 'N/A'
        return f"<Transaction ID: {self.id}, Type: {type_str}, User: {user_id_str}, Asset: {asset_id_str} on {date_str}>"


class PortfolioAsset(db.Model):
    """Tracks how much of each asset lives in each portfolio."""
    __tablename__   = "portfolio_asset"
    id               = db.Column(db.Integer, primary_key=True)
    portfolio_id     = db.Column(db.Integer, db.ForeignKey("portfolio.id"), nullable=False)
    asset_id         = db.Column(db.Integer, db.ForeignKey("asset.id"),     nullable=False)
    dollar_amount    = db.Column(db.Float, nullable=False, default=0.0)
    allocation_pct   = db.Column(db.Float, nullable=False, default=0.0)
    purchase_date    = db.Column(db.Date, nullable=True)

    portfolio = db.relationship("Portfolio", back_populates="holdings")
    asset     = db.relationship("Asset", back_populates="holdings")

    def __repr__(self):
        # Ensure IDs are handled if potentially None
        portfolio_id_str = self.portfolio_id if self.portfolio_id is not None else 'N/A'
        asset_id_str = self.asset_id if self.asset_id is not None else 'N/A'
        return f"<PortfolioAsset ID: {self.id}, Portfolio: {portfolio_id_str}, Asset: {asset_id_str}, Alloc: {self.allocation_pct:.2f}%>"


class CalculationResult(db.Model):
    """Temporary storage for Efficient Frontier calculation results."""
    # Using String for UUID for broader database compatibility
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now(UTC), nullable=False)
    results_text = db.Column(db.Text, nullable=False)

    user = db.relationship('User', backref=db.backref('calculation_results', lazy=True))

    def __repr__(self):
        return f"<CalculationResult {self.id} by User {self.user_id} at {self.timestamp.strftime('%Y-%m-%d %H:%M') if self.timestamp else 'N/A'}>"

    # Helper methods to get/set results as dictionary
    @property
    def results_data(self):
        """Loads the JSON text into a Python dictionary."""
        if self.results_text:
            try:
                # Consider using object_hook=db.metadata.bind.dialect.json_deserializer
                # if you are using a database that supports JSON natively and configured it
                return json.loads(self.results_text)
            except json.JSONDecodeError:
                print(f"Error decoding JSON for CalculationResult ID {self.id}")
                return {}
        return {}

    @results_data.setter
    def results_data(self, data_dict):
        """Saves a Python dictionary as JSON text."""
        # Use db.metadata.bind.dialect.json_serializer if using native JSON type
        self.results_text = json.dumps(data_dict)