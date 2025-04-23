# app/__init__.py

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
from flask_login import LoginManager
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize extensions (do not initialize with app here in factory pattern)
db = SQLAlchemy()
bcrypt = Bcrypt()

login_manager = LoginManager() # <--- ADDED Flask-Login instance


def create_app():
    # Determine the project root (one level up from the 'app' folder)
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    static_folder = os.path.join(project_root, 'static')
    template_folder = os.path.join(project_root, 'templates')

    # Create Flask app with explicit paths (optional but can help)
    app = Flask(__name__, static_folder=static_folder, template_folder=template_folder)

    db_path = os.path.join(project_root, 'instance', 'portfolio.db')
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", f"sqlite:///{db_path}")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Set the secret key for session management (REQUIRED by Flask-Login)
    # IMPORTANT: Change 'my_default_secret_key' to a real, random, secret key for production
    app.secret_key = os.getenv("SECRET_KEY", "my_default_secret_key") # <--- Ensure SECRET_KEY is set

    # Initialize extensions with the app instance
    db.init_app(app)
    bcrypt.init_app(app)
    migrate = Migrate(app, db)

    login_manager.init_app(app) # <--- ADDED Flask-Login initialization
    login_manager.login_view = 'auth.login_page'

    from app.routes.auth import auth_bp
    from app.routes.portfolio_api import portfolio_bp
    from app.routes.portfolio_metrics import metrics_bp
    from app.routes.transactions import transactions_bp
    from app.routes.efficient_frontier import efficient_frontier_bp
    from app.routes.admin import admin_bp
    # Conditionally import market_data if it exists
    try:
        from app.routes.market_data import market_bp
        app.register_blueprint(market_bp, url_prefix="/market")
    except ImportError:
        print("Warning: app/routes/market_data.py not found. Skipping market blueprint registration.")
        pass

    # Register blueprints with prefixes where appropriate
    app.register_blueprint(auth_bp) # Explicitly register auth with a prefix
    app.register_blueprint(portfolio_bp, url_prefix="/portfolio") # Portfolio blueprint with prefix
    app.register_blueprint(metrics_bp) # Metrics blueprint with prefix
    app.register_blueprint(transactions_bp, url_prefix="/transactions") # Transactions blueprint with prefix
    app.register_blueprint(efficient_frontier_bp, url_prefix="/efficient-frontier") # Give efficient frontier a prefix
    app.register_blueprint(admin_bp)

    with app.app_context():
        db.create_all()
    return app