from flask import Flask, request, jsonify, Response, render_template_string
from datetime import datetime
import json
import os
import requests

app = Flask(__name__)

# ===========================================
# CONFIGURATION
# ===========================================

GROQ_API_KEY = "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"  # Paste your real key
RESTAURANT_NAME = "Kebabish Original"
OWNER_PHONE = "+447438276572"  # Your real mobile

# Store orders and conversations
orders_db = {}
conversations = {}
order_counter = 100  # Start from order #100

# ===========================================
# AI SYSTEM PROMPT
# ===========================================

SYSTEM_PROMPT = f"""You are a friendly, professional phone ordering assistant for {Kebabish Original 7 Kings}.

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
1. Greet: "Thank you for calling {Kebabish Original 7 kings}! What can I get you today?"
2. Take orders one item at a time
3. ALWAYS ask spice level for curries
4. ALWAYS ask meat choice for kebabs
5. After each item ask "Would you like anything else?"
6. UPSELL: "Would you like a drink with that?" or "Garlic naan for £2.99?"
7. Before ending: repeat the full order back
8. Ask for customer name
9. Give total price
10. Say: "Your order will be ready in 20-25 minutes"
11. End with: "Thank you for calling {Kebabish_Original}!"

Keep responses SHORT and NATURAL."""

# ===========================================
# AI FUNCTION
# ===========================================

