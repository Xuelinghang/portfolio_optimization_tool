# Portfolio Optimizer Dependencies

This document lists all the required packages for the Portfolio Optimizer application.

## Core Frameworks
- Flask
- Flask-SQLAlchemy
- Flask-JWT-Extended
- Flask-Bcrypt

## Data Processing and Analysis
- numpy
- pandas
- scipy

## Visualization
- matplotlib
- plotly

## Financial Data APIs
- yfinance
- alpha-vantage

## Scheduling and Background Tasks
- APScheduler

## Web Content Extraction
- trafilatura

## Environment Management
- python-dotenv

## HTTP Requests
- requests

## Installation

These packages are already installed in the current environment. If you need to recreate this environment elsewhere, you can install these packages using pip:

```bash
pip install Flask Flask-SQLAlchemy Flask-JWT-Extended Flask-Bcrypt numpy pandas scipy matplotlib plotly yfinance alpha-vantage APScheduler trafilatura python-dotenv requests
```

## API Keys
The application uses several external financial data APIs that require API keys:
- Yahoo Finance API
- Alpha Vantage API
- CoinGecko API
- FRED (Federal Reserve Economic Data) API

These API keys are already configured in the application environment. End users do not need to provide their own API keys, as the application uses centralized keys for all data fetching operations.