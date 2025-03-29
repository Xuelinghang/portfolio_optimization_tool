# Database Schema Diagram

## Tables Overview

### Users
- user_id (PK)
- username
- email
- password_hash
- created_at

### Portfolios
- portfolio_id (PK)
- user_id (FK → Users)
- portfolio_name
- created_at
- last_updated

### Assets
- asset_id (PK)
- portfolio_id (FK → Portfolios)
- asset_name
- asset_type
- quantity
- purchase_price
- purchase_date

### Market_Data
- market_id (PK)
- asset_name
- asset_type
- current_price
- price_change
- volatility
- last_updated

### Portfolio_Analysis
- analysis_id (PK)
- portfolio_id (FK → Portfolios)
- expected_return
- volatility
- sharpe_ratio
- efficient_frontier (JSON/text)
- created_at
