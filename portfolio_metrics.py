import numpy as np
import pandas as pd
import scipy.optimize as sco

# Sample portfolio returns (Use actual historical data)
np.random.seed(42)
dates = pd.date_range("2020-01-01", periods=252)  # 1-year daily returns
returns = pd.DataFrame(np.random.normal(0.0005, 0.01, size=(252, 4)), index=dates, columns=["Stock A", "Stock B", "Stock C", "Stock D"])

# Portfolio weights (Modify as needed)
weights = np.array([0.25, 0.25, 0.25, 0.25])

# Risk-free rate (assumed)
risk_free_rate = 0.02 / 252  # Daily risk-free rate

# Function to calculate expected return
def expected_return(returns, weights):
    return np.dot(weights, returns.mean()) * 252  # Annualized

# Function to calculate portfolio volatility
def portfolio_volatility(returns, weights):
    cov_matrix = returns.cov() * 252  # Annualized covariance matrix
    return np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))

# Function to calculate Sharpe ratio
def sharpe_ratio(returns, weights, risk_free_rate):
    exp_return = expected_return(returns, weights)
    volatility = portfolio_volatility(returns, weights)
    return (exp_return - risk_free_rate * 252) / volatility

# Function to calculate maximum drawdown
def max_drawdown(portfolio_values):
    cumulative_max = portfolio_values.cummax()
    drawdowns = (portfolio_values - cumulative_max) / cumulative_max
    return drawdowns.min()

# Function to calculate CAGR
def cagr(start_balance, end_balance, years):
    return (end_balance / start_balance) ** (1 / years) - 1

# Function to compute Efficient Frontier
def efficient_frontier(returns):
    num_assets = len(returns.columns)
    mean_returns = returns.mean() * 252
    cov_matrix = returns.cov() * 252

    def portfolio_stats(weights):
        port_return = np.dot(weights, mean_returns)
        port_volatility = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
        return np.array([port_return, port_volatility, port_return / port_volatility])

    def min_volatility(weights):
        return portfolio_stats(weights)[1]  # Minimize volatility

    constraints = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})  # Weights sum to 1
    bounds = tuple((0, 1) for _ in range(num_assets))  # No short-selling
    initial_weights = np.array(num_assets * [1.0 / num_assets])

    result = sco.minimize(min_volatility, initial_weights, method="SLSQP", bounds=bounds, constraints=constraints)
    return result.x  # Optimal weights

# Compute Metrics
start_balance = 10000
end_balance = start_balance * (1 + expected_return(returns, weights))
years = len(returns) / 252

metrics = {
    "Start Balance": start_balance,
    "End Balance": round(end_balance, 2),
    "Annualized Return (CAGR)": round(cagr(start_balance, end_balance, years) * 100, 2),
    "Standard Deviation": round(portfolio_volatility(returns, weights) * 100, 2),
    "Best Year": round(returns.mean().max() * 252 * 100, 2),
    "Worst Year": round(returns.mean().min() * 252 * 100, 2),
    "Maximum Drawdown": round(max_drawdown((1 + returns.mean()).cumprod()) * 100, 2),
    "Sharpe Ratio": round(sharpe_ratio(returns, weights, risk_free_rate), 2),
}

print(metrics)
