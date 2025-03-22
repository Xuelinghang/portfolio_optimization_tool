
# Portfolio Optimizer

A web-based investment tool that allows users to register, log in, and retrieve real-time market data from multiple sources such as **Yahoo Finance**, **Alpha Vantage**, and **CoinGecko**. Built with **Flask (Python)** as the backend and plain **HTML/CSS/JavaScript** as the frontend.

---

## Features

- Secure user registration and login with bcrypt password hashing
- SQLite database to store user credentials (`users.db`)
- Flask backend with `/register` and `/login` endpoints
- CORS enabled for frontend-backend communication
- Real-time market data retrieval:
  - Yahoo Finance (stocks, ETFs, mutual funds)
  - Alpha Vantage (stocks, bonds)
  - CoinGecko (crypto)

---

##  Project Structure

portfolio_optimizer/
├── auth.py               # Flask backend with login/register API
├── market_data.py        # Python script to fetch market data
├── users.db              # SQLite database (auto-created)
├── register.html         # User registration page
├── login.html            # User login page
├── data-entry.html       # (Optional) dashboard after login
├── logo.jpeg             # Logo image used in frontend
└── README.md             # Project documentation

---

##  Setup Instructions

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/portfolio-optimizer.git
cd portfolio-optimizer

2. Create and Activate a Virtual Environment

python3 -m venv venv
source venv/bin/activate    

3. Install Dependencies

pip install flask flask-cors bcrypt yfinance alpha_vantage requests



⸻

▶Start the Flask Backend

python auth.py

Make sure you see:

Running on http://0.0.0.0:5001/



⸻

Start the Frontend

Option 1: Python HTTP Server

In another terminal:

python -m http.server 8080

Then open in your browser:

http://127.0.0.1:8080/register.html
http://127.0.0.1:8080/login.html

Option 2: VS Code Live Server
	•	Install the Live Server extension in VS Code
	•	Right-click register.html → “Open with Live Server”

⸻

Flask API Endpoints

Method	Endpoint	Description
POST	/register	Register new user
POST	/login	Authenticate user login

All requests should use Content-Type: application/json.

⸻

Market Data (market_data.py)

Use market_data.py to fetch financial data from:
	•	Yahoo Finance – stocks, ETFs, mutual funds
	•	Alpha Vantage – stocks & treasury bond yields
	•	CoinGecko – cryptocurrency prices

To use Alpha Vantage, add your API key:

ALPHA_VANTAGE_API_KEY = "your_api_key_here"

Run:

python market_data.py



⸻

Security
	•	Passwords are never stored in plain text — they’re hashed with bcrypt
	•	Backend input is validated and sanitized
	•	CORS enabled for frontend-backend development flow

⸻

Example Workflow
	1.	Run Flask server: python auth.py
	2.	Serve the frontend: python -m http.server 8080
	3.	Open browser: http://127.0.0.1:8080/register.html
	4.	Register a new user
	5.	Check SQLite DB:

sqlite3 users.db
sqlite> SELECT * FROM users;



⸻

Future Enhancements
	•	Add dashboard after login to show market trends
	•	Visualize portfolio performance
	•	Integrate portfolio optimization algorithms
	•	Add logout and session handling (JWT or Flask sessions)


