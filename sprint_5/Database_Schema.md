CREATE TABLE user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(100) NOT NULL
);
CREATE TABLE asset (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(10) NOT NULL,
    asset_type VARCHAR(10) NOT NULL,
    user_id INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES user(id)
);
CREATE TABLE portfolio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    portfolio_name VARCHAR(100) NOT NULL,
    portfolio_data TEXT,
    purchase_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES user(id)
);
CREATE TABLE market_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    date DATETIME DEFAULT CURRENT_TIMESTAMP,
    price FLOAT NOT NULL,
    FOREIGN KEY (asset_id) REFERENCES asset(id)
);
CREATE TABLE transaction (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    asset_id INTEGER NOT NULL,
    portfolio_id INTEGER NOT NULL,
    transaction_type VARCHAR(10) NOT NULL,
    quantity FLOAT NOT NULL,
    price FLOAT NOT NULL,
    transaction_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    fees FLOAT,
    notes TEXT,
    FOREIGN KEY (user_id) REFERENCES user(id),
    FOREIGN KEY (asset_id) REFERENCES asset(id),
    FOREIGN KEY (portfolio_id) REFERENCES portfolio(id)
);
