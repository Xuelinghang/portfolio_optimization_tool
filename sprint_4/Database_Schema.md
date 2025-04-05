# Database Schema

## Tables

### Users
- id (PK)
- username
- email
- password_hash

### Portfolios
- id (PK)
- user_id (FK → Users)
- name
- created_at

### Assets
- id (PK)
- portfolio_id (FK → Portfolios)
- name
- type (stock, crypto, bond, fund, ETF)
- amount
- purchase_price
- purchase_date

### MarketData
- id (PK)
- asset_name
- asset_type
- current_price
- volatility
- last_updated

### AnalysisResults
- id (PK)
- portfolio_id (FK → Portfolios)
- sharpe_ratio
- expected_return
- volatility
- efficient_frontier_data (JSON)
