import pandas as pd
import datetime as dt

def get_nifty_weekly_options():
    try:
        inst_df = pd.read_csv('https://api.kite.trade/instruments')
    except Exception as e:
        print(f"Error fetching instruments file: {e}")
        return pd.DataFrame()

    nifty_options_df = inst_df[
        (inst_df["name"] == "NIFTY") &
        (inst_df["segment"] == "NFO-OPT")
    ].copy()

    if nifty_options_df.empty:
        print("No NIFTY options found in instruments file.")
        return pd.DataFrame()

    nifty_options_df['expiry'] = pd.to_datetime(nifty_options_df['expiry'])
    today_dt_date = dt.date.today()

    expiries_today_or_later = [
        exp_dt for exp_dt in nifty_options_df['expiry'].unique()
        if pd.Timestamp(exp_dt).date() >= today_dt_date
    ]

    if not expiries_today_or_later:
        print("No NIFTY option expiries found for today or any future date.")
        return pd.DataFrame()

    try:
        selected_expiry_datetime = min(
            [pd.Timestamp(exp) for exp in expiries_today_or_later],
            key=lambda x: (x.date() - today_dt_date)
        )
    except ValueError:
        print("Error finding minimum expiry among valid dates.")
        return pd.DataFrame()
    
    print(f"Selected Expiry Date for Options: {selected_expiry_datetime.date()}")
    
    filtered_df = nifty_options_df[nifty_options_df['expiry'] == selected_expiry_datetime].copy()

    if filtered_df.empty:
        print(f"No options data found for the selected expiry: {selected_expiry_datetime.date()}.")
        
    return filtered_df

if __name__ == '__main__':
    options = get_nifty_weekly_options()
    if not options.empty:
        print(f"Found {len(options)} option instruments.")