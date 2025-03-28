import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize extensions
db = SQLAlchemy()
bcrypt = Bcrypt()
jwt = JWTManager()

def create_app():
    # Create Flask app and set folders for static files and templates
    app = Flask(__name__, static_folder="static", template_folder="templates")
    
    # Application configuration
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///portfolio.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "super_secret_key")  # Change this in production

    # Initialize extensions with the app
    db.init_app(app)
    bcrypt.init_app(app)
    jwt.init_app(app)

    # Register Blueprints from the routes package
    from app.routes.auth import auth_bp
    from app.routes.portfolio_api import portfolio_bp
    from app.routes.portfolio_metrics import metrics_bp
    # Register market_data blueprint if available (optional)
    try:
        from app.routes.market_data import market_bp
        app.register_blueprint(market_bp, url_prefix="/market")
    except ImportError:
        pass

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(portfolio_bp, url_prefix="/portfolio")
    app.register_blueprint(metrics_bp, url_prefix="/metrics")

    # Create database tables if they don't exist
    with app.app_context():
        db.create_all()

    return app