def get_ai_response(call_sid, user_message):
    try:
        if call_sid not in conversations:
            conversations[call_sid] = [{"role": "system", "content": SYSTEM_PROMPT}]
            orders_db[call_sid] = {
                "id": "",
                "items": [], "customer_name": "", "customer_phone": "",
                "total": "0.00", "order_type": "Pickup", "notes": "",
                "status": "in_progress", "timestamp": datetime.now().isoformat(),
                "printed": False
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
    return render_template_string(DASHBOARD_HTML)

@app.route("/dashboard")
def dashboard():
    """Live order dashboard"""
    return render_template_string(DASHBOARD_HTML)

@app.route("/voice", methods=["POST"])
def voice_webhook():
    call_sid = request.form.get("CallSid", "unknown")
    
    if call_sid not in conversations:
        conversations[call_sid] = [{"role": "system", "content": SYSTEM_PROMPT}]
        orders_db[call_sid] = {
            "id": "", "items": [], "customer_name": "", "customer_phone": "",
            "total": "0.00", "order_type": "Pickup", "notes": "",
            "status": "in_progress", "timestamp": datetime.now().isoformat(),
            "printed": False
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
    global order_counter
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
        order_counter += 1
        orders_db[call_sid]["id"] = f"ORD-{order_counter}"
        orders_db[call_sid]["status"] = "completed"
        orders_db[call_sid]["completed_at"] = datetime.now().strftime("%H:%M:%S")
        orders_db[call_sid]["date"] = datetime.now().strftime("%d/%m/%Y")
        
        # Try to extract customer name from conversation
        for msg in conversations.get(call_sid, []):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if "my name is" in content.lower():
                    name = content.lower().split("my name is")[-1].strip()
                    orders_db[call_sid]["customer_name"] = name.capitalize()
        
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
# ORDER APIs
# ===========================================

@app.route("/api/orders")
def get_orders():
    """Get all completed orders for dashboard"""
    completed = [o for o in orders_db.values() if o.get("status") == "completed"]
    return jsonify({"orders": completed})

@app.route("/api/orders/new")
def get_new_orders():
    """Get new unprinted orders"""
    new_orders = []
    for order in orders_db.values():
        if order.get("status") == "completed" and not order.get("viewed", False):
            order["viewed"] = True
            new_orders.append(order)
    return jsonify({"orders": new_orders})

@app.route("/api/stats")
def get_stats():
    """Dashboard statistics"""
    total = len([o for o in orders_db.values() if o.get("status") == "completed"])
    today = datetime.now().strftime("%d/%m/%Y")
    today_orders = len([o for o in orders_db.values() if o.get("date") == today and o.get("status") == "completed"])
    return jsonify({"total_orders": total, "today_orders": today_orders})

# ===========================================
# DASHBOARD HTML
# ===========================================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kebabish Original - Live Orders</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            background: #0a0a0a;
            color: #fff;
            min-height: 100vh;
        }
        .header {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            padding: 20px;
            text-align: center;
            border-bottom: 2px solid #3b82f6;
        }
        .header h1 { font-size: 28px; color: #3b82f6; }
        .header p { color: #888; margin-top: 5px; }
        .stats {
            display: flex;
            justify-content: center;
            gap: 30px;
            padding: 20px;
            background: #111;
        }
        .stat-box {
            text-align: center;
            padding: 15px 30px;
            background: #1a1a2e;
            border-radius: 10px;
            border: 1px solid #3b82f6;
        }
        .stat-box h2 { font-size: 32px; color: #22c55e; }
        .stat-box p { color: #888; font-size: 14px; }
        .orders-container {
            padding: 20px;
            max-width: 800px;
            margin: 0 auto;
        }
        .order-card {
            background: linear-gradient(135deg, #1a1a2e 0%, #0f3460 100%);
            border: 1px solid #3b82f6;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 15px;
            animation: slideIn 0.5s ease-out;
            position: relative;
            overflow: hidden;
        }
        .order-card.new {
            border-color: #22c55e;
            box-shadow: 0 0 20px rgba(34, 197, 94, 0.3);
            animation: pulse 2s infinite;
        }
        @keyframes slideIn {
            from { transform: translateX(-100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        @keyframes pulse {
            0%, 100% { box-shadow: 0 0 20px rgba(34, 197, 94, 0.3); }
            50% { box-shadow: 0 0 40px rgba(34, 197, 94, 0.6); }
        }
        .order-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        .order-id {
            font-size: 18px;
            font-weight: bold;
            color: #3b82f6;
        }
        .order-time {
            color: #888;
            font-size: 14px;
        }
        .order-status {
            background: #22c55e;
            color: #000;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
        }
        .order-details {
            margin-top: 10px;
        }
        .order-details p {
            margin: 5px 0;
            color: #ccc;
        }
        .customer-name {
            font-size: 20px;
            color: #fff;
            font-weight: bold;
        }
        .order-total {
            font-size: 24px;
            color: #22c55e;
            font-weight: bold;
            text-align: right;
            margin-top: 10px;
        }
        .no-orders {
            text-align: center;
            padding: 60px 20px;
            color: #555;
        }
        .no-orders h2 { font-size: 48px; margin-bottom: 10px; }
        .refresh-indicator {
            position: fixed;
            top: 20px;
            right: 20px;
            background: #3b82f6;
            color: #fff;
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 12px;
            opacity: 0;
            transition: opacity 0.3s;
        }
        .refresh-indicator.show { opacity: 1; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🍕 Kebabish Original</h1>
        <p>Live Order Dashboard - Auto-refreshing</p>
    </div>
    
    <div class="stats">
        <div class="stat-box">
            <h2 id="today-count">0</h2>
            <p>Today's Orders</p>
        </div>
        <div class="stat-box">
            <h2 id="total-count">0</h2>
            <p>Total Orders</p>
        </div>
    </div>
    
    <div class="orders-container" id="orders-list">
        <div class="no-orders">
            <h2>📱</h2>
            <p>Waiting for orders...</p>
            <p style="margin-top: 10px; font-size: 14px;">Call your AI number to place a test order</p>
        </div>
    </div>
    
    <div class="refresh-indicator" id="refresh-indicator">Checking...</div>
    
    <audio id="notification-sound" preload="auto">
        <source src="data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2teleR0NZKrk7rNsGgxJkNTsvXwkDk+L0O+0dSQPUIjN7LVyJQ1MiMzrsnMiDUyGzOuwdyQMTIfL6q12JgxMhsnprnUkDEuGyOerdiUNTIbH5Kl1JQxMhsbkpnUlDEuGxeKkdiUNTIbE4qN1JQxLhsPioXUlDEuGw+KhdiUNTIbD4aB1JQxLhsPgvnUlDEuGv+C9dSUNS4a+4Lx1JQ1Lhrzfu3UlDUuGvN67dSUNS4a73rp1JQ1LhrveunUlDUuGu9y6dSUNS4a62rh1JQ1LhrbauHUlDUuGstm2dSUNS4ay2bB1JQ1LhrDZrHUlDUuGrNirdSUNS4as1qd1JQ1LhqzVxnUlDUuGq9PGdSUNS4ar0sZ1JQ1LhqvRxnUlDUuGq9C+dS=" type="audio/wav">
    </audio>

    <script>
        let lastOrderCount = 0;
        let audioEnabled = false;
        
        // Enable audio on first user interaction
        document.addEventListener('click', () => { audioEnabled = true; }, { once: true });
        
        function playNotification() {
            if (audioEnabled) {
                document.getElementById('notification-sound').play().catch(e => console.log('Audio blocked'));
            }
        }
        
        function showRefreshIndicator() {
            const el = document.getElementById('refresh-indicator');
            el.classList.add('show');
            setTimeout(() => el.classList.remove('show'), 1000);
        }
        
        async function fetchOrders() {
            showRefreshIndicator();
            try {
                const response = await fetch('/api/orders');
                const data = await response.json();
                const orders = data.orders || [];
                
                // Update stats
                const todayResponse = await fetch('/api/stats');
                const stats = await todayResponse.json();
                document.getElementById('today-count').textContent = stats.today_orders;
                document.getElementById('total-count').textContent = stats.total_orders;
                
                // Check for new orders
                if (orders.length > lastOrderCount) {
                    playNotification();
                }
                lastOrderCount = orders.length;
                
                // Render orders
                const container = document.getElementById('orders-list');
                if (orders.length === 0) {
                    container.innerHTML = `
                        <div class="no-orders">
                            <h2>📱</h2>
                            <p>Waiting for orders...</p>
                            <p style="margin-top: 10px; font-size: 14px;">Call your AI number to place a test order</p>
                        </div>`;
                    return;
                }
                
                // Sort by newest first
                orders.reverse();
                
                container.innerHTML = orders.map(order => `
                    <div class="order-card ${order.printed ? '' : 'new'}">
                        <div class="order-header">
                            <span class="order-id">#${order.id || '---'}</span>
                            <span class="order-time">${order.completed_at || '--:--'}</span>
                            <span class="order-status">NEW ORDER</span>
                        </div>
                        <div class="order-details">
                            <p class="customer-name">${order.customer_name || 'Walk-in'}</p>
                            <p>📞 ${order.customer_phone || 'No phone'}</p>
                            <p>📦 Type: ${order.order_type || 'Pickup'}</p>
                            <hr style="border-color: #333; margin: 10px 0;">
                            <p><strong>Items:</strong></p>
                            ${(order.items || []).map(item => `
                                <p>• ${item.quantity || 1}x ${item.name} ${item.options ? `(${item.options})` : ''} ${item.price || ''}</p>
                            `).join('')}
                            ${order.notes ? `<p style="color: #fbbf24;">📝 ${order.notes}</p>` : ''}
                        </div>
                        <div class="order-total">${order.total || '£0.00'}</div>
                    </div>
                `).join('');
                
            } catch (error) {
                console.error('Error fetching orders:', error);
            }
        }
        
        // Fetch immediately and every 5 seconds
        fetchOrders();
        setInterval(fetchOrders, 5000);
    </script>
</body>
</html>
"""

# ===========================================
# START
# ===========================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
