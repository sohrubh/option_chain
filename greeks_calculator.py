import numpy as np
from scipy.stats import norm
import datetime


RISK_FREE_RATE = 0.06  # 6% risk-free rate
TRADING_DAYS_PER_YEAR = 252
HOURS_IN_TRADING_DAY = 6.25 #9:15 AM to 3:30 PM
MINUTES_IN_TRADING_DAY = HOURS_IN_TRADING_DAY * 60
SECONDS_IN_TRADING_DAY = MINUTES_IN_TRADING_DAY * 60

def time_to_expiry_in_years(expiry_datetime, current_datetime):
    if expiry_datetime.date() < current_datetime.date():
        return 0 # Expired

    market_close_time = datetime.time(15, 30, 0)
    
    exact_expiry_moment = datetime.datetime.combine(expiry_datetime.date(), market_close_time)

    if current_datetime >= exact_expiry_moment:
        return 0 # Expired or at expiry

    time_delta = exact_expiry_moment - current_datetime
    
    total_seconds_in_year = 365.25 * 24 * 60 * 60
    
    t = time_delta.total_seconds() / total_seconds_in_year
    return max(t, 1e-6)

# Black-Scholes
def d1_d2(S, K, T, r, sigma):
    if T <= 0 or sigma <=0:
        return np.nan, np.nan

    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return d1, d2

def black_scholes_price(S, K, T, r, sigma, option_type="call"):
    if T <= 1e-6 or sigma <= 1e-6 : # Effectively expired or no volatility
        if option_type == "call":
            return max(0, S - K)
        else: # put
            return max(0, K - S)
            
    d1, d2 = d1_d2(S, K, T, r, sigma)
    if np.isnan(d1):
        if option_type == "call": return max(0, S-K)
        else: return max(0, K-S)

    if option_type == "call":
        price = (S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2))
    elif option_type == "put":
        price = (K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))
    else:
        raise ValueError("option_type must be 'call' or 'put'")
    return price

# Greeks Formulas
def delta(S, K, T, r, sigma, option_type="call"):
    if T <= 1e-6: return 1.0 if S > K and option_type=="call" else (-1.0 if S < K and option_type=="put" else 0.0)
    if sigma <= 1e-6: return 1.0 if S > K and option_type=="call" else (-1.0 if S < K and option_type=="put" else 0.0)

    d1, _ = d1_d2(S, K, T, r, sigma)
    if np.isnan(d1): return np.nan

    if option_type == "call":
        return norm.cdf(d1)
    elif option_type == "put":
        return norm.cdf(d1) - 1
    return np.nan

def vega(S, K, T, r, sigma): 
    if T <= 1e-6 or sigma <= 1e-6: return 0.0
    d1, _ = d1_d2(S, K, T, r, sigma)
    if np.isnan(d1): return np.nan
    return S * norm.pdf(d1) * np.sqrt(T) * 0.01

def theta(S, K, T, r, sigma, option_type="call"):
    if T <= 1e-6 or sigma <= 1e-6: return 0.0
    d1, d2 = d1_d2(S, K, T, r, sigma)
    if np.isnan(d1): return np.nan

    p1 = - (S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T))
    if option_type == "call":
        p2 = r * K * np.exp(-r * T) * norm.cdf(d2)
        return (p1 - p2) / 365.25
    elif option_type == "put":
        p2 = r * K * np.exp(-r * T) * norm.cdf(-d2)
        return (p1 + p2) / 365.25
    return np.nan

# Implied Volatility Calculation (Newton-Raphson)
def implied_volatility(market_price, S, K, T, r, option_type="call", initial_sigma=0.5, max_iterations=100, tolerance=1e-5):
    if T <= 1e-6 : return 0.0 
    if market_price <=0: return 0.0

    sigma = initial_sigma
    for i in range(max_iterations):
        price_at_sigma = black_scholes_price(S, K, T, r, sigma, option_type)
        vega_at_sigma = S * norm.pdf(d1_d2(S, K, T, r, sigma)[0]) * np.sqrt(T)

        if vega_at_sigma < 1e-8: 
            if initial_sigma > 0.2:
                return implied_volatility(market_price, S, K, T, r, option_type, 0.1, 20, tolerance)
            return np.nan

        diff = price_at_sigma - market_price
        if abs(diff) < tolerance:
            return sigma
        
        sigma = sigma - diff / vega_at_sigma
        
        sigma = max(0.001, min(sigma, 5.0))

    return sigma

# Main Calculation
def calculate_all_greeks(market_price, S, K, expiry_datetime, current_datetime, option_type="call"):
    greeks = {'iv': np.nan, 'delta': np.nan, 'theta': np.nan, 'vega': np.nan}
    
    T = time_to_expiry_in_years(expiry_datetime, current_datetime)
    r = RISK_FREE_RATE

    if T <= 1e-6 or S <= 0 or K <= 0 or market_price < 0: 
        if T <= 1e-6:
            greeks['iv'] = 0.0
            greeks['vega'] = 0.0
            greeks['theta'] = 0.0
            if option_type == "call":
                greeks['delta'] = 1.0 if S > K else 0.0
            else: # put
                greeks['delta'] = -1.0 if S < K else 0.0
        return greeks

    # 1. Calculate Implied Volatility
    iv = implied_volatility(market_price, S, K, T, r, option_type)
    if np.isnan(iv) or iv <= 0:
        return greeks 
    greeks['iv'] = iv

    # 2. Calculate other Greeks using the found IV
    greeks['delta'] = delta(S, K, T, r, iv, option_type)
    greeks['theta'] = theta(S, K, T, r, iv, option_type)
    greeks['vega'] = vega(S, K, T, r, iv)

    return greeks

if __name__ == '__main__':
    print("working ..")