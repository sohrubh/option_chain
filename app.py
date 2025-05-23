import kiteapp as kt
import pandas as pd
from time import sleep
import datetime
import threading
from flask import Flask, jsonify, render_template_string, request
from instruments import get_nifty_weekly_options
import greeks_calculator 
import traceback
import numpy as np

ENCTOKEN_FILE = "enctoken.txt"
USER_ID = "ABC012"
API_KEY = "kite"
NIFTY_INDEX_TOKEN = 256265
DEFAULT_NUM_STRIKES_EACH_SIDE = 8
DEFAULT_MODE = 'ltpoi' 

option_chain_display_data = {}
nifty_spot_ltp = None
instrument_details_map = {} 
data_lock = threading.Lock()
subscribed_tokens_global_list = []

# KiteApp Setup
kite = None
kws = None
try:
    with open(ENCTOKEN_FILE, 'r') as rd:
        enctoken = rd.read().strip()
    kite = kt.KiteApp(API_KEY,USER_ID,enctoken)
    kws = kite.kws()
    print("KiteApp and KWS initialized.")
except Exception as e:
    print(f"CRITICAL: Error initializing KiteApp: {e}")
    traceback.print_exc()
    exit()

flask_app = Flask(__name__)

def initialize_data_and_subscriptions():
    global option_chain_display_data, instrument_details_map, subscribed_tokens_global_list
    print("Initializing data structures and subscriptions...")
    
    nifty_options_df = get_nifty_weekly_options()

    current_option_tokens = []
    temp_instrument_details = {}
    temp_strike_data_for_init = {}

    if not nifty_options_df.empty:
        # Ensure 'strike' column is integer type after reading
        nifty_options_df['strike'] = nifty_options_df['strike'].astype(int) # CHANGED TO INT
        nifty_options_df['expiry'] = pd.to_datetime(nifty_options_df['expiry'])

        for _, row in nifty_options_df.iterrows():
            token = int(row['instrument_token'])
            strike = int(row['strike']) # CHANGED TO INT
            opt_type = row['instrument_type']
            tradingsymbol = row['tradingsymbol']
            expiry_datetime = row['expiry'].to_pydatetime() if hasattr(row['expiry'], 'to_pydatetime') else row['expiry']

            current_option_tokens.append(token)
            temp_instrument_details[token] = {
                'tradingsymbol': tradingsymbol, 'strike': strike, # Strike stored as int
                'type': opt_type, 'expiry_datetime': expiry_datetime
            }
            if strike not in temp_strike_data_for_init:
                temp_strike_data_for_init[strike] = {}
            if opt_type == 'CE':
                temp_strike_data_for_init[strike]['call_token'] = token
                temp_strike_data_for_init[strike]['call_symbol'] = tradingsymbol
            elif opt_type == 'PE':
                temp_strike_data_for_init[strike]['put_token'] = token
                temp_strike_data_for_init[strike]['put_symbol'] = tradingsymbol
        print(f"Processed {len(current_option_tokens)} option instruments initially.")
    else:
        print("No NIFTY options loaded.")

    temp_option_chain_display = {}
    for strike, details in temp_strike_data_for_init.items(): # strike here is already int
        option_template = {
            'ltp': None, 'oi': None, 'volume': None, 'last_update_time': None,
            'iv': None, 'delta': None, 'theta': None, 'vega': None
        }
        temp_option_chain_display[strike] = {
            'strike': strike, # Stored as int
            'call': {**option_template, 'instrument_token': details.get('call_token'), 'tradingsymbol': details.get('call_symbol')},
            'put': {**option_template, 'instrument_token': details.get('put_token'), 'tradingsymbol': details.get('put_symbol')},
            'is_atm': False
        }

    with data_lock:
        option_chain_display_data = temp_option_chain_display
        instrument_details_map = temp_instrument_details
        subscribed_tokens_global_list = list(set(current_option_tokens))
        if NIFTY_INDEX_TOKEN not in subscribed_tokens_global_list:
             subscribed_tokens_global_list.append(NIFTY_INDEX_TOKEN)
    
    print(f"Total tokens to subscribe (incl. NIFTY Index): {len(subscribed_tokens_global_list)}.")

