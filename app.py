from flask import Flask, request
import requests
import os
import json
import datetime

app = Flask(__name__)

# =========================
# CONFIG
# =========================

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
TRADIER_TOKEN = os.getenv("TRADIER_TOKEN")
TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")
TRADIER_BASE_URL = "https://sandbox.tradier.com/v1"

ALLOWED_SYMBOLS = ["SPY", "QQQ", "NVDA", "TSLA"]

# =========================
# UTIL
# =========================

def send_discord(msg):
    if DISCORD_WEBHOOK:
        requests.post(DISCORD_WEBHOOK, json={"content": msg})

def headers():
    return {
        "Authorization": f"Bearer {TRADIER_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded"
    }

# =========================
# REGIME ENGINE
# =========================

def get_regime(adx):
    if adx >= 28:
        return "STRONG"
    elif adx >= 20:
        return "WEAK"
    else:
        return "CHOP"

def size_by_regime(regime):
    if regime == "STRONG":
        return 2
    elif regime == "WEAK":
        return 1
    else:
        return 1

# =========================
# OPTIONS
# =========================

def get_chain(symbol, expiration):
    url = f"{TRADIER_BASE_URL}/markets/options/chains"
    params = {"symbol": symbol, "expiration": expiration, "greeks": "true"}
    r = requests.get(url, headers=headers(), params=params)
    return r.json()

def select_option(chain, side, regime):
    options = chain.get("options", {}).get("option", [])
    if not options:
        return None

    best = None
    best_score = 999

    for opt in options:
        try:
            delta = float(opt.get("greeks", {}).get("delta", 0))

            # REGIME SHIFT
            if regime == "STRONG":
                target = 0.65 if side == "CALL" else -0.65
            elif regime == "WEAK":
                target = 0.50 if side == "CALL" else -0.50
            else:
                target = 0.45 if side == "CALL" else -0.45

            score = abs(delta - target)

            if score < best_score:
                best_score = score
                best = opt

        except:
            continue

    return best

def place_option(symbol, side, qty):
    url = f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders"

    payload = {
        "class": "option",
        "symbol": symbol,
        "side": side,
        "quantity": qty,
        "type": "market",
        "duration": "day"
    }

    r = requests.post(url, headers=headers(), data=payload)
    return r.status_code, r.text[:500]

# =========================
# ROUTE
# =========================

@app.route("/webhook", methods=["POST"])
def webhook():

    data = request.get_json(force=True)

    ticker = data.get("ticker", "").upper()
    side = data.get("side", "")
    alert_type = data.get("type", "")
    entry_type = data.get("entry_type", "")
    grade = data.get("grade", "")

    # optional: you can pass ADX from TradingView later
    adx = float(data.get("adx", 22))

    send_discord(f"📩 {ticker} {side} {alert_type} {entry_type}")

    if ticker not in ALLOWED_SYMBOLS:
        send_discord("⛔ blocked symbol")
        return "ok"

    # =========================
    # REGIME
    # =========================

    regime = get_regime(adx)
    qty = size_by_regime(regime)

    exp = datetime.date.today().strftime("%Y-%m-%d")

    chain = get_chain(ticker, exp)

    # =========================
    # ENTRY EXECUTION (ALL SIGNALS)
    # =========================

    if alert_type == "ENTRY":

        contract = select_option(chain, side, regime)

        if not contract:
            send_discord("❌ no contract found")
            return "ok"

        opt_symbol = contract["symbol"]

        status, resp = place_option(opt_symbol, "buy_to_open", qty)

        send_discord(
            f"🚀 EXECUTED\n"
            f"{ticker} {side}\n"
            f"Regime: {regime}\n"
            f"Qty: {qty}\n"
            f"Contract: {opt_symbol}\n"
            f"Status: {status}"
        )

    # =========================
    # EXIT (simple mirror)
    # =========================

    elif alert_type == "EXIT":

        send_discord(f"🔴 EXIT SIGNAL {ticker} {side}")

    return "ok"


# =========================
# HEALTH CHECK
# =========================

@app.route("/")
def home():
    return "v3 running"

@app.route("/test")
def test():
    return {
        "discord": bool(DISCORD_WEBHOOK),
        "tradier": bool(TRADIER_TOKEN),
        "account": bool(TRADIER_ACCOUNT_ID)
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
