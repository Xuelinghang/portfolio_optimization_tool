import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize extensions
db = SQLAlchemy()
bcrypt = Bcrypt()

def create_app():
    # Determine the project root (one level up from the 'app' folder)
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    static_folder = os.path.join(project_root, 'static')
    template_folder = os.path.join(project_root, 'templates')
    
    # Create Flask app with absolute paths for static and templates folders
    app = Flask(__name__, static_folder=static_folder, template_folder=template_folder)
    
    # Application configuration
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///portfolio.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    # Set the secret key for session management
    app.secret_key = os.getenv("SECRET_KEY", "my_default_secret_key")
    
    # Initialize extensions with the app
    db.init_app(app)
    bcrypt.init_app(app)

    # Register Blueprints from the routes package.
    from app.routes.auth import auth_bp
    from app.routes.portfolio_api import portfolio_bp
    from app.routes.portfolio_metrics import metrics_bp
    try:
        from app.routes.market_data import market_bp
        app.register_blueprint(market_bp, url_prefix="/market")
    except ImportError:
        pass

    app.register_blueprint(auth_bp)  # Now routes like "/" or "/login-page" are at the root.
    app.register_blueprint(portfolio_bp, url_prefix="/portfolio")
    app.register_blueprint(metrics_bp, url_prefix="/metrics")

    # Create database tables if they don't exist
    with app.app_context():
        db.create_all()

    return app