def on_ticks(ws, ticks):
    global option_chain_display_data, nifty_spot_ltp, instrument_details_map
    current_time_for_greeks = datetime.datetime.now()

    try:
        with data_lock: 
            for tick in ticks:
                token = tick.get('instrument_token')
                if token == NIFTY_INDEX_TOKEN:
                    nifty_spot_ltp = tick.get('last_price')
                    # print(f"NIFTY Spot Update: {nifty_spot_ltp}") 
                    continue 
                
                if token in instrument_details_map and nifty_spot_ltp is not None:
                    details = instrument_details_map[token]
                    strike_price = details['strike']
                    original_opt_type = details['type'] 
                    expiry_dt = details['expiry_datetime']
                    option_ltp = tick.get('last_price')

                    dict_key_for_option_type = None
                    greek_calc_option_type = None # 'call' or 'put' for calculator
                    if original_opt_type == 'CE':
                        dict_key_for_option_type = 'call'
                        greek_calc_option_type = 'call'
                    elif original_opt_type == 'PE':
                        dict_key_for_option_type = 'put'
                        greek_calc_option_type = 'put'
                    
                    if dict_key_for_option_type and strike_price in option_chain_display_data:
                        if dict_key_for_option_type in option_chain_display_data[strike_price]:
                            chain_entry = option_chain_display_data[strike_price][dict_key_for_option_type]
                            
                            chain_entry['ltp'] = option_ltp
                            chain_entry['oi'] = tick.get('oi')
                            chain_entry['volume'] = tick.get('volume_traded')
                            chain_entry['last_update_time'] = current_time_for_greeks.isoformat()

                            # Calculate Greeks if option_ltp is valid
                            if option_ltp is not None and option_ltp > 0 and nifty_spot_ltp > 0 :
                                try:
                                    calculated_greeks = greeks_calculator.calculate_all_greeks(
                                        market_price=option_ltp,
                                        S=nifty_spot_ltp,
                                        K=strike_price,
                                        expiry_datetime=expiry_dt,
                                        current_datetime=current_time_for_greeks,
                                        option_type=greek_calc_option_type
                                    )
                                    chain_entry['iv'] = calculated_greeks['iv'] if not np.isnan(calculated_greeks['iv']) else None
                                    chain_entry['delta'] = calculated_greeks['delta'] if not np.isnan(calculated_greeks['delta']) else None
                                    chain_entry['theta'] = calculated_greeks['theta'] if not np.isnan(calculated_greeks['theta']) else None
                                    chain_entry['vega'] = calculated_greeks['vega'] if not np.isnan(calculated_greeks['vega']) else None
                                except Exception as e_greek:
                                    chain_entry['iv'] = None; chain_entry['delta'] = None; chain_entry['theta'] = None; chain_entry['vega'] = None;
                            else: # If LTP is None or zero, or spot is None/zero, cannot calculate greeks
                                chain_entry['iv'] = None; chain_entry['delta'] = None; chain_entry['theta'] = None; chain_entry['vega'] = None;
    except Exception as e:
        print(f"Error in on_ticks: {e}")
        traceback.print_exc()

def on_connect(ws, response):
    print(f"WebSocket Connected. Response: {response}")
    global subscribed_tokens_global_list
    if subscribed_tokens_global_list:
        print(f"Subscribing to {len(subscribed_tokens_global_list)} tokens.")
        ws.subscribe(subscribed_tokens_global_list)
        ws.set_mode(ws.MODE_FULL, subscribed_tokens_global_list)
        print("Subscription and mode set commands sent.")
    else:
        print("No tokens to subscribe to in on_connect.")

