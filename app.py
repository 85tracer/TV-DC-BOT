from flask import Flask, request
import requests
import os
import json
 
app = Flask(__name__)
 
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
TRADIER_TOKEN = os.getenv("TRADIER_TOKEN")
TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")
 
TRADIER_BASE_URL = "https://sandbox.tradier.com/v1"
 
def send_discord(message):
    if DISCORD_WEBHOOK:
        requests.post(DISCORD_WEBHOOK, json={"content": message})
 
def tradier_headers():
    return {
        "Authorization": f"Bearer {TRADIER_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded"
    }
 
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
 
    return {
        "status_code": r.status_code,
        "response": r.text[:1000]
    }
 
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
 
@app.route("/tradier-profile")
def tradier_profile():
    r = requests.get(
        f"{TRADIER_BASE_URL}/user/profile",
        headers=tradier_headers()
    )
 
    return {
        "status_code": r.status_code,
        "response": r.text[:1000]
    }
 
@app.route("/paper-buy-qqq")
def paper_buy_qqq():
    result = place_equity_order("QQQ", "buy", 1)
 
    send_discord(
        f"Paper order sent\nSymbol: QQQ\nSide: BUY\nQty: 1\nStatus: {result['status_code']}\nResponse: {result['response']}"
    )
 
    return result
 
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    raw_body = request.get_data(as_text=True)
 
    try:
        data = request.get_json(silent=True)
 
        if data is None and raw_body:
            data = json.loads(raw_body)
 
        if data is None:
            send_discord(f"TV Alert Received\n{raw_body}")
            return "ok", 200
 
        alert_type = data.get("type")
        side = data.get("side")
        ticker = data.get("ticker", "QQQ")
        grade = data.get("grade", "")
        entry_type = data.get("entry_type", "")
 
        send_discord(
            f"TV Alert Parsed\nType: {alert_type}\nSide: {side}\nTicker: {ticker}\nGrade: {grade}\nEntry: {entry_type}"
        )
 
        if alert_type == "ENTRY" and side == "CALL":
            result = place_equity_order("QQQ", "buy", 1)
            send_discord(f"Sandbox BUY QQQ sent\nStatus: {result['status_code']}\n{result['response']}")
 
        if alert_type == "EXIT" and side == "CALL":
            result = place_equity_order("QQQ", "sell", 1)
            send_discord(f"Sandbox SELL QQQ sent\nStatus: {result['status_code']}\n{result['response']}")
 
        return "ok", 200
 
    except Exception as e:
        send_discord(f"Webhook error\n{str(e)}\nRaw body:\n{raw_body}")
        return "ok", 200
 
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
