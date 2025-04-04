# Portfolio Optimizer - Project Documentation

## Project Overview
The Portfolio Optimizer is a comprehensive financial analytics platform that combines advanced portfolio visualization with interactive market data insights. It's designed to empower individual investors with user-friendly financial tracking tools.

## Features

### Portfolio Management
- Create and save multiple investment portfolios
- Manual data entry for portfolio holdings
- CSV upload support for bulk data import
- Track portfolio performance over time

### Portfolio Analysis
- Detailed portfolio performance metrics
- Risk assessment tools
- Asset allocation visualization
- Performance tracking with historical data

### Advanced Tools
- Efficient Frontier analysis for optimal portfolio allocation
- Risk vs. return visualization
- Tangency portfolio calculation
- Maximum information ratio portfolio

### Market Data Integration
- Real-time and historical data from multiple sources:
  - Yahoo Finance
  - Alpha Vantage
  - FRED (Federal Reserve Economic Data)
  - CoinGecko (cryptocurrencies)
- Scheduled background data updates

## Technical Architecture

### Backend
- **Framework**: Flask
- **Database**: SQLAlchemy with SQLite
- **Authentication**: JWT-based authentication with Flask-JWT-Extended
- **Password Security**: BCrypt hashing via Flask-Bcrypt

### Data Processing
- **Libraries**: pandas, numpy, scipy
- **Scheduled Tasks**: APScheduler for background data updates

### Visualization
- **Libraries**: plotly, matplotlib
- **Chart Types**: Line charts, bar charts, pie charts, heatmaps, scatter plots

## Module Structure

### Core Modules
- **app/__init__.py**: Application factory and configuration
- **app/models.py**: Database models for users, assets, portfolios, and market data
- **app/market_fetcher.py**: API integration for financial data

### Routes
- **app/routes/auth.py**: User authentication and account management
- **app/routes/portfolio_api.py**: Portfolio creation and management
- **app/routes/portfolio_metrics.py**: Portfolio performance calculations
- **app/routes/efficient_frontier.py**: Portfolio optimization tools
- **app/routes/market_data.py**: Market data retrieval

### Utilities
- **utils/data_processing.py**: Data validation and processing
- **utils/financial_metrics.py**: Financial calculations
- **utils/visualizations.py**: Chart generation

## User Workflow
1. User registers/logs in
2. Creates a new portfolio (manual entry or CSV upload)
3. Views saved portfolios
4. Selects analysis tools:
   - Portfolio Analysis for performance metrics
   - Efficient Frontier for optimization
5. Views dashboards with interactive visualizations
6. Downloads or updates portfolio data

## API Dependencies
The application uses several external financial data APIs:
- Yahoo Finance API (primary data source with 15-20 minute delay)
- Alpha Vantage API (backup source)
- CoinGecko API (cryptocurrency data)
- FRED (Federal Reserve Economic Data) API (economic indicators)

**Note**: The application uses centralized API keys that are already configured. End users do not need to provide their own API keys.

## Setup and Deployment
1. Install dependencies listed in dependencies.md
2. The application already has API keys configured - no additional setup required
3. Run the application with `python run.py`
4. Access the web interface at http://localhost:5000