def on_close(ws, code, reason):
    print(f"WebSocket Closed. Code: {code}, Reason: {reason}")

def on_error(ws, code, reason):
    print(f"WebSocket Error. Code: {code}, Reason: {reason}")

if kws:
    kws.on_ticks = on_ticks
    kws.on_connect = on_connect
    kws.on_close = on_close
    kws.on_error = on_error
else:
    print("CRITICAL: kws object is None. Cannot assign callbacks.")
    exit()

CHAIN_HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>NIFTY Option Chain</title>
    <style>
        body { font-family: Arial, sans-serif; } 
        table { border-collapse: collapse; width: 95%; margin: 10px auto; font-size: 0.9em; }
        th, td { border: 1px solid #ccc; text-align: center; padding: 5px; } 
        th { background-color: #e9ecef; }
        .strike-col { background-color: #f8f9fa; font-weight: bold; } 
        .call-side { background-color: #fff9f9; }
        .put-side { background-color: #f9f9ff; } 
        .atm-strike { background-color: #fff3cd; font-weight: bold; border: 2px solid #fadb5f;} 
        .header-calls { text-align: center; color: #c00; } 
        .header-puts { text-align: center; color: #007bff; }
        .data-na { color: #aaa; } 
        h1, h2, .controls, .mode-toggle { text-align: center; margin-bottom:10px; }
        .controls label, .controls input, .controls button, .mode-toggle a { margin: 0 5px; }
        .mode-toggle a { padding: 5px 10px; text-decoration: none; border: 1px solid #ccc; border-radius: 4px; }
        .mode-toggle a.active { background-color: #007bff; color: white; border-color: #007bff; }
    </style>
    <meta http-equiv="refresh" content="{{ refresh_interval }}">
</head>
<body>
    <h1>NIFTY Option Chain</h1>

    <div class="mode-toggle">
        Mode:
        <a href="/?mode=ltpoi&strikes_each_side={{ current_strikes_each_side }}" 
           class="{{ 'active' if current_mode == 'ltpoi' }}">LTP/OI</a>
        <a href="/?mode=greeks&strikes_each_side={{ current_strikes_each_side }}"
           class="{{ 'active' if current_mode == 'greeks' }}">Greeks</a>
    </div>

    <div class="controls">
        <form method="GET" action="/">
            <input type="hidden" name="mode" value="{{ current_mode }}">
            <label for="strikes_each_side">Strikes per side:</label>
            <input type="number" id="strikes_each_side" name="strikes_each_side" 
                   value="{{ current_strikes_each_side }}" min="1" max="50">
            <button type="submit">Update View</button>
        </form>
    </div>
    <h2>NIFTY Spot LTP: <span id="niftyLTP">{{ nifty_ltp if nifty_ltp is not none else 'N/A' }}</span></h2>
    <table>
        <thead>
            <tr>
                {% if current_mode == 'ltpoi' %}
                    <th colspan="3" class="header-calls">CALL</th> 
                    <th class="strike-col">Strike</th> 
                    <th colspan="3" class="header-puts">PUT</th>
                {% elif current_mode == 'greeks' %}
                    <th colspan="4" class="header-calls">CALL</th> 
                    <th class="strike-col">Strike</th> 
                    <th colspan="4" class="header-puts">PUT</th>
                {% endif %}
            </tr>
            <tr>
                {% if current_mode == 'ltpoi' %}
                    <th>Volume</th> <th>OI</th> <th>LTP</th> 
                    <th class="strike-col">Price</th> 
                    <th>LTP</th> <th>OI</th> <th>Volume</th>
                {% elif current_mode == 'greeks' %}
                    <th>IV</th> <th>Vega</th> <th>Delta</th> <th>Theta</th>
                    <th class="strike-col">Price</th> 
                    <th>Theta</th> <th>Delta</th> <th>Vega</th> <th>IV</th>
                {% endif %}
            </tr>
        </thead>
        <tbody>
            {% if not chain_view_data %}
            <tr><td colspan="{% if current_mode == 'ltpoi' %}7{% elif current_mode == 'greeks' %}9{% endif %}">No option data to display for the selected range or expiry.</td></tr>
            {% endif %}
            {% for strike_data in chain_view_data %}
            <tr class="{% if strike_data.is_atm %}atm-strike{% endif %}">
                {% if current_mode == 'ltpoi' %}
                    <td class="call-side{{ ' data-na' if strike_data.call.volume is none }}">{{ strike_data.call.volume if strike_data.call.volume is not none else 'N/A' }}</td>
                    <td class="call-side{{ ' data-na' if strike_data.call.oi is none }}">{{ strike_data.call.oi if strike_data.call.oi is not none else 'N/A' }}</td>
                    <td class="call-side{{ ' data-na' if strike_data.call.ltp is none }}">{{ strike_data.call.ltp if strike_data.call.ltp is not none else 'N/A' }}</td>
                {% elif current_mode == 'greeks' %}
                    <td class="call-side{{ ' data-na' if strike_data.call.iv is none }}">{{ "%.2f"|format(strike_data.call.iv) if strike_data.call.iv is not none else 'N/A' }}</td>
                    <td class="call-side{{ ' data-na' if strike_data.call.vega is none }}">{{ "%.4f"|format(strike_data.call.vega) if strike_data.call.vega is not none else 'N/A' }}</td>
                    <td class="call-side{{ ' data-na' if strike_data.call.delta is none }}">{{ "%.4f"|format(strike_data.call.delta) if strike_data.call.delta is not none else 'N/A' }}</td>
                    <td class="call-side{{ ' data-na' if strike_data.call.theta is none }}">{{ "%.4f"|format(strike_data.call.theta) if strike_data.call.theta is not none else 'N/A' }}</td>
                {% endif %}
                
                <td class="strike-col">{{ strike_data.strike }}</td>
                
                {% if current_mode == 'ltpoi' %}
                    <td class="put-side{{ ' data-na' if strike_data.put.ltp is none }}">{{ strike_data.put.ltp if strike_data.put.ltp is not none else 'N/A' }}</td>
                    <td class="put-side{{ ' data-na' if strike_data.put.oi is none }}">{{ strike_data.put.oi if strike_data.put.oi is not none else 'N/A' }}</td>
                    <td class="put-side{{ ' data-na' if strike_data.put.volume is none }}">{{ strike_data.put.volume if strike_data.put.volume is not none else 'N/A' }}</td>
                {% elif current_mode == 'greeks' %}
                    <td class="put-side{{ ' data-na' if strike_data.put.theta is none }}">{{ "%.4f"|format(strike_data.put.theta) if strike_data.put.theta is not none else 'N/A' }}</td>
                    <td class="put-side{{ ' data-na' if strike_data.put.delta is none }}">{{ "%.4f"|format(strike_data.put.delta) if strike_data.put.delta is not none else 'N/A' }}</td>
                    <td class="put-side{{ ' data-na' if strike_data.put.vega is none }}">{{ "%.4f"|format(strike_data.put.vega) if strike_data.put.vega is not none else 'N/A' }}</td>
                    <td class="put-side{{ ' data-na' if strike_data.put.iv is none }}">{{ "%.2f"|format(strike_data.put.iv) if strike_data.put.iv is not none else 'N/A' }}</td>
                {% endif %}
            </tr>
            {% endfor %}
        </tbody>
    </table>
</body>
</html>
"""

@flask_app.route('/')
def display_option_chain():
    current_mode = request.args.get('mode', DEFAULT_MODE).lower()
    if current_mode not in ['ltpoi', 'greeks']: 
        current_mode = DEFAULT_MODE

    try:
        num_strikes_param = int(request.args.get('strikes_each_side', DEFAULT_NUM_STRIKES_EACH_SIDE))
        if not (1 <= num_strikes_param <= 50):
            num_strikes_param = DEFAULT_NUM_STRIKES_EACH_SIDE
    except ValueError:
        num_strikes_param = DEFAULT_NUM_STRIKES_EACH_SIDE

    with data_lock:
        current_chain_data_dict = dict(option_chain_display_data) 
        current_nifty_ltp = nifty_spot_ltp

    atm_strike_val = None
    # Keys of current_chain_data_dict are now integers
    all_sorted_strike_keys = sorted([s for s in current_chain_data_dict.keys() if isinstance(s, int)])


    if current_nifty_ltp and all_sorted_strike_keys:
        # Ensure nifty_spot_ltp is float for comparison, strikes are int
        atm_strike_val = min(all_sorted_strike_keys, key=lambda s_int: abs(s_int - float(current_nifty_ltp)))


    display_strike_keys = []
    if atm_strike_val is not None and all_sorted_strike_keys: # Check atm_strike_val is not None
        try:
            atm_index = all_sorted_strike_keys.index(atm_strike_val)
            start_index = max(0, atm_index - num_strikes_param)
            end_index = min(len(all_sorted_strike_keys), atm_index + num_strikes_param + 1) 
            display_strike_keys = all_sorted_strike_keys[start_index:end_index]
        except ValueError: # atm_strike_val might not be in all_sorted_strike_keys if list is empty initially
            display_strike_keys = all_sorted_strike_keys 
    else:
        display_strike_keys = all_sorted_strike_keys
    
    chain_view_list = []
    for strike_val in display_strike_keys: # strike_val is already int
        if strike_val in current_chain_data_dict:
            data_for_strike = current_chain_data_dict[strike_val].copy() 
            data_for_strike['is_atm'] = True if atm_strike_val is not None and strike_val == atm_strike_val else False
            
            default_option_fields = {'ltp': None, 'oi': None, 'volume': None, 'iv': None, 'delta': None, 'theta': None, 'vega': None, 'tradingsymbol': 'N/A', 'instrument_token': None}
            if 'call' not in data_for_strike or not data_for_strike['call']:
                 data_for_strike['call'] = default_option_fields.copy()
            else: 
                for k, v in default_option_fields.items():
                    if k not in data_for_strike['call']: data_for_strike['call'][k] = v

            if 'put' not in data_for_strike or not data_for_strike['put']:
                data_for_strike['put'] = default_option_fields.copy()
            else: 
                for k, v in default_option_fields.items():
                    if k not in data_for_strike['put']: data_for_strike['put'][k] = v
            
            chain_view_list.append(data_for_strike)
    
    refresh_interval = 2 

    return render_template_string(CHAIN_HTML_TEMPLATE, 
                                  chain_view_data=chain_view_list, 
                                  nifty_ltp=current_nifty_ltp,
                                  current_strikes_each_side=num_strikes_param,
                                  current_mode=current_mode,
                                  refresh_interval=refresh_interval)

@flask_app.route('/json_data_chain')
def get_json_data_chain():
    with data_lock:
        return jsonify({
            "nifty_spot_ltp": nifty_spot_ltp,
            "option_chain": option_chain_display_data
        })

if __name__ == '__main__':
    print("Application starting (Option Chain Viewer)...")
    initialize_data_and_subscriptions()
    if kws:
        print("Attempting to connect WebSocket...")
        try:
            kws.connect(threaded=True)
        except Exception as e:
            print(f"Error calling kws.connect(): {e}")
            #traceback.print_exc()
            exit()
        sleep(3) 
    else:
        print("CRITICAL: kws is None. Cannot connect WebSocket.")
        exit()
    #print(f"Starting Flask server on http://0.0.0.0:5000")
    #print(f"Default display: {DEFAULT_NUM_STRIKES_EACH_SIDE} strikes on each side of ATM, Mode: {DEFAULT_MODE}.")
    print("Access the option chain at http://127.0.0.1:5000/")
    flask_app.run(debug=True, host='0.0.0.0', use_reloader=False)