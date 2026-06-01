from flask import Flask, request

import requests

import os

import json

 

app = Flask(__name__)

 

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

TRADIER_TOKEN = os.getenv("TRADIER_TOKEN")

TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")

TRADIER_BASE_URL = https://sandbox.tradier.com/v1

 

ALLOWED_SYMBOLS = ["SPY", "QQQ", "NVDA", "TSLA"]

 

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

        price = data.get("price", "")

        sl = data.get("sl", "")

        tp = data.get("tp", "")

 

        send_discord(

            f"📩 TV Alert Parsed\n"

            f"Ticker: {ticker}\n"

            f"Type: {alert_type}\n"

            f"Side: {side}\n"

            f"Grade: {grade}\n"

            f"Entry: {entry_type}\n"

            f"Price: {price}\n"

            f"SL: {sl}\n"

            f"TP: {tp}"

        )

 

        if ticker not in ALLOWED_SYMBOLS:

            send_discord(f"⛔ No order: {ticker} is not allowed.")

            return "ok", 200

 

        if alert_type == "ENTRY" and side == "CALL" and grade in ["A", "B"] and entry_type == "EX1":

            result = place_equity_order(ticker, "buy", 1)

            send_discord(

                f"✅ AUTO PAPER BUY\n"

                f"Symbol: {ticker}\n"

                f"Qty: 1 share\n"

                f"Reason: CALL A EX1\n"

                f"Status: {result['status_code']}\n"

                f"Response: {result['response']}"

            )

 

        elif alert_type == "EXIT" and side == "CALL":

            result = place_equity_order(ticker, "sell", 1)

            send_discord(

                f"✅ AUTO PAPER SELL\n"

                f"Symbol: {ticker}\n"

                f"Qty: 1 share\n"

                f"Reason: CALL EXIT\n"

                f"Status: {result['status_code']}\n"

                f"Response: {result['response']}"

            )

 

        else:

            send_discord("ℹ️ No auto order. Rule requires ENTRY + CALL + Grade A + EX1.")

 

        return "ok", 200

 

    except Exception as e:

        send_discord(f"❌ Webhook error\n{str(e)}\nRaw body:\n{raw_body}")

        return "ok", 200

 

@app.route("/paper-buy-test")

def paper_buy_test():

    result = place_equity_order("SPY", "buy", 1)

    send_discord(f"Manual paper test BUY SPY\nStatus: {result['status_code']}\n{result['response']}")

    return result

 

if __name__ == "__main__":

    app.run(host="0.0.0.0", port=8080)
