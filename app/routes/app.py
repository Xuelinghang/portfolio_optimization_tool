import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager
from dotenv import load_dotenv

# Load environment variables from .env (if available)
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# App Configuration
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///portfolio.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "super_secret_key")  # Replace in production
app.config["UPLOAD_FOLDER"] = os.path.join(os.getcwd(), "uploads")

# Ensure the uploads folder exists
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# Initialize extensions
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
jwt = JWTManager(app)

# ---------------- REGISTER BLUEPRINTS ----------------
# Note: Make sure your Blueprints are defined in their respective files.
from app.routes.auth import auth_bp
from app.routes.portfolio_api import portfolio_bp
from app.routes.portfolio_metrics import metrics_bp
from app.routes.market_data import market_bp  # Optional: if you have market data endpoints

app.register_blueprint(auth_bp, url_prefix="/auth")
app.register_blueprint(portfolio_bp, url_prefix="/portfolio")
app.register_blueprint(metrics_bp, url_prefix="/metrics")
app.register_blueprint(market_bp, url_prefix="/market")  # Optional

# ---------------- MAIN ENTRY POINT ----------------
if __name__ == "__main__":
    # Create database tables if they don't exist
    with app.app_context():
        db.create_all()
    app.run(debug=True)


from flask import Flask

app = Flask(__name__)

@app.route("/test")
def test():
    return "Test route works!"

if __name__ == "__main__":
    app.run(debug=True)
