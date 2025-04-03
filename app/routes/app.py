import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv

# Load environment variables from .env (if available)
load_dotenv()

app = Flask(__name__, static_folder="static", template_folder="templates")

# App Configuration
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///portfolio.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = os.path.join(os.getcwd(), "uploads")
# Set a secret key for session management (change in production!)
app.secret_key = os.getenv("SECRET_KEY", "super_secret_key")

# Ensure the uploads folder exists
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# Initialize extensions
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# ---------------- REGISTER BLUEPRINTS ----------------
from app.routes.auth import auth_bp
from app.routes.portfolio_api import portfolio_bp
from app.routes.portfolio_metrics import metrics_bp
from app.routes.market_data import market_bp  # Optional

app.register_blueprint(auth_bp, url_prefix="/auth")
app.register_blueprint(portfolio_bp, url_prefix="/portfolio")
app.register_blueprint(metrics_bp, url_prefix="/metrics")
app.register_blueprint(market_bp, url_prefix="/market")  # Optional

# ---------------- MAIN ENTRY POINT ----------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
<<<<<<< HEAD


=======
>>>>>>> 9238b7bd13e3228f275e5e1ae5ab4e4dcc7d9b6a
