1. Functional Requirements
    - User Authentication & Authorization: Users can sign up, log in, reset passwords, and manage profiles. Admins can manage user roles
    - Portfolio Input: Users can input assets manually (symbol, quantity, type) or upload CSV files.
    - Real-Time Data Integration: Fetch live/historical data for stocks (Yahoo Finance), crypto (CoinGecko), and ETFs (Alpha Vantage)
    - Financial Metrics Calculation: Compute Efficient Frontier, Sharpe Ratio, volatility, and expected returns using PyPortfolioOpt
    - Interactive Visualization: Display risk-return metrics via dynamic charts (Efficient Frontier, Sharpe Ratio heatmaps).
    - Portfolio Comparison: Compare multiple portfolios side-by-side with metrics and visualizations.
    - Portfolio Optimization: Suggest optimal asset allocations based on risk tolerance and return objectives.
    - Admin Dashboard: Admins can manage API keys, user accounts, data sources, and system logs.
    - Export/Download Reports: Users can download PDF/CSV reports summarizing portfolio analysis.
    - Scenario Modeling	Simulate: "what-if" scenarios (e.g., adding/removing assets, adjusting weights).
2. Non-Functional Requirements
    - Performance: Portfolio calculations complete within ≤2 seconds. API response times <500ms for non-computational requests.
    - Security: JWT-based authentication with HTTPS. Encrypted user data (AES-256) and hashed passwords (bcrypt). Rate limiting (100 requests/minute/user).
    - Scalability: Support 1,000+ concurrent users with horizontal scaling (Django + Celery workers). Redis caching for market data (5-minute TTL).
    - Usability: Mobile-responsive UI with tooltips for financial terms (e.g., "What is the Sharpe Ratio?"). Intuitive drag-and-drop CSV upload and interactive chart controls.
    - Reliability: 99.9% uptime with redundant cloud servers. Retry logic for failed API calls to external data providers (3 attempts).
    - Compliance: GDPR compliance for EU users. Audit trails for admin actions.
    - Maintainability: Modular codebase with OpenAPI/Swagger documentation. Automated CI/CD pipelines (GitLab) for testing and deployment.