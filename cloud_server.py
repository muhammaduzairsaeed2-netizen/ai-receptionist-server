from flask import Flask, request, Response, jsonify
from datetime import datetime
import json
import os
import requests

app = Flask(__name__)

# ===========================================
# CONFIG - FILL IN YOUR GROQ API KEY
# ===========================================

GROQ_API_KEY = "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"
RESTAURANT_NAME = "Kebabish Original"

# ===========================================
# AI PROMPT - NO f-STRINGS, SIMPLE TEXT
# ===========================================

SYSTEM_PROMPT = "You are a friendly phone ordering assistant for Kebabish Original takeaway.\n\nMENU:\n- Chicken Tikka Masala: 12.99 pounds (Spice: Mild, Medium, Hot, Extra Hot)\n- Lamb Curry: 13.99 pounds (Spice: Mild, Medium, Hot, Extra Hot)\n- Doner Kebab: 9.99 pounds (Meat: Lamb, Chicken, Mixed)\n- Shish Kebab: 11.99 pounds (Meat: Lamb, Chicken)\n- Garlic Naan: 2.99\n- Plain Naan: 1.99\n- Coke: 2.50\n\nRULES:\n1. Greet: Thank you for calling Kebabish Original, what can I get you today?\n2. Ask spice level for curries\n3. Ask meat choice for kebabs\n4. Ask would you like anything else after each item\n5. Give total price\n6. Say order will be ready in 20 to 25 minutes\n7. Say thank you for calling Kebabish Original goodbye\n8. Keep responses short."

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
    try:
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

        if resp.status_code != 200:
            print("GROQ ERROR STATUS: " + str(resp.status_code))
            print("GROQ BODY: " + resp.text[:200])
            return "Thank you for calling Kebabish Original, what can I get you today?"

        data = resp.json()

        if "choices" not in data or len(data["choices"]) == 0:
            print("GROQ ERROR: No choices in response")
            return "Thank you for calling Kebabish Original, what can I get you today?"

        ai_reply = data["choices"][0]["message"]["content"]
        conversations[call_sid].append({"role": "assistant", "content": ai_reply})

        print("AI REPLY: " + ai_reply[:80])
        return ai_reply

    except Exception as e:
        print("AI ERROR: " + str(e))
        return "Thank you for calling Kebabish Original, what can I get you today?"

# ===========================================
# HOME
# ===========================================

@app.route("/")
def home():
    return "Kebabish Original AI Server is running!"

# ===========================================
# VOICE WEBHOOK
# ===========================================

@app.route("/voice", methods=["POST"])
def voice_webhook():
    call_sid = request.form.get("CallSid", "unknown")
    print("NEW CALL: " + call_sid)

    greeting = get_ai_response(call_sid, "Customer called. Greet them.")
    print("GREETING: " + greeting[:80])

    xml = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<Response>\n"
    xml += "    <Say voice=\"Polly.Joanna\" language=\"en-GB\">" + greeting + "</Say>\n"
    xml += "    <Gather input=\"speech\" language=\"en-GB\" action=\"/handle-speech\" method=\"POST\" speechTimeout=\"3\" speechModel=\"phone_call\" enhanced=\"true\">\n"
    xml += "        <Say voice=\"Polly.Joanna\" language=\"en-GB\">Go ahead.</Say>\n"
    xml += "    </Gather>\n"
    xml += "</Response>"

    return Response(xml, mimetype="text/xml")

# ===========================================
# HANDLE SPEECH
# ===========================================

@app.route("/handle-speech", methods=["POST"])
def handle_speech():
    call_sid = request.form.get("CallSid", "unknown")
    speech_result = request.form.get("SpeechResult", "")

    print("CALLER SAID: " + speech_result)

    if not speech_result:
        xml = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<Response>\n"
        xml += "    <Say voice=\"Polly.Joanna\" language=\"en-GB\">I didn't catch that. Could you repeat please?</Say>\n"
        xml += "    <Gather input=\"speech\" language=\"en-GB\" action=\"/handle-speech\" method=\"POST\" speechTimeout=\"3\" speechModel=\"phone_call\" enhanced=\"true\">\n"
        xml += "        <Say voice=\"Polly.Joanna\" language=\"en-GB\">I am listening.</Say>\n"
        xml += "    </Gather>\n"
        xml += "</Response>"
        return Response(xml, mimetype="text/xml")

    ai_response = get_ai_response(call_sid, speech_result)

    ending_words = ['thank you', 'goodbye', 'ready', 'see you', 'bye']
    is_ending = any(word in ai_response.lower() for word in ending_words)

    if is_ending:
        global order_counter
        order_counter += 1
        orders_db[call_sid]["id"] = "ORD-" + str(order_counter)
        orders_db[call_sid]["status"] = "completed"
        orders_db[call_sid]["completed_at"] = datetime.now().strftime("%H:%M:%S")

        print("ORDER DONE: " + orders_db[call_sid]["id"])

        xml = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<Response>\n"
        xml += "    <Say voice=\"Polly.Joanna\" language=\"en-GB\">" + ai_response + "</Say>\n"
        xml += "    <Hangup/>\n"
        xml += "</Response>"
    else:
        xml = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<Response>\n"
        xml += "    <Say voice=\"Polly.Joanna\" language=\"en-GB\">" + ai_response + "</Say>\n"
        xml += "    <Gather input=\"speech\" language=\"en-GB\" action=\"/handle-speech\" method=\"POST\" speechTimeout=\"3\" speechModel=\"phone_call\" enhanced=\"true\">\n"
        xml += "        <Say voice=\"Polly.Joanna\" language=\"en-GB\">Anything else?</Say>\n"
        xml += "    </Gather>\n"
        xml += "</Response>"

    return Response(xml, mimetype="text/xml")

# ===========================================
# ORDER API
# ===========================================

@app.route("/api/orders")
def get_orders():
    completed = [o for o in orders_db.values() if o.get("status") == "completed"]
    return jsonify({"orders": completed})

# ===========================================
# START
# ===========================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
