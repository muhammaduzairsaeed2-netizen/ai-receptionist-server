from flask import Flask, request, Response, jsonify
from datetime import datetime
import json
import os
import requests

app = Flask(__name__)

# ===========================================
# CONFIG - Reads from Render Environment
# ===========================================

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
RESTAURANT_NAME = os.environ.get("RESTAURANT_NAME", "Kebabish Original")

# ===========================================
# AI PROMPT
# ===========================================

SYSTEM_PROMPT = (
    "You are a friendly phone ordering assistant for Kebabish Original takeaway.\n\n"
    "MENU:\n"
    "- Chicken Tikka Masala: 12.99 pounds (Spice: Mild, Medium, Hot, Extra Hot)\n"
    "- Lamb Curry: 13.99 pounds (Spice: Mild, Medium, Hot, Extra Hot)\n"
    "- Doner Kebab: 9.99 pounds (Meat: Lamb, Chicken, Mixed)\n"
    "- Shish Kebab: 11.99 pounds (Meat: Lamb, Chicken)\n"
    "- Garlic Naan: 2.99\n"
    "- Plain Naan: 1.99\n"
    "- Coke: 2.50\n\n"
    "RULES:\n"
    "1. Greet: Thank you for calling Kebabish Original, what can I get you today?\n"
    "2. Ask spice level for curries\n"
    "3. Ask meat choice for kebabs\n"
    "4. Ask would you like anything else after each item\n"
    "5. Ask for customer name\n"
    "6. Give total price\n"
    "7. Say order will be ready in 20 to 25 minutes\n"
    "8. Say thank you for calling Kebabish Original goodbye\n"
    "9. Keep responses short and natural."
)

# ===========================================
# STORAGE
# ===========================================

orders_db = {}
conversations = {}
order_counter = 100

# ===========================================
# AI FUNCTION
# ===========================================

def get_ai_response(call_sid, user_message):
    if call_sid not in conversations:
        conversations[call_sid] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        orders_db[call_sid] = {
            "id": "",
            "customer_name": "",
            "items": [],
            "total": "0.00",
            "status": "in_progress",
            "timestamp": datetime.now().isoformat()
        }

    conversations[call_sid].append({"role": "user", "content": user_message})

    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": "Bearer " + GROQ_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "model": "llama3-8b-8192",
                "messages": conversations[call_sid],
                "max_tokens": 150,
                "temperature": 0.7
            },
            timeout=10
        )

        print("GROQ STATUS: " + str(resp.status_code))

        if resp.status_code != 200:
            print("GROQ ERROR: " + resp.text[:300])
            return "Thank you for calling Kebabish Original, what can I get you today?"

        data = resp.json()

        if "choices" not in data or len(data["choices"]) == 0:
            print("GROQ ERROR: No choices in response")
            print("RESPONSE: " + json.dumps(data)[:300])
            return "Thank you for calling Kebabish Original, what can I get you today?"

        choice = data["choices"][0]
        if "message" not in choice or "content" not in choice["message"]:
            print("GROQ ERROR: Bad message format")
            return "Thank you for calling Kebabish Original, what can I get you today?"

        ai_reply = choice["message"]["content"]
        conversations[call_sid].append({"role": "assistant", "content": ai_reply})
        print("AI REPLY: " + ai_reply[:80])
        return ai_reply

    except Exception as e:
        print("AI ERROR: " + str(e))
        return "Thank you for calling Kebabish Original, what can I get you today?"

# ===========================================
# HOME / DASHBOARD
# ===========================================

@app.route("/")
def home():
    completed = [o for o in orders_db.values() if o.get("status") == "completed"]
    completed.reverse()
    html = "<html><head><title>Kebabish Orders</title><style>"
    html += "body{font-family:Arial;background:#0a0a0a;color:#fff;padding:20px}"
    html += ".header{text-align:center;padding:20px;border-bottom:2px solid #3b82f6}"
    html += ".header h1{color:#3b82f6;margin:0}"
    html += ".stats{display:flex;justify-content:center;gap:30px;padding:20px}"
    html += ".stat{text-align:center;padding:15px 30px;background:#1a1a2e;border-radius:10px;border:1px solid #3b82f6}"
    html += ".stat h2{color:#22c55e;font-size:32px;margin:0}"
    html += ".stat p{color:#888;margin:5px 0 0}"
    html += ".order{background:#1a1a2e;border:1px solid #3b82f6;border-radius:10px;padding:15px;margin:15px 0}"
    html += ".order.new{border-color:#22c55e;box-shadow:0 0 15px rgba(34,197,94,0.3)}"
    html += ".order-id{color:#3b82f6;font-weight:bold;font-size:18px}"
    html += ".order-total{color:#22c55e;font-size:22px;font-weight:bold;text-align:right}"
    html += ".empty{text-align:center;color:#555;padding:60px}"
    html += "</style></head><body>"
    html += "<div class='header'><h1>Kebabish Original</h1><p>Live Orders</p></div>"
    html += "<div class='stats'>"
    today = datetime.now().strftime("%d/%m/%Y")
    today_count = len([o for o in orders_db.values() if o.get("status") == "completed" and o.get("date") == today])
    total_count = len([o for o in orders_db.values() if o.get("status") == "completed"])
    html += "<div class='stat'><h2>" + str(today_count) + "</h2><p>Today</p></div>"
    html += "<div class='stat'><h2>" + str(total_count) + "</h2><p>Total</p></div>"
    html += "</div>"
    if not completed:
        html += "<div class='empty'><h2>No orders yet</h2><p>Call your AI number to place a test order</p></div>"
    else:
        for order in completed:
            is_new = "new" if not order.get("viewed") else ""
            html += "<div class='order " + is_new + "'>"
            html += "<div class='order-id'>#" + order.get("id", "---") + "</div>"
            html += "<p><strong>" + order.get("customer_name", "Walk-in") + "</strong></p>"
            html += "<p>" + order.get("completed_at", "--:--") + "</p>"
            for item in order.get("items", []):
                html += "<p>" + str(item.get("quantity", 1)) + "x " + item.get("name", "?") + "</p>"
            html += "<div class='order-total'>" + order.get("total", "0.00") + "</div>"
            html += "</div>"
    html += "<script>setInterval(function(){location.reload()},5000);</script>"
    html += "</body></html>"
    return html

