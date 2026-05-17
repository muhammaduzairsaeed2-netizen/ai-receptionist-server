from flask import Flask, request, jsonify, Response
from datetime import datetime
import json
import os
import requests

app = Flask(__name__)

# ===========================================
# CONFIGURATION - Uses environment variables
# ===========================================

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
RESTAURANT_NAME = os.environ.get("RESTAURANT_NAME", "Kebabish Original")
OWNER_PHONE = os.environ.get("OWNER_PHONE", "")

# Store orders and conversations in memory
orders_db = {}
conversations = {}

# ===========================================
# AI SYSTEM PROMPT
# ===========================================

SYSTEM_PROMPT = f"""You are a friendly, professional phone ordering assistant for {RESTAURANT_NAME}.

MENU:
- Chicken Tikka Masala: £12.99 (Spice: Mild, Medium, Hot, Extra Hot)
- Lamb Curry: £13.99 (Spice: Mild, Medium, Hot, Extra Hot)
- Chicken Madras: £11.99 (Spice: Medium, Hot, Extra Hot)
- Doner Kebab: £9.99 (Meat: Lamb, Chicken, Mixed)
- Shish Kebab: £11.99 (Meat: Lamb, Chicken)
- Kofta Kebab: £10.99
- Mixed Kebab Platter: £16.99
- Samosa (2 pcs): £4.99
- Onion Bhaji: £5.99
- Chicken Pakora: £6.99
- Veggie Pakora: £5.99
- Garlic Naan: £2.99
- Plain Naan: £1.99
- Peshwari Naan: £3.49
- Cheese Naan: £3.49
- Roti: £1.99
- Pilau Rice: £3.49
- Mushroom Rice: £3.99
- Coke/Diet/Sprite: £2.50
- Bottle Water: £1.50

RULES:
1. Greet: "Thank you for calling {RESTAURANT_NAME}! What can I get you today?"
2. Take orders one item at a time
3. ALWAYS ask spice level for curries
4. ALWAYS ask meat choice for kebabs
5. After each item ask "Would you like anything else?"
6. UPSELL: "Would you like a drink with that?" or "Garlic naan for £2.99?"
7. Before ending: repeat the full order back
8. Ask for customer name
9. Give total price
10. Say: "Your order will be ready in 20-25 minutes"
11. End with: "Thank you for calling {RESTAURANT_NAME}!"

Keep responses SHORT and NATURAL - like a friendly real person."""

# ===========================================
# AI FUNCTION (Groq - FREE)
# ===========================================

def get_ai_response(call_sid, user_message):
    try:
        if call_sid not in conversations:
            conversations[call_sid] = [{"role": "system", "content": SYSTEM_PROMPT}]
            orders_db[call_sid] = {
                "items": [], "customer_name": "", "customer_phone": "",
                "total": "0.00", "order_type": "Pickup", "notes": "",
                "status": "in_progress", "timestamp": datetime.now().isoformat()
            }
        
        conversations[call_sid].append({"role": "user", "content": user_message})
        
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": "llama3-8b-8192", "messages": conversations[call_sid], "max_tokens": 120, "temperature": 0.7},
            timeout=10
        )
        
        data = response.json()
        ai_reply = data["choices"][0]["message"]["content"]
        conversations[call_sid].append({"role": "assistant", "content": ai_reply})
        
        return ai_reply
    except Exception as e:
        print(f"AI error: {e}")
        return "Sorry, I didn't catch that. Could you repeat please?"

# ===========================================
# TWILIO WEBHOOKS
# ===========================================

@app.route("/")
def home():
    return {"status": "ok", "message": "AI Receptionist Server is running!", "time": datetime.now().isoformat()}

@app.route("/voice", methods=["POST"])
def voice_webhook():
    call_sid = request.form.get("CallSid", "unknown")
    
    if call_sid not in conversations:
        conversations[call_sid] = [{"role": "system", "content": SYSTEM_PROMPT}]
        orders_db[call_sid] = {
            "items": [], "customer_name": "", "customer_phone": "",
            "total": "0.00", "order_type": "Pickup", "notes": "",
            "status": "in_progress", "timestamp": datetime.now().isoformat()
        }
    
    greeting = get_ai_response(call_sid, "Hi, a customer just called. Greet them.")
    
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna" language="en-GB">{greeting}</Say>
    <Gather input="speech" language="en-GB" action="/handle-speech" method="POST" speechTimeout="auto">
        <Say voice="Polly.Joanna" language="en-GB">I'm listening.</Say>
    </Gather>
</Response>"""
    
    return Response(xml, mimetype="text/xml")

@app.route("/handle-speech", methods=["POST"])
def handle_speech():
    call_sid = request.form.get("CallSid", "unknown")
    speech_result = request.form.get("SpeechResult", "")
    
    if not speech_result:
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna" language="en-GB">I didn't catch that. Could you say that again?</Say>
    <Gather input="speech" language="en-GB" action="/handle-speech" method="POST" speechTimeout="auto">
        <Say voice="Polly.Joanna" language="en-GB">Go ahead.</Say>
    </Gather>
</Response>"""
        return Response(xml, mimetype="text/xml")
    
    ai_response = get_ai_response(call_sid, speech_result)
    
    ending_phrases = ['thank you for calling', 'goodbye', 'order will be ready', 'see you soon']
    is_ending = any(p in ai_response.lower() for p in ending_phrases)
    
    if is_ending:
        orders_db[call_sid]["status"] = "completed"
        orders_db[call_sid]["completed_at"] = datetime.now().isoformat()
        
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna" language="en-GB">{ai_response}</Say>
    <Hangup/>
</Response>"""
    else:
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna" language="en-GB">{ai_response}</Say>
    <Gather input="speech" language="en-GB" action="/handle-speech" method="POST" speechTimeout="auto">
        <Say voice="Polly.Joanna" language="en-GB">Anything else?</Say>
    </Gather>
</Response>"""
    
    return Response(xml, mimetype="text/xml")

@app.route("/status", methods=["POST"])
def call_status():
    call_sid = request.form.get("CallSid")
    status = request.form.get("CallStatus")
    print(f"Call {call_sid} status: {status}")
    return "OK"

# ===========================================
# ORDER API (for Print Agent at restaurant)
# ===========================================

@app.route("/orders/new", methods=["GET"])
def get_new_orders():
    """Print Agent calls this to check for new completed orders"""
    new_orders = []
    for call_sid, order in list(orders_db.items()):
        if order.get("status") == "completed" and not order.get("printed", False):
            order["printed"] = True
            new_orders.append(order)
    return jsonify({"orders": new_orders})

@app.route("/orders", methods=["GET"])
def get_all_orders():
    return jsonify({"orders": list(orders_db.values())})

@app.route("/test", methods=["GET"])
def test():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})

# ===========================================
# START
# ===========================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
