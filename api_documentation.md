# Portfolio Optimizer - API Documentation

This document outlines the internal API endpoints available in the Portfolio Optimizer application, primarily for developers who wish to understand the system architecture or extend the application.

## Authentication Endpoints

### Register User
- **URL**: `/register`
- **Method**: `POST`
- **Body**:
  ```json
  {
    "username": "string",
    "email": "string",
    "password": "string"
  }
  ```
- **Response**: Returns user details and authentication token

### Login
- **URL**: `/login`
- **Method**: `POST`
- **Body**:
  ```json
  {
    "username": "string",
    "password": "string"
  }
  ```
- **Response**: Returns authentication token and user details

### Logout
- **URL**: `/logout`
- **Method**: `POST`
- **Authentication**: Requires valid JWT token
- **Response**: Confirmation of logout

## Portfolio Management Endpoints

### Save Portfolio
- **URL**: `/save-portfolio`
- **Method**: `POST`
- **Authentication**: Requires valid JWT token
- **Body**:
  ```json
  {
    "portfolio_name": "string",
    "portfolio_data": "json_string"
  }
  ```
- **Response**: Confirmation of portfolio save with portfolio ID

### Get All Portfolios
- **URL**: `/saved-portfolios`
- **Method**: `GET`
- **Authentication**: Requires valid JWT token
- **Response**: List of all saved portfolios for the authenticated user

### Get Portfolio by ID
- **URL**: `/portfolio/<portfolio_id>`
- **Method**: `GET`
- **Authentication**: Requires valid JWT token
- **Response**: Complete portfolio data including assets and performance metrics

### Update Portfolio
- **URL**: `/update-portfolio/<portfolio_id>`
- **Method**: `POST`
- **Authentication**: Requires valid JWT token
- **Body**:
  ```json
  {
    "portfolio_name": "string",
    "portfolio_data": "json_string"
  }
  ```
- **Response**: Confirmation of portfolio update

### Delete Portfolio
- **URL**: `/delete-portfolio/<portfolio_id>`
- **Method**: `POST`
- **Authentication**: Requires valid JWT token
- **Response**: Confirmation of portfolio deletion

### Download Portfolio
- **URL**: `/download-portfolio/<portfolio_id>`
- **Method**: `GET`
- **Authentication**: Requires valid JWT token
- **Query Parameters**:
  - `format`: `csv` or `json` (default: `csv`)
- **Response**: File download with portfolio data

## Portfolio Analysis Endpoints

### Calculate Portfolio Metrics
- **URL**: `/portfolio-metrics/<portfolio_id>`
- **Method**: `GET`
- **Authentication**: Requires valid JWT token
- **Response**: Comprehensive portfolio metrics including:
  - Performance metrics (CAGR, Sharpe ratio, etc.)
  - Risk metrics
  - Asset allocation
  - Historical performance data

## Market Data Endpoints

### Get All Market Data
- **URL**: `/api/market-data`
- **Method**: `GET`
- **Authentication**: Requires valid JWT token
- **Response**: Current market data for all assets

### Get Market Data by Asset
- **URL**: `/api/market-data/<asset_id>`
- **Method**: `GET`
- **Authentication**: Requires valid JWT token
- **Response**: Historical market data for the specified asset

### Add Market Data
- **URL**: `/api/market-data`
- **Method**: `POST`
- **Authentication**: Requires valid JWT token
- **Body**:
  ```json
  {
    "asset_id": "integer",
    "price": "float",
    "date": "datetime string (optional)"
  }
  ```
- **Response**: Confirmation of market data addition

### Refresh Market Data
- **URL**: `/refresh-market-data`
- **Method**: `POST`
- **Authentication**: Requires valid JWT token
- **Response**: Confirmation of market data refresh

## Efficient Frontier Endpoints

### Calculate Efficient Frontier
- **URL**: `/efficient-frontier/calculate`
- **Method**: `POST`
- **Authentication**: Requires valid JWT token
- **Body**:
  ```json
  {
    "tickers": ["string"],
    "start_date": "YYYY-MM-DD",
    "end_date": "YYYY-MM-DD"
  }
  ```
- **Response**: Efficient frontier calculation results including:
  - Multiple portfolios along the efficient frontier
  - Tangency portfolio
  - Maximum information ratio portfolio
  - Equal weight portfolio
  - Asset metrics

## Data Entry Endpoints

### Manual Asset Entry
- **URL**: `/submit-manual-entry`
- **Method**: `POST`
- **Authentication**: Requires valid JWT token
- **Body**:
  ```json
  {
    "symbol": "string",
    "asset_type": "string",
    "quantity": "float",
    "purchase_price": "float (optional)",
    "purchase_date": "YYYY-MM-DD (optional)"
  }
  ```
- **Response**: Confirmation of asset addition

### Upload CSV
- **URL**: `/upload-csv`
- **Method**: `POST`
- **Authentication**: Requires valid JWT token
- **Body**: Form data with CSV file
- **Response**: Parsed portfolio data from CSV

### Search Ticker
- **URL**: `/search-ticker`
- **Method**: `GET`
- **Query Parameters**:
  - `q`: Search query
- **Authentication**: Requires valid JWT token
- **Response**: List of matching ticker symbols and basic information

## Error Handling

All endpoints follow a consistent error response format:

```json
{
  "error": "string",
  "message": "string",
  "status_code": "integer"
}
```

Common error codes:
- `400`: Bad Request - Malformed request or invalid parameters
- `401`: Unauthorized - Missing or invalid authentication
- `403`: Forbidden - Insufficient permissions
- `404`: Not Found - Resource not found
- `500`: Internal Server Error - Unexpected server error

## API Usage Notes

- All endpoints require authentication except the login and register endpoints
- JWT tokens should be included in the Authorization header as `Bearer <token>`
- All responses are in JSON format except for file downloads
- Dates should be provided in ISO format (YYYY-MM-DD)
- The API enforces rate limiting to prevent abuse
- The application uses centralized API keys for all external financial data services - users do not need to provide their own API keys
- Yahoo Finance is the primary data source (with 15-20 minute delay), with Alpha Vantage as a backup source