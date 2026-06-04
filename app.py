
from flask import Flask, request
import requests
import os
import datetime
import json
 
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
 
 
def place_option_entry(underlying, option_symbol, qty):
    url = f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders"
 
    payload = {
        "class": "option",
        "symbol": underlying,
        "option_symbol": option_symbol,
        "side": "buy_to_open",
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
 
 
def place_option_exit(underlying, option_symbol, qty):
    url = f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders"
 
    payload = {
        "class": "option",
        "symbol": underlying,
        "option_symbol": option_symbol,
        "side": "sell_to_close",
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
 
 
def get_positions():
    url = f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/positions"
 
    r = requests.get(
        url,
        headers=tradier_headers(),
        timeout=10
    )
 
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:1000]}
 
    return r.status_code, body
 
 
def find_option_position(ticker, side):
    status, body = get_positions()
 
    if status != 200:
        return None, status, body
 
    positions = body.get("positions", {}).get("position", [])
 
    if positions == "null" or positions is None:
        positions = []
 
    if not isinstance(positions, list):
        positions = [positions]
 
    for pos in positions:
        symbol = str(pos.get("symbol", ""))
 
        if not symbol.startswith(ticker):
            continue
 
        if side == "CALL" and "C" in symbol:
            return pos, status, body
 
        if side == "PUT" and "P" in symbol:
            return pos, status, body
 
    return None, status, body
 
 
def parse_webhook_data():
    try:
        data = request.get_json(silent=True)
 
        if data is not None:
            return data
 
        raw = request.get_data(as_text=True).strip()
 
        if not raw:
            return {"type": "ERROR", "message": "empty body"}
 
        if raw.upper() == "C EXIT":
            return {
                "type": "EXIT",
                "side": "CALL",
                "ticker": "QQQ"
            }
 
        if raw.upper() == "P EXIT":
            return {
                "type": "EXIT",
                "side": "PUT",
                "ticker": "QQQ"
            }
 
        if raw.startswith("{"):
            return json.loads(raw)
 
        return {
            "type": "ERROR",
            "message": f"unknown raw alert: {raw[:300]}"
        }
 
    except Exception as e:
        return {
            "type": "ERROR",
            "message": str(e)
        }
 
 
@app.route("/webhook", methods=["POST"])
def webhook():
    data = parse_webhook_data()
 
    if data.get("type") == "ERROR":
        send_discord(f"❌ WEBHOOK PARSE ERROR\n{data.get('message')}")
        return "ok", 200
 
    ticker = str(data.get("ticker", "")).upper().strip()
    ticker = ticker.split(":")[-1]
    side = str(data.get("side", "")).upper().strip()
    alert_type = str(data.get("type", "")).upper().strip()
    entry_type = str(data.get("entry_type", "")).strip()
    grade = str(data.get("grade", "")).strip()
    trade_id = str(data.get("trade_id", "")).strip()
 
    try:
        adx = float(data.get("adx", 22))
    except Exception:
        adx = 22
 
    send_discord(
        f"📩 ALERT RECEIVED\n"
        f"Ticker: {ticker}\n"
        f"Side: {side}\n"
        f"Type: {alert_type}\n"
        f"Trade ID: {trade_id}\n"
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
 
    # =========================
    # EXIT
    # =========================
 
    if alert_type == "EXIT":
        position, pos_status, pos_body = find_option_position(ticker, side)
 
        if not position:
            send_discord(
                f"⚠️ EXIT RECEIVED BUT NO POSITION FOUND\n"
                f"Ticker: {ticker}\n"
                f"Side: {side}\n"
                f"Positions status: {pos_status}\n"
                f"Positions response: {str(pos_body)[:700]}"
            )
            return "ok", 200
 
        option_symbol = position.get("symbol")
        qty = abs(int(float(position.get("quantity", 0))))
 
        if qty <= 0:
            send_discord(
                f"⚠️ EXIT FOUND POSITION BUT QTY IS ZERO\n"
                f"Option: {option_symbol}\n"
                f"Position: {position}"
            )
            return "ok", 200
 
        try:
            status, resp = place_option_exit(
                underlying=ticker,
                option_symbol=option_symbol,
                qty=qty
            )
        except Exception as e:
            send_discord(f"❌ EXIT ORDER REQUEST ERROR\n{str(e)}")
            return "ok", 200
 
        send_discord(
            f"🔴 EXIT ORDER SENT\n"
            f"Underlying: {ticker}\n"
            f"Option: {option_symbol}\n"
            f"Side: sell_to_close\n"
            f"Qty: {qty}\n"
            f"Status: {status}\n"
            f"Response: {resp}"
        )
 
        return "ok", 200
 
    # =========================
    # ENTRY
    # =========================
 
    regime = get_regime(adx)
    qty = size_by_regime(regime)
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
            f"Response: {str(chain)[:800]}"
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
        status, resp = place_option_entry(
            underlying=ticker,
            option_symbol=option_symbol,
            qty=qty
        )
    except Exception as e:
        send_discord(f"❌ ENTRY ORDER REQUEST ERROR\n{str(e)}")
        return "ok", 200
 
    send_discord(
        f"🚀 ENTRY ORDER SENT\n"
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
    return "v6 running - entry + exit enabled", 200
 
 
@app.route("/test", methods=["GET"])
def test():
    return {
        "version": "v6",
        "discord": bool(DISCORD_WEBHOOK),
        "tradier": bool(TRADIER_TOKEN),
        "account": bool(TRADIER_ACCOUNT_ID)
    }, 200
 
 
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
