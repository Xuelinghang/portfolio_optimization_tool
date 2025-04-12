# Unit Test Suite

## Frameworks
- pytest
- unittest.mock

## Test Areas

### 1. Authentication
- test_user_registration_valid
- test_user_login_invalid_password

### 2. Portfolio Handling
- test_upload_csv_valid
- test_add_asset_manual_entry
- test_invalid_csv_format
- test_invalid_ticker
- test_invalid_input

### 3. Financial Metrics
- test_calculate_sharpe_ratio
- test_expected_return_accuracy
- test_volatility_computation

### 4. Market Data
- test_fetch_market_data_mocked
- test_asset_not_found_response

### Run Tests
```bash
pytest tests/
```

import unittest
import json
from app import create_app, db
from app.models import User, Portfolio, Asset, MarketData, Transaction

class PortfolioTestCase(unittest.TestCase):
    def setUp(self):
        # Create test application and configure in-memory SQLite DB for testing
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_user_registration_and_login(self):
        # Test registration
        response = self.client.post(
            '/register',
            data=json.dumps({
                'username': 'testuser',
                'email': 'test@example.com',
                'password': 'password123'
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 201)
        
        # Test login with username
        response = self.client.post(
            '/login',
            data=json.dumps({
                'username': 'testuser',
                'password': 'password123'
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['username'], 'testuser')

    def test_create_portfolio(self):
        # Register and log in a user
        self.client.post(
            '/register',
            data=json.dumps({
                'username': 'user2',
                'email': 'user2@example.com',
                'password': 'password'
            }),
            content_type='application/json'
        )
        self.client.post(
            '/login',
            data=json.dumps({
                'username': 'user2',
                'password': 'password'
            }),
            content_type='application/json'
        )
        
        # Create a portfolio
        portfolio_data = [
            {'ticker': 'AAPL', 'allocation': 0.5},
            {'ticker': 'GOOG', 'allocation': 0.5}
        ]
        response = self.client.post(
            '/save-portfolio',
            data=json.dumps({
                'portfolioName': 'Test Portfolio',
                'portfolioData': portfolio_data
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.data)
        self.assertIn('portfolio_id', data)

    def test_transaction_creation(self):
        # Register, login, and create a portfolio, then create a transaction.
        self.client.post(
            '/register',
            data=json.dumps({
                'username': 'user3',
                'email': 'user3@example.com',
                'password': 'password'
            }),
            content_type='application/json'
        )
        self.client.post(
            '/login',
            data=json.dumps({
                'username': 'user3',
                'password': 'password'
            }),
            content_type='application/json'
        )
        # Create portfolio first
        portfolio_data = [
            {'ticker': 'MSFT', 'allocation': 1.0}
        ]
        port_response = self.client.post(
            '/save-portfolio',
            data=json.dumps({
                'portfolioName': 'Test Portfolio 3',
                'portfolioData': portfolio_data
            }),
            content_type='application/json'
        )
        port_data = json.loads(port_response.data)
        portfolio_id = port_data.get('portfolio_id')
        self.assertIsNotNone(portfolio_id)
        
        # Create an Asset for the transaction
        with self.app.app_context():
            from app.models import Asset
            asset = Asset(symbol='MSFT', asset_type='Stock', user_id=1)
            db.session.add(asset)
            db.session.commit()
            asset_id = asset.id
        
        transaction_data = {
            'user_id': 1,  # typically set from the session
            'asset_id': asset_id,
            'portfolio_id': portfolio_id,
            'transaction_type': 'buy',
            'quantity': 10,
            'price': 250.0,
            'fees': 5.0,
            'notes': 'Initial buy'
        }
        # Use the appropriate endpoint for transactions
        response = self.client.post(
            '/transactions/',
            data=json.dumps(transaction_data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)  # or 201, depending on implementation

if __name__ == '__main__':
    unittest.main()