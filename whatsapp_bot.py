import os
import json
import requests
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client

app = Flask(__name__)

# --- CONFIGURATION ---
TWILIO_SID = os.environ.get("TWILIO_SID", "YOUR_SID_HERE") 
TWILIO_TOKEN = os.environ.get("TWILIO_TOKEN", "YOUR_TOKEN_HERE")
TWILIO_NUMBER = 'whatsapp:+14155238886'

client = Client(TWILIO_SID, TWILIO_TOKEN)

users = {}

(BTC_SIDE, BTC_ENTRY, BTC_AMT, BTC_LEV, 
 ETH_SIDE, ETH_ENTRY, ETH_AMT, ETH_LEV, 
 TARGET, MONITORING) = range(10)

def get_price(symbol):
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
        resp = requests.get(url, timeout=5).json()
        return float(resp['price'])
    except:
        return None

def calculate_pnl(current, entry, amt, lev, side):
    if side == 'long':
        return ((current - entry) / entry) * amt * lev
    else:
        return ((entry - current) / entry) * amt * lev

# --- CRON JOB TRIGGER ---
@app.route("/check", methods=['GET'])
def check_prices():
    log_messages = []
    try:
        btc_price = get_price("BTCUSDT")
        eth_price = get_price("ETHUSDT")

        if not btc_price or not eth_price:
            return "Error fetching prices", 500

        for phone, data in list(users.items()):
            if data.get('state') == MONITORING:
                btc_pnl = calculate_pnl(btc_price, data['btc_entry'], data['btc_amt'], data['btc_lev'], data['btc_side'])
                eth_pnl = calculate_pnl(eth_price, data['eth_entry'], data['eth_amt'], data['eth_lev'], data['eth_side'])
                total = btc_pnl + eth_pnl

                log_messages.append(f"User {phone[-4:]}: ${total:.2f}")

                if total >= data['target']:
                    msg = (f"🚀 *Target Hit!*\n\n"
                           f"Profit: *${total:.2f}*\n"
                           f"BTC: ${btc_pnl:.2f}\nETH: ${eth_pnl:.2f}")
                    try:
                        client.messages.create(from_=TWILIO_NUMBER, to=phone, body=msg)
                        users[phone]['state'] = -1
                        log_messages.append(f"Alert sent to {phone[-4:]}")
                    except Exception as e:
                        log_messages.append(f"Failed to send alert: {e}")

        return "<br>".join(log_messages) if log_messages else "No active monitoring", 200

    except Exception as e:
        return f"Error: {e}", 500

# --- MAIN ROUTE ---
@app.route("/", methods=['GET', 'POST'])
def bot():
    # Browser Check
    if request.method == 'GET':
        return "✅ WhatsApp Bot is Running!", 200

    # WhatsApp Logic
    incoming_msg = request.values.get('Body', '').strip().lower()
    sender = request.values.get('From')
    resp = MessagingResponse()
    msg = resp.message()

    if sender not in users:
        users[sender] = {'state': -1}

    state = users[sender]['state']

    if incoming_msg == 'setup':
        users[sender]['state'] = BTC_SIDE
        msg.body("Let's start.\nAre you *Long* or *Short* on BTC?")
    
    elif incoming_msg == 'status':
        if state != MONITORING:
            msg.body("⚠️ Not monitoring.")
        else:
            d = users[sender]
            b, e = get_price("BTCUSDT"), get_price("ETHUSDT")
            if b and e:
                bp = calculate_pnl(b, d['btc_entry'], d['btc_amt'], d['btc_lev'], d['btc_side'])
                ep = calculate_pnl(e, d['eth_entry'], d['eth_amt'], d['eth_lev'], d['eth_side'])
                msg.body(f"📊 *Status*\nCurrent PnL: ${bp+ep:.2f}")
            else:
                msg.body("Error fetching prices.")

    elif state == BTC_SIDE:
        if incoming_msg in ['long', 'short']:
            users[sender]['btc_side'] = incoming_msg
            users[sender]['state'] = BTC_ENTRY
            msg.body("BTC Entry Price:")
        else: msg.body("Type Long or Short.")

    elif state == BTC_ENTRY:
        try:
            users[sender]['btc_entry'] = float(incoming_msg)
            users[sender]['state'] = BTC_AMT
            msg.body("BTC Amount ($):")
        except: msg.body("Numbers only.")

    elif state == BTC_AMT:
        try:
            users[sender]['btc_amt'] = float(incoming_msg)
            users[sender]['state'] = BTC_LEV
            msg.body("BTC Leverage:")
        except: msg.body("Numbers only.")

    elif state == BTC_LEV:
        try:
            users[sender]['btc_lev'] = float(incoming_msg)
            users[sender]['state'] = ETH_SIDE
            msg.body("Now ETH.\n*Long* or *Short*?")
        except: msg.body("Numbers only.")

    elif state == ETH_SIDE:
        if incoming_msg in ['long', 'short']:
            users[sender]['eth_side'] = incoming_msg
            users[sender]['state'] = ETH_ENTRY
            msg.body("ETH Entry Price:")
        else: msg.body("Type Long or Short.")

    elif state == ETH_ENTRY:
        try:
            users[sender]['eth_entry'] = float(incoming_msg)
            users[sender]['state'] = ETH_AMT
            msg.body("ETH Amount ($):")
        except: msg.body("Numbers only.")

    elif state == ETH_AMT:
        try:
            users[sender]['eth_amt'] = float(incoming_msg)
            users[sender]['state'] = ETH_LEV
            msg.body("ETH Leverage:")
        except: msg.body("Numbers only.")

    elif state == ETH_LEV:
        try:
            users[sender]['eth_lev'] = float(incoming_msg)
            users[sender]['state'] = TARGET
            msg.body("Target Profit ($):")
        except: msg.body("Numbers only.")

    elif state == TARGET:
        try:
            users[sender]['target'] = float(incoming_msg)
            users[sender]['state'] = MONITORING
            msg.body("✅ Setup Saved & Monitoring!")
        except: msg.body("Numbers only.")

    else:
        msg.body("Send 'setup' to start.")

    return str(resp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)