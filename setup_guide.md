# Portfolio Optimizer - Setup Guide

This guide provides detailed instructions for setting up and running the Portfolio Optimizer application.

## Prerequisites

### Python
- Python 3.8 or higher is required
- pip (Python package installer)

### API Keys
The application uses API keys for the following services:
- [Alpha Vantage](https://www.alphavantage.co/support/#api-key)
- [FRED Economic Data](https://fred.stlouisfed.org/docs/api/api_key.html)
- [Yahoo Finance](https://www.yahoofinanceapi.com/)
- [CoinGecko](https://www.coingecko.com/en/api/documentation)

**Note**: API keys are already configured in the application environment. End users do not need to provide their own API keys, as the system uses centralized keys for all data fetching operations.

## Installation Steps

### 1. Clone the Repository
```bash
git clone <repository-url>
cd portfolio-optimizer
```

### 2. Create and Activate Virtual Environment (Optional but Recommended)
```bashs
# On Windows
python -m venv venv
venv\Scripts\activate

# On macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
All required packages are listed in the `dependencies.md` file. Install them using pip:

```bash
pip install Flask Flask-SQLAlchemy Flask-JWT-Extended Flask-Bcrypt numpy pandas scipy matplotlib plotly yfinance alpha-vantage APScheduler trafilatura python-dotenv requests
```

### 4. Environment Variables
The application is already configured with the necessary API keys. No additional configuration is required for end users.

If you're developing or deploying your own instance of the application, you would need to create a `.env` file with your own API keys, but this isn't necessary for using the existing application.

### 5. Initialize the Database
The application will automatically create the SQLite database on first run. No additional setup is required.

## Running the Application

### Development Mode
```bash
python run.py
```
The application will be available at http://localhost:5000

### Production Deployment
For production deployment, consider using a production-ready WSGI server like Gunicorn:

```bash
pip install gunicorn
gunicorn -w 4 "app:create_app()" -b 0.0.0.0:5000
```

## Application Structure

### Key Directories
- `app/`: Main application code
  - `models.py`: Database models
  - `market_fetcher.py`: Financial API integrations
  - `routes/`: Route handlers for different features
- `templates/`: HTML templates for the web interface
- `static/`: CSS, JavaScript, and images
- `utils/`: Utility functions for data processing and visualization
- `instance/`: Database file (created automatically)

## Troubleshooting

### API Connection Issues
- Check your internet connection
- Some APIs have rate limits that may affect data retrieval
- If you experience persistent API issues, the system administrator may need to check the API keys

### Database Errors
- If you encounter database errors, try deleting the `instance/portfolio.db` file and restart the application to recreate it

### Missing Dependencies
- If you encounter import errors, ensure all packages listed in `dependencies.md` are installed

## Next Steps

After successful setup:
1. Register a user account
2. Create your first portfolio
3. Explore the analysis tools
4. Check out the Efficient Frontier tool for portfolio optimization

For more details on using the application, refer to the `README.md` file.