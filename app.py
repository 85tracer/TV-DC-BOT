from flask import Flask, request
import requests
import os
 
app = Flask(__name__)
 
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
TRADIER_TOKEN = os.getenv("TRADIER_TOKEN")
TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")
 
@app.route("/")
def home():
    return "running"
 
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    raw_body = request.get_data(as_text=True)
 
    if DISCORD_WEBHOOK:
        requests.post(
            DISCORD_WEBHOOK,
            json={"content": f"TV Alert Received\n{raw_body}"}
        )
 
    return "ok", 200
 
@app.route("/tradier-test")
def tradier_test():
    return {
        "discord_exists": bool(DISCORD_WEBHOOK),
        "tradier_token_exists": bool(TRADIER_TOKEN),
        "tradier_account_exists": bool(TRADIER_ACCOUNT_ID)
    }
 
@app.route("/tradier-profile")
def tradier_profile():
    headers = {
        "Authorization": f"Bearer {TRADIER_TOKEN}",
        "Accept": "application/json"
    }
 
    r = requests.get(
        https://sandbox.tradier.com/v1/user/profile,
        headers=headers
    )
 
    return {
        "status_code": r.status_code,
        "response": r.text[:1000]
    }
 
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
