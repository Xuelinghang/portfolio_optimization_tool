from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from datetime import datetime

# Initialize Flask app
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///portfolio.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JWT_SECRET_KEY"] = "your_secret_key"  # Change this in production

# Initialize extensions
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
jwt = JWTManager(app)

# User Model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(100), nullable=False)

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

# Asset Model
class Asset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(10), nullable=False)
    asset_type = db.Column(db.String(10), nullable=False)  # Stock, ETF, Bond, Crypto
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    user = db.relationship("User", backref=db.backref("assets", lazy=True))

# Portfolio Model
class Portfolio(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    asset_id = db.Column(db.Integer, db.ForeignKey("asset.id"), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    purchase_price = db.Column(db.Float, nullable=False)
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship("User", backref=db.backref("portfolio", lazy=True))
    asset = db.relationship("Asset", backref=db.backref("portfolio", lazy=True))

# Market Data Model
class MarketData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("asset.id"), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    price = db.Column(db.Float, nullable=False)
    asset = db.relationship("Asset", backref=db.backref("market_data", lazy=True))

# Create tables
with app.app_context():
    db.create_all()

# --------------------------- AUTHENTICATION ---------------------------

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if User.query.filter_by(username=username).first():
        return jsonify({"message": "User already exists"}), 400

    new_user = User(username=username)
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()

    return jsonify({"message": "User registered successfully"}), 201

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    user = User.query.filter_by(username=username).first()

    if user and user.check_password(password):
        access_token = create_access_token(identity=user.id)
        return jsonify({"access_token": access_token}), 200
    else:
        return jsonify({"message": "Invalid credentials"}), 401

# --------------------------- PORTFOLIO MANAGEMENT ---------------------------

@app.route("/assets", methods=["POST"])
@jwt_required()
def add_asset():
    data = request.get_json()
    user_id = get_jwt_identity()
    symbol = data.get("symbol")
    asset_type = data.get("asset_type")

    new_asset = Asset(symbol=symbol, asset_type=asset_type, user_id=user_id)
    db.session.add(new_asset)
    db.session.commit()

    return jsonify({"message": "Asset added successfully"}), 201

@app.route("/portfolio", methods=["POST"])
@jwt_required()
def add_to_portfolio():
    data = request.get_json()
    user_id = get_jwt_identity()
    asset_id = data.get("asset_id")
    quantity = data.get("quantity")
    purchase_price = data.get("purchase_price")

    new_portfolio_entry = Portfolio(
        user_id=user_id, asset_id=asset_id, quantity=quantity, purchase_price=purchase_price
    )
    db.session.add(new_portfolio_entry)
    db.session.commit()

    return jsonify({"message": "Asset added to portfolio"}), 201

@app.route("/portfolio", methods=["GET"])
@jwt_required()
def get_portfolio():
    user_id = get_jwt_identity()
    portfolio = Portfolio.query.filter_by(user_id=user_id).all()

    portfolio_data = [
        {"id": entry.id, "asset_symbol": entry.asset.symbol, "quantity": entry.quantity, "purchase_price": entry.purchase_price}
        for entry in portfolio
    ]
    
    return jsonify(portfolio_data), 200

# --------------------------- MARKET DATA ---------------------------

@app.route("/market_data", methods=["POST"])
@jwt_required()
def add_market_data():
    data = request.get_json()
    asset_id = data.get("asset_id")
    price = data.get("price")

    new_market_data = MarketData(asset_id=asset_id, price=price)
    db.session.add(new_market_data)
    db.session.commit()

    return jsonify({"message": "Market data added successfully"}), 201

@app.route("/market_data/<asset_id>", methods=["GET"])
@jwt_required()
def get_market_data(asset_id):
    market_data = MarketData.query.filter_by(asset_id=asset_id).all()
    market_data_list = [{"date": entry.date.strftime("%Y-%m-%d"), "price": entry.price} for entry in market_data]

    return jsonify(market_data_list), 200

# Run the app
if __name__ == "__main__":
    app.run(debug=True)
