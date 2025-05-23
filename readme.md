# NIFTY Option Chain Viewer

Hey there! This little Python app whips up a real-time NIFTY option chain right in your browser. You can see live prices, OI, volume, and Option Greeks!

## Features ✨

*   Shows live NIFTY 50 index price.
*   Displays the NIFTY weekly option chain.
*   **Toggle Views:**
    *   **LTP/OI Mode:** Volume, Open Interest, Last Traded Price.
    *   **Greeks Mode:** Calculated IV, Vega, Delta, Theta.
*   Pick how many strikes you want to see around the current price (ATM).
*   Highlights the ATM strike.
*   Auto-refreshes every 2s so you see the latest data.

## Prerequisites 📋

*   Python 3.8+
*   A Zerodha account (for enctoken).

## Setup & Config 🚀

1.  **Clone it:**
    ```bash
    # git clone <your-repo-url>
    # cd <project-folder>
    ```

2.  **Virtual Environment (Good Idea!):**
    ```bash
    python -m venv venv
    # Windows: .\venv\Scripts\activate
    # macOS/Linux: source venv/bin/activate
    ```

3.  **Dependencies:**
    ```bash
    # pip install -r requirements.txt
    ```

4.  **🔑 API Credentials 🔑**
    This app needs enctoken from Zerodha website, so:
    *   **Edit `app.py`:**
        Open `app.py` and find these lines. Put your own Kite User ID and API Key here:
        ```python
        USER_ID = "YOUR_USER_ID"
        ```
    *   **Create `enctoken.txt`:**
        In the main project folder, paste enctoken in `enctoken.txt`.
        Generate a **fresh enctoken** from your Kite session (it usually lasts a day) and paste *only the token string* into this file. Save it.

5.  **Fire It Up!**
    ```bash
    python app.py
    ```
    Then open your browser and go to `http://127.0.0.1:5000/`.

## Project Demo 🎬

https://github.com/user-attachments/assets/0e0dd11a-cf83-4b3e-aa84-d3fddbf10c04

---
