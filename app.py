from flask import Flask, request
import requests
import os
 
app = Flask(__name__)
 
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
 
@app.route("/")
def home():
    return "running"
 
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    raw_body = request.get_data(as_text=True)
    content_type = request.headers.get("Content-Type", "none")
 
    print("===== TV WEBHOOK RECEIVED =====")
    print("Content-Type:", content_type)
    print("Raw Body:", raw_body)
    print("DISCORD_WEBHOOK exists:", bool(DISCORD_WEBHOOK))
 
    if not DISCORD_WEBHOOK:
        return "DISCORD_WEBHOOK missing", 200
 
    message = f"TV Alert Received\nContent-Type: {content_type}\nBody: {raw_body}"
 
    try:
        r = requests.post(DISCORD_WEBHOOK, json={"content": message})
        print("Discord status:", r.status_code)
        print("Discord response:", r.text)
    except Exception as e:
        print("Discord error:", str(e))
        return "Discord error printed in logs", 200
 
    return "ok", 200
 
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)


@app.route("/tradier-test")
def tradier_test():
    return {
      "token_exists": bool(os.getenv("TRADIER_TOKEN")),
      "account_exists: bool(os.getenv("TRADIER_ACCOUNT_ID"))
   }