# ===========================================
# VOICE WEBHOOK
# ===========================================

@app.route("/voice", methods=["POST"])
def voice_webhook():
    call_sid = request.form.get("CallSid", "unknown")
    print("NEW CALL: " + call_sid)

    greeting = get_ai_response(call_sid, "Customer called. Greet them.")

    xml = "<?xml version='1.0' encoding='UTF-8'?>\n"
    xml += "<Response>\n"
    xml += "<Say voice='Polly.Joanna' language='en-GB'>" + greeting + "</Say>\n"
    xml += "<Gather input='speech' language='en-GB' action='/handle-speech' method='POST' speechTimeout='auto'>\n"
    xml += "<Say voice='Polly.Joanna' language='en-GB'>Go ahead.</Say>\n"
    xml += "</Gather>\n"
    xml += "</Response>"

    return Response(xml, mimetype="text/xml")

# ===========================================
# HANDLE SPEECH
# ===========================================

@app.route("/handle-speech", methods=["POST"])
def handle_speech():
    call_sid = request.form.get("CallSid", "unknown")
    speech_result = request.form.get("SpeechResult", "")

    print("CALLER SAID: [" + speech_result + "]")

    if not speech_result:
        xml = "<?xml version='1.0' encoding='UTF-8'?>\n"
        xml += "<Response>\n"
        xml += "<Say voice='Polly.Joanna' language='en-GB'>I did not catch that. Could you repeat please?</Say>\n"
        xml += "<Gather input='speech' language='en-GB' action='/handle-speech' method='POST' speechTimeout='auto'>\n"
        xml += "<Say voice='Polly.Joanna' language='en-GB'>I am listening.</Say>\n"
        xml += "</Gather>\n"
        xml += "</Response>"
        return Response(xml, mimetype="text/xml")

    ai_response = get_ai_response(call_sid, speech_result)

    is_ending = False
    lower_reply = ai_response.lower()
    if "thank you" in lower_reply or "goodbye" in lower_reply or "order will be ready" in lower_reply:
        is_ending = True

    if is_ending:
        global order_counter
        order_counter += 1
        orders_db[call_sid]["id"] = "ORD-" + str(order_counter)
        orders_db[call_sid]["status"] = "completed"
        orders_db[call_sid]["completed_at"] = datetime.now().strftime("%H:%M:%S")
        orders_db[call_sid]["date"] = datetime.now().strftime("%d/%m/%Y")
        print("ORDER COMPLETED: " + orders_db[call_sid]["id"])

        xml = "<?xml version='1.0' encoding='UTF-8'?>\n"
        xml += "<Response>\n"
        xml += "<Say voice='Polly.Joanna' language='en-GB'>" + ai_response + "</Say>\n"
        xml += "<Hangup/>\n"
        xml += "</Response>"
    else:
        xml = "<?xml version='1.0' encoding='UTF-8'?>\n"
        xml += "<Response>\n"
        xml += "<Say voice='Polly.Joanna' language='en-GB'>" + ai_response + "</Say>\n"
        xml += "<Gather input='speech' language='en-GB' action='/handle-speech' method='POST' speechTimeout='auto'>\n"
        xml += "<Say voice='Polly.Joanna' language='en-GB'>Anything else?</Say>\n"
        xml += "</Gather>\n"
        xml += "</Response>"

    return Response(xml, mimetype="text/xml")

# ===========================================
# CALL STATUS
# ===========================================

@app.route("/status", methods=["POST"])
def call_status():
    print("Call status: " + request.form.get("CallStatus", ""))
    return "OK"

# ===========================================
# ORDER API
# ===========================================

@app.route("/api/orders")
def get_orders():
    completed = [o for o in orders_db.values() if o.get("status") == "completed"]
    return jsonify({"orders": completed})

@app.route("/api/orders/new")
def get_new_orders():
    new_orders = []
    for order in list(orders_db.values()):
        if order.get("status") == "completed" and not order.get("viewed", False):
            order["viewed"] = True
            new_orders.append(order)
    return jsonify({"orders": new_orders})

# ===========================================
# START
# ===========================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
