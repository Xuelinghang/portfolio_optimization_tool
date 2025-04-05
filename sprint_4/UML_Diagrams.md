# UML Diagrams

## Use Case Diagram

**Actors:**
- User (Investor/Trader)
- Admin

**Use Cases:**
- Register/Login
- Upload Portfolio (Manual/CSV)
- View Portfolio Analysis
- Fetch Market Data
- View Visualization
- Download Report

## Class Diagram (Simplified)

```
+-------------+       +--------------+       +----------+
|   User      |       |  Portfolio   |       |  Asset   |
+-------------+       +--------------+       +----------+
| id          |1     *| id           |1     *| id       |
| username    |-------| user_id      |-------| name     |
| email       |       | name         |       | type     |
| password    |       | created_at   |       | amount   |
+-------------+       +--------------+       +----------+

+------------------+
| MarketData       |
+------------------+
| id               |
| asset_name       |
| asset_type       |
| current_price    |
| volatility       |
| last_updated     |
+------------------+
```