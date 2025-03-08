1. Class Design and Database Design
+----------------+          +---------------------+          +----------------+
|     User       |          |     Portfolio       |          |     Asset      |
+----------------+          +---------------------+          +----------------+
| user_id (PK)   |<-----1:M-| portfolio_id (PK)   |<-----1:M-| asset_id (PK)  |
| email          |          | user_id (FK)        |          | portfolio_id   |
| role           |          | name                |          | symbol         |
| hashed_password|          | created_at          |          | quantity       |
+----------------+          | updated_at          |          | purchase_price |
                            +---------------------+          +----------------+
                                     |                                  |
                                     |                                  | M:1
                                     |                                  |
                                     |          +---------------------+ |
                                     +--------->|   MarketData        |
                                                +---------------------+
                                                | symbol (PK)         |
                                                | price               |
                                                | timestamp           |
                                                | asset_type          |
                                                +---------------------+

User: Stores user credentials and roles (user, admin).
- Relationships: A user can create 1:M Portfolios.
Portfolio: Represents a collection of assets owned by a user.
- Relationships: Each portfolio belongs to 1 User. A portfolio contains 1:M Assets.
Asset: Represents individual holdings (e.g., stocks, crypto) in a portfolio.
- Relationships: Each asset references a MarketData entry via symbol (e.g., AAPL, BTC).
MarketData: Stores real-time or cached market data fetched from APIs (Yahoo Finance, CoinGecko, etc.).
- Attributes: symbol acts as a universal identifier (e.g., stock ticker, crypto symbol). asset_type distinguishes between stock, crypto, etc.
Key Relationships: User → Portfolio → Asset: Hierarchical ownership. Asset → MarketData: Assets reference market data by symbol to fetch live prices.

2. Architecture
Frontend: React.js (TypeScript) with Plotly/D3.js for interactive charts.
Backend: Django REST Framework (Python) for API logic.
Database: PostgreSQL (relational data) + Redis (caching).

3. APIs
Yahoo Finance API: Free access to historical stock prices, fundamentals, and market data.
Alpha Vantage: Free tier available, provides stock, forex, and cryptocurrency data.
CoinGecko API: Cryptocurrency market data, including price, volume, and historical trends.
Authentication:
    - POST /auth/login: Returns JWT token.
    - POST /auth/register: Creates a new user.
Portfolio Management:
    - POST /api/portfolios: Submit a portfolio (manual/CSV).
    - GET /api/portfolios/{id}/metrics: Returns Sharpe Ratio, Efficient Frontier, etc.
Market Data:
    - GET /api/market/{symbol}: Fetch cached price for a symbol.

4. Testing Approach
Unit Tests: 
    - Backend: pytest for financial calculations (e.g., Sharpe Ratio logic).
    - Frontend: Jest + React Testing Library for component rendering.

5. Error Handling
- Input Validation:
    - Reject invalid symbols (e.g., XYZ123) or negative quantities.
    - Validate CSV formats (column headers, numeric values).
- Error Messaging:
    - User-friendly messages (e.g., "Invalid symbol: BTC not found").
    - Log errors with context (timestamp, user ID, affected endpoint) for debugging.
- Fallback Mechanisms:
    - Use cached market data if APIs are unavailable.
    - Graceful degradation (e.g., disable real-time updates during outages).