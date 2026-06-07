
from flask import Flask, request
import requests
import os
import datetime
import json
import time
 
app = Flask(__name__)
 
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
TRADIER_TOKEN = os.getenv("TRADIER_TOKEN")
TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
 
TRADIER_BASE_URL = https://sandbox.tradier.com/v1
 
ALLOWED_SYMBOLS = ["SPY", "QQQ", "NVDA", "TSLA"]
 
MAX_SPREAD_PCT = 0.15
MIN_VOLUME = 100
MIN_ABS_DELTA = 0.45
MAX_ABS_DELTA = 0.65
TARGET_ABS_DELTA = 0.55
 
MAX_PREMIUM_PER_TRADE = 500
 
DUPLICATE_WINDOW_SECONDS = 30
 
OPEN_TRADES = {}
PROCESSED_ALERTS = {}
 
 
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
 
 
def clean_old_alerts():
    now = time.time()
 
    old_keys = [
        key for key, ts in PROCESSED_ALERTS.items()
        if now - ts > DUPLICATE_WINDOW_SECONDS
    ]
 
    for key in old_keys:
        PROCESSED_ALERTS.pop(key, None)
 
 
def is_duplicate_alert(alert_key):
    clean_old_alerts()
 
    if alert_key in PROCESSED_ALERTS:
        return True
 
    PROCESSED_ALERTS[alert_key] = time.time()
    return False
 
 
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
 
 
def get_option_cp(option_symbol):
    s = str(option_symbol).upper()
 
    for i, ch in enumerate(s):
        if ch in ["C", "P"]:
            tail = s[i + 1:]
            if len(tail) >= 8 and tail.isdigit():
                return ch
 
    return None
 
 
def calc_entry_limit_price(bid, ask):
    try:
        bid = float(bid)
        ask = float(ask)
 
        if bid <= 0 or ask <= 0:
            return None
 
        if ask <= bid:
            return None
 
        mid = (bid + ask) / 2
        spread_pct = (ask - bid) / mid
 
        if spread_pct > MAX_SPREAD_PCT:
            return None
 
        limit_price = min(ask, mid + 0.02)
        return round(limit_price, 2)
 
    except Exception:
        return None
 
 
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
 
    target_type = "call" if side == "CALL" else "put"
    candidates = []
 
    for opt in options:
        try:
            if opt.get("option_type", "").lower() != target_type:
                continue
 
            bid = float(opt.get("bid") or 0)
            ask = float(opt.get("ask") or 0)
            volume = int(float(opt.get("volume") or 0))
            delta = float(opt.get("greeks", {}).get("delta", 0))
 
            if bid <= 0 or ask <= 0:
                continue
 
            if ask <= bid:
                continue
 
            mid = (bid + ask) / 2
 
            if mid <= 0:
                continue
 
            spread_pct = (ask - bid) / mid
 
            if volume < MIN_VOLUME:
                continue
 
            if spread_pct > MAX_SPREAD_PCT:
                continue
 
            abs_delta = abs(delta)
 
            if abs_delta < MIN_ABS_DELTA:
                continue
 
            if abs_delta > MAX_ABS_DELTA:
                continue
 
            delta_distance = abs(abs_delta - TARGET_ABS_DELTA)
 
            candidates.append({
                "option": opt,
                "spread_pct": spread_pct,
                "delta_distance": delta_distance,
                "volume": volume
            })
 
        except Exception:
            continue
 
    if not candidates:
        return None
 
    candidates.sort(
        key=lambda x: (
            x["spread_pct"],
            x["delta_distance"],
            -x["volume"]
        )
    )
 
    return candidates[0]["option"]
 
 
