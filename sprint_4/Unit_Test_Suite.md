# Unit Test Suite

## Frameworks
- pytest
- unittest.mock

## Test Areas

### 1. Authentication
- test_user_registration_valid
- test_user_login_invalid_password
- test_jwt_token_generation

### 2. Portfolio Handling
- test_upload_csv_valid
- test_add_asset_manual_entry
- test_invalid_csv_format

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
