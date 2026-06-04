from flask import Flask, request
import requests
import os
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
        try:
            requests.post(DISCORD_WEBHOOK, json={"content": msg})
        except Exception:
            pass
 
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
    params = {
        "symbol": symbol,
        "expiration": expiration,
        "greeks": "true"
    }
 
    r = requests.get(url, headers=headers(), params=params)
    return r.status_code, r.json()
 
def select_option(chain, side, regime):
    options = chain.get("options", {}).get("option", [])
 
    if not options:
        return None
 
    best = None
    best_score = 999
 
    for opt in options:
        try:
            delta = float(opt.get("greeks", {}).get("delta", 0))
 
            if side == "CALL":
                if regime == "STRONG":
                    target = 0.65
                elif regime == "WEAK":
                    target = 0.50
                else:
                    target = 0.45
            elif side == "PUT":
                if regime == "STRONG":
                    target = -0.65
                elif regime == "WEAK":
                    target = -0.50
                else:
                    target = -0.45
            else:
                return None
 
            score = abs(delta - target)
 
            if score < best_score:
                best_score = score
                best = opt
 
        except Exception:
            continue
 
    return best
 
def place_option(underlying, option_symbol, side, qty):
    url = f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders"
 
    payload = {
        "class": "option",
        "symbol": underlying,
        "option_symbol": option_symbol,
        "side": side,
        "quantity": qty,
        "type": "market",
        "duration": "day"
    }
 
    r = requests.post(url, headers=headers(), data=payload)
    return r.status_code, r.text[:1000]
 
# =========================
# ROUTE
# =========================
 
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
    except Exception as e:
        send_discord(f"❌ JSON ERROR: {str(e)}")
        return "ok"
 
    ticker = data.get("ticker", "").upper()
    side = data.get("side", "").upper()
    alert_type = data.get("type", "").upper()
    entry_type = data.get("entry_type", "")
    grade = data.get("grade", "")
 
    try:
        adx = float(data.get("adx", 22))
    except Exception:
        adx = 22
 
    send_discord(
        f"📩 ALERT RECEIVED\n"
        f"Ticker: {ticker}\n"
        f"Side: {side}\n"
        f"Type: {alert_type}\n"
        f"Entry: {entry_type}\n"
        f"Grade: {grade}\n"
        f"ADX: {adx}"
    )
 
    if ticker not in ALLOWED_SYMBOLS:
        send_discord(f"⛔ BLOCKED SYMBOL: {ticker}")
        return "ok"
 
    if side not in ["CALL", "PUT"]:
        send_discord(f"❌ INVALID SIDE: {side}")
        return "ok"
 
    regime = get_regime(adx)
    qty = size_by_regime(regime)
 
    expiration = datetime.date.today().strftime("%Y-%m-%d")
 
    chain_status, chain = get_chain(ticker, expiration)
 
    if chain_status != 200:
        send_discord(
            f"❌ CHAIN ERROR\n"
            f"Ticker: {ticker}\n"
            f"Expiration: {expiration}\n"
            f"Status: {chain_status}\n"
            f"Response: {chain}"
        )
        return "ok"
 
    # =========================
    # ENTRY
    # =========================
 
    if alert_type == "ENTRY":
        contract = select_option(chain, side, regime)
 
        if not contract:
            send_discord(
                f"❌ NO CONTRACT FOUND\n"
                f"Ticker: {ticker}\n"
                f"Side: {side}\n"
                f"Expiration: {expiration}\n"
                f"Regime: {regime}"
            )
            return "ok"
 
        option_symbol = contract.get("symbol")
        bid = contract.get("bid")
        ask = contract.get("ask")
        last = contract.get("last")
        delta = contract.get("greeks", {}).get("delta")
 
        status, resp = place_option(
            underlying=ticker,
            option_symbol=option_symbol,
            side="buy_to_open",
            qty=qty
        )
 
        send_discord(
            f"🚀 ORDER SENT\n"
            f"Underlying: {ticker}\n"
            f"Option: {option_symbol}\n"
            f"Side: buy_to_open\n"
            f"Signal: {side}\n"
            f"Regime: {regime}\n"
            f"Qty: {qty}\n"
            f"Bid: {bid} Ask: {ask} Last: {last}\n"
            f"Delta: {delta}\n"
            f"Status: {status}\n"
            f"Response: {resp}"
        )
 
    # =========================
    # EXIT
    # =========================
 
    elif alert_type == "EXIT":
        send_discord(
            f"🔴 EXIT SIGNAL RECEIVED\n"
            f"Ticker: {ticker}\n"
            f"Side: {side}\n"
            f"Note: exit logic not implemented yet"
        )
 
    else:
        send_discord(f"⚠️ UNKNOWN ALERT TYPE: {alert_type}")
 
    return "ok"
 
# =========================
# HEALTH CHECK
# =========================
 
@app.route("/")
def home():
    return "v4 running - fixed Tradier option_symbol"
 
@app.route("/test")
def test():
    return {
        "discord": bool(DISCORD_WEBHOOK),
        "tradier": bool(TRADIER_TOKEN),
        "account": bool(TRADIER_ACCOUNT_ID),
        "version": "v4"
    }
 
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