def place_option_entry(underlying, option_symbol, qty, limit_price):
    url = f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders"
 
    payload = {
        "class": "option",
        "symbol": underlying,
        "option_symbol": option_symbol,
        "side": "buy_to_open",
        "quantity": qty,
        "type": "limit",
        "price": limit_price,
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
 
 
def normalize_positions(body):
    positions = body.get("positions", {}).get("position", [])
 
    if positions == "null" or positions is None:
        return []
 
    if not isinstance(positions, list):
        return [positions]
 
    return positions
 
 
def find_exact_position(option_symbol):
    status, body = get_positions()
 
    if status != 200:
        return None, status, body
 
    positions = normalize_positions(body)
 
    for pos in positions:
        if str(pos.get("symbol", "")) == str(option_symbol):
            return pos, status, body
 
    return None, status, body
 
 
def find_matching_positions(ticker, side):
    status, body = get_positions()
 
    if status != 200:
        return [], status, body
 
    positions = normalize_positions(body)
    wanted_cp = "C" if side == "CALL" else "P"
 
    matches = []
 
    for pos in positions:
        symbol = str(pos.get("symbol", "")).upper()
 
        if not symbol.startswith(ticker.upper()):
            continue
 
        actual_cp = get_option_cp(symbol)
 
        if actual_cp == wanted_cp:
            matches.append(pos)
 
    return matches, status, body
 
 
def parse_webhook_data():
    try:
        data = request.get_json(silent=True)
 
        if data is not None:
            return data
 
        raw = request.get_data(as_text=True).strip()
 
        if not raw:
            return {
                "type": "ERROR",
                "message": "empty body"
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
 
 
def make_trade_key(ticker, side, trade_id):
    if trade_id:
        return f"{ticker}:{side}:{trade_id}"
 
    return f"{ticker}:{side}:LATEST"
 
 
def make_alert_key(ticker, side, trade_id, alert_type):
    return f"{ticker}:{side}:{trade_id}:{alert_type}"
 
 
@app.route("/webhook", methods=["POST"])
def webhook():
    data = parse_webhook_data()
 
    if data.get("type") == "ERROR":
        send_discord(f"WEBHOOK PARSE ERROR\n{data.get('message')}")
        return "ok", 200
 
    if WEBHOOK_SECRET:
        incoming_secret = str(data.get("secret", "")).strip()
 
        if incoming_secret != WEBHOOK_SECRET:
            send_discord("BLOCKED - BAD WEBHOOK SECRET")
            return "ok", 200
 
    if not TRADIER_TOKEN or not TRADIER_ACCOUNT_ID:
        send_discord("BLOCKED - MISSING TRADIER ENVIRONMENT VARIABLES")
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
        f"ALERT RECEIVED\n"
        f"Ticker: {ticker}\n"
        f"Side: {side}\n"
        f"Type: {alert_type}\n"
        f"Trade ID: {trade_id}\n"
        f"Entry: {entry_type}\n"
        f"Grade: {grade}\n"
        f"ADX: {adx}"
    )
 
    if ticker not in ALLOWED_SYMBOLS:
        send_discord(f"BLOCKED SYMBOL: {ticker}")
        return "ok", 200
 
    if side not in ["CALL", "PUT"]:
        send_discord(f"INVALID SIDE: {side}")
        return "ok", 200
 
    if alert_type not in ["ENTRY", "EXIT"]:
        send_discord(f"INVALID TYPE: {alert_type}")
        return "ok", 200
 
    alert_key = make_alert_key(ticker, side, trade_id, alert_type)
 
    if is_duplicate_alert(alert_key):
        send_discord(
            f"DUPLICATE ALERT BLOCKED\n"
            f"Alert key: {alert_key}"
        )
        return "ok", 200
 
    trade_key = make_trade_key(ticker, side, trade_id)
 
    if alert_type == "EXIT":
        remembered = OPEN_TRADES.get(trade_key)
 
        if remembered:
            option_symbol = remembered.get("option_symbol")
            position, pos_status, pos_body = find_exact_position(option_symbol)
 
            if position:
                qty = abs(int(float(position.get("quantity", 0))))
 
                if qty <= 0:
                    send_discord(
                        f"EXIT BLOCKED - EXACT POSITION QTY ZERO\n"
                        f"Trade key: {trade_key}\n"
                        f"Option: {option_symbol}\n"
                        f"Position: {position}"
                    )
                    return "ok", 200
 
                status, resp = place_option_exit(
                    underlying=ticker,
                    option_symbol=option_symbol,
                    qty=qty
                )
 
                send_discord(
                    f"EXIT ORDER SENT - EXACT MATCH\n"
                    f"Trade key: {trade_key}\n"
                    f"Underlying: {ticker}\n"
                    f"Option: {option_symbol}\n"
                    f"Side: sell_to_close\n"
                    f"Qty: {qty}\n"
                    f"Status: {status}\n"
                    f"Response: {resp}"
                )
 
                if status in [200, 201]:
                    OPEN_TRADES.pop(trade_key, None)
 
                return "ok", 200
 
            send_discord(
                f"REMEMBERED TRADE NOT FOUND IN POSITIONS\n"
                f"Trade key: {trade_key}\n"
                f"Remembered option: {option_symbol}\n"
                f"Will try safe fallback search."
            )
 
        matches, pos_status, pos_body = find_matching_positions(ticker, side)
 
        if len(matches) == 0:
            send_discord(
                f"EXIT RECEIVED BUT NO POSITION FOUND\n"
                f"Ticker: {ticker}\n"
                f"Side: {side}\n"
                f"Trade key: {trade_key}\n"
                f"Positions status: {pos_status}\n"
                f"Positions response: {str(pos_body)[:700]}"
            )
            return "ok", 200
 
        if len(matches) > 1:
            match_symbols = [str(pos.get("symbol", "")) for pos in matches]
 
            send_discord(
                f"EXIT BLOCKED - MULTIPLE MATCHING POSITIONS\n"
                f"Ticker: {ticker}\n"
                f"Side: {side}\n"
                f"Trade key: {trade_key}\n"
                f"Matches: {match_symbols}\n"
                f"Manual action required."
            )
            return "ok", 200
 
        position = matches[0]
        option_symbol = position.get("symbol")
        qty = abs(int(float(position.get("quantity", 0))))
 
        if qty <= 0:
            send_discord(
                f"EXIT FOUND POSITION BUT QTY IS ZERO\n"
                f"Option: {option_symbol}\n"
                f"Position: {position}"
            )
            return "ok", 200
 
        status, resp = place_option_exit(
            underlying=ticker,
            option_symbol=option_symbol,
            qty=qty
        )
 
        send_discord(
            f"EXIT ORDER SENT - FALLBACK SINGLE MATCH\n"
            f"Underlying: {ticker}\n"
            f"Option: {option_symbol}\n"
            f"Side: sell_to_close\n"
            f"Qty: {qty}\n"
            f"Status: {status}\n"
            f"Response: {resp}"
        )
 
        return "ok", 200
 
    regime = get_regime(adx)
    qty = size_by_regime(regime)
    expiration = datetime.date.today().strftime("%Y-%m-%d")
 
    try:
        chain_status, chain = get_chain(ticker, expiration)
    except Exception as e:
        send_discord(f"CHAIN REQUEST ERROR\n{str(e)}")
        return "ok", 200
 
    if chain_status != 200:
        send_discord(
            f"CHAIN ERROR\n"
            f"Ticker: {ticker}\n"
            f"Expiration: {expiration}\n"
            f"Status: {chain_status}\n"
            f"Response: {str(chain)[:800]}"
        )
        return "ok", 200
 
    contract = select_option(chain, side, regime)
 
    if not contract:
        send_discord(
            f"NO CONTRACT FOUND AFTER LIQUIDITY FILTER\n"
            f"Ticker: {ticker}\n"
            f"Side: {side}\n"
            f"Expiration: {expiration}\n"
            f"Regime: {regime}\n"
            f"Rules: volume >= {MIN_VOLUME}, "
            f"spread <= {int(MAX_SPREAD_PCT * 100)}%, "
            f"abs(delta) {MIN_ABS_DELTA}-{MAX_ABS_DELTA}"
        )
        return "ok", 200
 
    option_symbol = contract.get("symbol")
    bid = contract.get("bid")
    ask = contract.get("ask")
    last = contract.get("last")
    volume = contract.get("volume")
    delta = contract.get("greeks", {}).get("delta")
 
    limit_price = calc_entry_limit_price(bid, ask)
 
    if limit_price is None:
        send_discord(
            f"ENTRY BLOCKED - BAD QUOTE OR WIDE SPREAD\n"
            f"Trade key: {trade_key}\n"
            f"Underlying: {ticker}\n"
            f"Option: {option_symbol}\n"
            f"Bid: {bid}\n"
            f"Ask: {ask}\n"
            f"Last: {last}\n"
            f"Volume: {volume}\n"
            f"Delta: {delta}"
        )
        return "ok", 200
 
    estimated_premium = limit_price * 100 * qty
 
    if estimated_premium > MAX_PREMIUM_PER_TRADE:
        send_discord(
            f"ENTRY BLOCKED - PREMIUM TOO HIGH\n"
            f"Trade key: {trade_key}\n"
            f"Underlying: {ticker}\n"
            f"Option: {option_symbol}\n"
            f"Qty: {qty}\n"
            f"Limit price: {limit_price}\n"
            f"Estimated premium: {estimated_premium}\n"
            f"Max allowed: {MAX_PREMIUM_PER_TRADE}"
        )
        return "ok", 200
 
    try:
        status, resp = place_option_entry(
            underlying=ticker,
            option_symbol=option_symbol,
            qty=qty,
            limit_price=limit_price
        )
    except Exception as e:
        send_discord(f"ENTRY ORDER REQUEST ERROR\n{str(e)}")
        return "ok", 200
 
    if status in [200, 201]:
        OPEN_TRADES[trade_key] = {
            "ticker": ticker,
            "side": side,
            "trade_id": trade_id,
            "option_symbol": option_symbol,
            "qty": qty,
            "entry_type": entry_type,
            "grade": grade,
            "limit_price": limit_price,
            "created_at": datetime.datetime.utcnow().isoformat()
        }
 
    send_discord(
        f"ENTRY LIMIT ORDER SUBMITTED - NOT CONFIRMED FILLED\n"
        f"Trade key: {trade_key}\n"
        f"Underlying: {ticker}\n"
        f"Option: {option_symbol}\n"
        f"Side: buy_to_open\n"
        f"Signal: {side}\n"
        f"Entry type: {entry_type}\n"
        f"Grade: {grade}\n"
        f"Regime: {regime}\n"
        f"Qty: {qty}\n"
        f"Bid: {bid} Ask: {ask} Last: {last}\n"
        f"Volume: {volume}\n"
        f"Limit price: {limit_price}\n"
        f"Estimated premium: {estimated_premium}\n"
        f"Delta: {delta}\n"
        f"Status: {status}\n"
        f"Response: {resp}"
    )
 
    return "ok", 200
 
 
@app.route("/", methods=["GET"])
def home():
    return "v10 running - execution safety enabled", 200
 
 
@app.route("/test", methods=["GET"])
def test():
    return {
        "version": "v10",
        "entry_order_type": "limit",
        "exit_order_type": "market",
        "max_spread_pct": MAX_SPREAD_PCT,
        "min_volume": MIN_VOLUME,
        "min_abs_delta": MIN_ABS_DELTA,
        "max_abs_delta": MAX_ABS_DELTA,
        "target_abs_delta": TARGET_ABS_DELTA,
        "max_premium_per_trade": MAX_PREMIUM_PER_TRADE,
        "duplicate_window_seconds": DUPLICATE_WINDOW_SECONDS,
        "discord": bool(DISCORD_WEBHOOK),
        "tradier": bool(TRADIER_TOKEN),
        "account": bool(TRADIER_ACCOUNT_ID),
        "webhook_secret_enabled": bool(WEBHOOK_SECRET),
        "open_trades_count": len(OPEN_TRADES),
        "processed_alerts_count": len(PROCESSED_ALERTS)
    }, 200
 
 
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
