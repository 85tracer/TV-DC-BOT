from flask import Flask, request
import requests
import os
 
app = Flask(__name__)
 
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
 
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
 
    requests.post(
        DISCORD_WEBHOOK,
        json={
            "content": f"TV Alert:\n{data}"
        }
    )
 
    return {"status": "ok"}
 
@app.route("/")
def home():
    return "running"
 
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
