# Unit Test Suite Overview

## Tools
- pytest
- unittest.mock
- coverage (optional)

## Authentication Tests
- test_register_valid_user()
- test_login_invalid_password()

## Portfolio Data Validation
- test_csv_upload_parser()
- test_invalid_asset_format()

## Financial Metric Calculations
- test_calculate_sharpe_ratio()
- test_efficient_frontier_generation()

## Market Data Integration
- test_market_data_api_response()
- test_missing_symbol_handling()

## Run Tests
```bash
pytest tests/
```
