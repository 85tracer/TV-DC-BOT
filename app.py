from flask import Flask, request
import requests
import os
import datetime
 
app = Flask(__name__)
 
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
TRADIER_TOKEN = os.getenv("TRADIER_TOKEN")
TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")
TRADIER_BASE_URL = "https://sandbox.tradier.com/v1"
 
ALLOWED_SYMBOLS = ["SPY", "QQQ", "NVDA", "TSLA"]
 
 
def send_discord(msg):
    if not DISCORD_WEBHOOK:
        return
    try:
        requests.post(
            DISCORD_WEBHOOK,
            json={"content": msg[:1900]},
            timeout=5
        )
    except Exception:
        pass
 
 
def tradier_headers():
    return {
        "Authorization": f"Bearer {TRADIER_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded"
    }
 
 
def get_regime(adx):
    if adx >= 28:
        return "STRONG"
    elif adx >= 20:
        return "WEAK"
    return "CHOP"
 
 
def size_by_regime(regime):
    if regime == "STRONG":
        return 2
    return 1
 
 
def get_chain(symbol, expiration):
    url = f"{TRADIER_BASE_URL}/markets/options/chains"
    params = {
        "symbol": symbol,
        "expiration": expiration,
        "greeks": "true"
    }
 
    r = requests.get(
        url,
        headers=tradier_headers(),
        params=params,
        timeout=10
    )
 
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:1000]}
 
    return r.status_code, body
 
 
def select_option(chain, side, regime):
    options = chain.get("options", {}).get("option", [])
 
    if not isinstance(options, list):
        options = [options]
 
    if not options:
        return None
 
    if side == "CALL":
        target = 0.65 if regime == "STRONG" else 0.50 if regime == "WEAK" else 0.45
    elif side == "PUT":
        target = -0.65 if regime == "STRONG" else -0.50 if regime == "WEAK" else -0.45
    else:
        return None
 
    best = None
    best_score = 999
 
    for opt in options:
        try:
            if opt.get("option_type", "").lower() != side.lower():
                continue
 
            delta = float(opt.get("greeks", {}).get("delta", 0))
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
 
    r = requests.post(
        url,
        headers=tradier_headers(),
        data=payload,
        timeout=10
    )
 
    return r.status_code, r.text[:1000]
 
 
@app.route("/webhook", methods=["POST"])
def webhook():
    data = None
 
    try:
        if request.is_json:
            data = request.get_json(silent=True)
 
        if data is None:
            send_discord("❌ Webhook received, but body was not valid JSON.")
            return "ok", 200
 
    except Exception as e:
        send_discord(f"❌ JSON READ ERROR\n{str(e)}")
        return "ok", 200
 
    ticker = str(data.get("ticker", "")).upper().strip()
    side = str(data.get("side", "")).upper().strip()
    alert_type = str(data.get("type", "")).upper().strip()
    entry_type = str(data.get("entry_type", "")).strip()
    grade = str(data.get("grade", "")).strip()
 
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
        return "ok", 200
 
    if side not in ["CALL", "PUT"]:
        send_discord(f"❌ INVALID SIDE: {side}")
        return "ok", 200
 
    if alert_type not in ["ENTRY", "EXIT"]:
        send_discord(f"❌ INVALID TYPE: {alert_type}")
        return "ok", 200
 
    regime = get_regime(adx)
    qty = size_by_regime(regime)
 
    if alert_type == "EXIT":
        send_discord(
            f"🔴 EXIT SIGNAL RECEIVED\n"
            f"Ticker: {ticker}\n"
            f"Side: {side}\n"
            f"Note: exit order is not implemented yet."
        )
        return "ok", 200
 
    expiration = datetime.date.today().strftime("%Y-%m-%d")
 
    try:
        chain_status, chain = get_chain(ticker, expiration)
    except Exception as e:
        send_discord(f"❌ CHAIN REQUEST ERROR\n{str(e)}")
        return "ok", 200
 
    if chain_status != 200:
        send_discord(
            f"❌ CHAIN ERROR\n"
            f"Ticker: {ticker}\n"
            f"Expiration: {expiration}\n"
            f"Status: {chain_status}\n"
            f"Response: {chain}"
        )
        return "ok", 200
 
    contract = select_option(chain, side, regime)
 
    if not contract:
        send_discord(
            f"❌ NO CONTRACT FOUND\n"
            f"Ticker: {ticker}\n"
            f"Side: {side}\n"
            f"Expiration: {expiration}\n"
            f"Regime: {regime}"
        )
        return "ok", 200
 
    option_symbol = contract.get("symbol")
    bid = contract.get("bid")
    ask = contract.get("ask")
    last = contract.get("last")
    delta = contract.get("greeks", {}).get("delta")
 
    try:
        status, resp = place_option(
            underlying=ticker,
            option_symbol=option_symbol,
            side="buy_to_open",
            qty=qty
        )
    except Exception as e:
        send_discord(f"❌ ORDER REQUEST ERROR\n{str(e)}")
        return "ok", 200
 
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
 
    return "ok", 200
 
 
@app.route("/", methods=["GET"])
def home():
    return "v5 running - safer JSON + Tradier timeout", 200
 
 
@app.route("/test", methods=["GET"])
def test():
    return {
        "version": "v5",
        "discord": bool(DISCORD_WEBHOOK),
        "tradier": bool(TRADIER_TOKEN),
        "account": bool(TRADIER_ACCOUNT_ID)
    }, 200
 
 
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
 
