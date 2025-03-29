# UML Use Case and Class Diagrams

## Use Case Diagram
**Actors:**
- Investor / Trader
- Administrator

**Use Cases:**
- Register/Login
- Input Portfolio (manual/CSV)
- View Risk/Return Metrics
- Upload/Manage Portfolios
- Fetch Market Data
- Analyze Portfolio
- Download Portfolio Reports

## Class Diagram (Simplified View)
```
+----------------+       +--------------------+       +----------------+
|     User       |       |    Portfolio       |       |   Asset        |
+----------------+       +--------------------+       +----------------+
| id             |1     *| id                 |1     *| id             |
| username       |-------| user_id            |-------| portfolio_id   |
| email          |       | name               |       | name           |
| password_hash  |       | created_at         |       | type           |
+----------------+       +--------------------+       | quantity       |
                                                  | purchase_price |
                                                  +----------------+

+----------------+  
| MarketData     |  
+----------------+  
| id             |  
| asset_name     |  
| asset_type     |  
| current_price  |  
| volatility     |  
| timestamp      |  
+----------------+
```