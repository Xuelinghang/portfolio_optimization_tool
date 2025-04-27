# app/__init__.py

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
from flask_login import LoginManager
from dotenv import load_dotenv
from app.config import Config

# Load environment variables
load_dotenv()

# Initialize extensions (not yet bound to app)
db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()

# Ensure SQLAlchemy metadata knows about all your models before create_all()
import app.models    # registers Asset, MarketData, etc.


def create_app():
    # Paths for static/templates
    project_root   = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    static_folder  = os.path.join(project_root, 'static')
    template_folder= os.path.join(project_root, 'templates')

    # Create Flask app
    app = Flask(__name__, static_folder=static_folder, template_folder=template_folder)
    app.config.from_object(Config)

    # Initialize extensions
    db.init_app(app)
    bcrypt.init_app(app)
    Migrate(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login_page'

    # Register your blueprints
    from app.routes.auth import auth_bp
    from app.routes.portfolio_api import portfolio_bp
    from app.routes.portfolio_metrics import metrics_bp
    from app.routes.transactions import transactions_bp
    from app.routes.efficient_frontier import efficient_frontier_bp
    from app.routes.admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(portfolio_bp, url_prefix="/portfolio")
    app.register_blueprint(metrics_bp)
    app.register_blueprint(transactions_bp, url_prefix="/transactions")
    app.register_blueprint(efficient_frontier_bp, url_prefix="/efficient-frontier")
    app.register_blueprint(admin_bp)

    # Optional market blueprint
    try:
        from app.routes.market_data import market_bp
        app.register_blueprint(market_bp, url_prefix="/market")
    except ImportError:
        print("Warning: app/routes/market_data.py not found. Skipping market blueprint registration.")

    # Application context: create tables, seed assets, and fetch history
    with app.app_context():
        # 1) Create all tables
        db.create_all()
        if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            # 2) Seed COMMON_TICKERS with real details
            from app.models import Asset
            from app.market_fetcher import fetch_market_data, fetch_and_map_asset_details

            for symbol in Config.COMMON_TICKERS:
                s = symbol.strip().upper()
                if not Asset.query.filter_by(symbol=s).first():
                    # Fetch name, type, sector, etc.
                    details = fetch_and_map_asset_details(s) or {}
                    asset = Asset(
                        symbol       = s,
                        company_name = details.get('name'),
                        asset_type   = details.get('type'),
                        sector       = details.get('sector'),
                        user_id      = None
                    )
                    db.session.add(asset)

            db.session.commit()

            # 3) Backfill one year of historical prices
            fetch_market_data(historical=True)
    return app
