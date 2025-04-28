import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
from flask_login import LoginManager
from dotenv import load_dotenv
from app.config import Config
from app.routes.admin import admin_bp

# Load environment variables from .env
load_dotenv()

# Initialize extensions
db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()

# Make sure SQLAlchemy knows about all your models before create_all()
import app.models  # Import models like Asset, User, etc.

def create_app():
    # Paths for static and template folders
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    static_folder = os.path.join(project_root, 'static')
    template_folder = os.path.join(project_root, 'templates')

    # Create Flask app instance
    app = Flask(__name__, static_folder=static_folder, template_folder=template_folder)
    app.config.from_object(Config)

    # Initialize extensions with the app
    db.init_app(app)
    bcrypt.init_app(app)
    migrate = Migrate(app, db)  # Ensure migration support
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login_page'

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.portfolio_api import portfolio_bp
    from app.routes.portfolio_metrics import metrics_bp
    from app.routes.transactions import transactions_bp
    from app.routes.efficient_frontier import efficient_frontier_bp

    # Register the admin blueprint
    app.register_blueprint(auth_bp)
    app.register_blueprint(portfolio_bp, url_prefix="/portfolio")
    app.register_blueprint(metrics_bp)
    app.register_blueprint(transactions_bp, url_prefix="/transactions")
    app.register_blueprint(efficient_frontier_bp, url_prefix="/efficient-frontier")
    app.register_blueprint(admin_bp, url_prefix='/admin')  # Ensure admin routes work

    # Optional: Register market blueprint (if available)
    try:
        from app.routes.market_data import market_bp
        app.register_blueprint(market_bp, url_prefix="/market")
    except ImportError:
        print("Warning: app/routes/market_data.py not found. Skipping market blueprint registration.")

    # Application context: create tables, seed assets, fetch historical data
    with app.app_context():
        db.create_all()  # Create all tables in the database
        if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':  # Ensure it's only run in the main app
            # Seed common tickers with real details if not present
            from app.models import Asset
            from app.market_fetcher import fetch_market_data, fetch_and_map_asset_details

            for symbol in Config.COMMON_TICKERS:
                s = symbol.strip().upper()
                if not Asset.query.filter_by(symbol=s).first():  # Check if the asset exists
                    details = fetch_and_map_asset_details(s) or {}
                    asset = Asset(
                        symbol=s,
                        company_name=details.get('name'),
                        asset_type=details.get('type'),
                        sector=details.get('sector'),
                        user_id=None  # No user assigned initially
                    )
                    db.session.add(asset)

            db.session.commit()

            # Backfill one year of historical prices for assets
            fetch_market_data(historical=True)

    return app
