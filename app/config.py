# app/config.py

import os
from dotenv import load_dotenv

load_dotenv()
basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'default_secret_key')

    database_url = os.getenv('DATABASE_URL')
    if database_url and database_url.startswith('sqlite:///'):
        relative_path = database_url.replace('sqlite:///', '')
        absolute_path = os.path.join(basedir, relative_path)
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{absolute_path}"
    else:
        SQLALCHEMY_DATABASE_URI = database_url

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ← Make sure this is present exactly like this:
    COMMON_TICKERS = [
        'AAPL','MSFT','GOOG','AMZN','TSLA',
        'SPY','QQQ','IWM','TLT','GLD',
        'NVDA','META','BRK.A','JPM','V',
        'JNJ','UNH','XOM','PG','AMD',
        'INTC','CRM','ADBE','PYPL','NFLX',
        'DIS','KO','PEP','T','F',
        'GM','BA','GE','VOO','IVV',
        'VTI','AGG','BND','HYG','LQD',
        'GOVT','SHY','IEF','VCIT','VCLT',
        'MUB','BTC','ETH','USDT','USDC',
        'XRP','SOL','BNB','DOGE','ADA',
        'TRX'
    ]
     # ─── Mail settings ──────────────────────────────────────────────────────
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'True').lower() in ('true', '1', 'yes')
    MAIL_USERNAME       = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD       = os.getenv('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = (
        os.getenv('MAIL_DEFAULT_NAME', 'Portfolio Optimizer'),
        os.getenv('MAIL_USERNAME')
    )
    # ───────────────────────────────────────────────────────────────────────
