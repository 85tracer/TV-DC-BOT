from flask import Flask, request
import requests
import os
 
app = Flask(__name__)
 
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
 
@app.route("/")
def home():
    return "running"
 
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(silent=True)
 
        if data is None:
            data = request.get_data(as_text=True)
 
        message = f"TV Alert:\n{data}"
 
        if not DISCORD_WEBHOOK:
            return {"error": "DISCORD_WEBHOOK not set"}, 500
 
        r = requests.post(DISCORD_WEBHOOK, json={"content": message})
        return {"status": "ok", "discord_status": r.status_code}
 
    except Exception as e:
        return {"error": str(e)}, 500
 
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
 
