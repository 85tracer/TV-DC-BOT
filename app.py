from flask import Flask, request
import requests
import os
import json
import datetime

app = Flask(__name__)

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
TRADIER_TOKEN = os.getenv("TRADIER_TOKEN")
TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")
TRADIER_BASE_URL = "https://sandbox.tradier.com/v1"

ALLOWED_SYMBOLS = ["SPY", "QQQ", "NVDA", "TSLA"]

# =========================
# Utils
# =========================

def send_discord(message):
    if DISCORD_WEBHOOK:
        requests.post(DISCORD_WEBHOOK, json={"content": message})

def tradier_headers():
    return {
        "Authorization": f"Bearer {TRADIER_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded"
    }

# =========================
# Equity (optional test)
# =========================

def place_equity_order(symbol, side, quantity):
    url = f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders"

    payload = {
        "class": "equity",
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "type": "market",
        "duration": "day"
    }

    r = requests.post(url, headers=tradier_headers(), data=payload)

    return {"status_code": r.status_code, "response": r.text[:1000]}

# =========================
# OPTIONS ENGINE
# =========================

def get_option_chain(symbol, expiration):
    url = f"{TRADIER_BASE_URL}/markets/options/chains"

    params = {
        "symbol": symbol,
        "expiration": expiration,
        "greeks": "true"
    }

    r = requests.get(url, headers=tradier_headers(), params=params)
    return r.json()

def select_atm_option(chain_data, side):
    options = chain_data.get("options", {}).get("option", [])

    if not options:
        return None

    best = None
    best_score = 999

    for opt in options:
        try:
            delta = float(opt.get("greeks", {}).get("delta", 0))

            if side == "CALL":
                score = abs(delta - 0.5)
            else:
                score = abs(delta + 0.5)

            if score < best_score:
                best_score = score
                best = opt

        except:
            continue

    return best

def place_option_order(option_symbol, side, quantity):
    url = f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders"

    payload = {
        "class": "option",
        "symbol": option_symbol,
        "side": side,
        "quantity": quantity,
        "type": "market",
        "duration": "day"
    }

    r = requests.post(url, headers=tradier_headers(), data=payload)

    return {"status_code": r.status_code, "response": r.text[:1000]}

# =========================
# Routes
# =========================

@app.route("/")
def home():
    return "running"

@app.route("/tradier-test")
def tradier_test():
    return {
        "discord_exists": bool(DISCORD_WEBHOOK),
        "tradier_token_exists": bool(TRADIER_TOKEN),
        "tradier_account_exists": bool(TRADIER_ACCOUNT_ID)
    }

@app.route("/webhook", methods=["GET", "POST"])
def webhook():

    raw_body = request.get_data(as_text=True)

    try:
        data = request.get_json(silent=True)

        if data is None and raw_body:
            data = json.loads(raw_body)

        ticker = data.get("ticker", "").upper()
        alert_type = data.get("type", "")
        side = data.get("side", "")
        grade = data.get("grade", "")
        entry_type = data.get("entry_type", "")

        send_discord(
            f"📩 TV ALERT\n"
            f"{ticker} {alert_type} {side} {grade} {entry_type}"
        )

        # =========================
        # FILTER
        # =========================

        if ticker not in ALLOWED_SYMBOLS:
            send_discord("⛔ Symbol not allowed")
            return "ok", 200

        # =========================
        # CALL OPTION ENTRY
        # =========================

        if alert_type == "ENTRY" and side == "CALL" and grade in ["A", "B"] and entry_type == "EX1":

            exp = datetime.date.today().strftime("%Y-%m-%d")

            chain = get_option_chain(ticker, exp)
            contract = select_atm_option
