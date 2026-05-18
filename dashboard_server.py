from flask import Flask, request, jsonify
from datetime import datetime
import json
import os

app = Flask(__name__)

# ===========================================
# ORDER STORAGE
# ===========================================

orders_list = []
order_counter = 100

# ===========================================
# VAPI WEBHOOK - Receives orders from Vapi AI
# ===========================================

@app.route("/print-order", methods=["POST"])
def receive_order():
    """Vapi sends completed orders here"""
    try:
        payload = request.get_json(force=True, silent=True) or {}
        print("VAPI DATA: " + json.dumps(payload)[:500])
        
        # Extract from Vapi format
        tool_call_id = ""
        order_data = {}
        
        # Try Vapi toolCallList format
        if "message" in payload and isinstance(payload["message"], dict):
            msg = payload["message"]
            if "toolCallList" in msg:
                for tc in msg["toolCallList"]:
                    tool_call_id = tc.get("id", "")
                    fn = tc.get("function", {})
                    args = fn.get("arguments", "{}")
                    if isinstance(args, str):
                        try:
                            order_data = json.loads(args)
                        except:
                            order_data = {}
                    elif isinstance(args, dict):
                        order_data = args
        
        # Fallback: direct format
        if not order_data:
            order_data = {k: v for k, v in payload.items() if k not in ["message", "toolCallId"]}
            tool_call_id = payload.get("toolCallId", "")
        
        # Save order
        global order_counter
        order_counter += 1
        
        new_order = {
            "id": "ORD-" + str(order_counter),
            "customer_name": order_data.get("customerName", order_data.get("customer_name", "Walk-in")),
            "customer_phone": order_data.get("customerPhone", order_data.get("customer_phone", "")),
            "items": order_data.get("items", []),
            "total": order_data.get("total", "0.00"),
            "order_type": order_data.get("orderType", order_data.get("order_type", "Pickup")),
            "notes": order_data.get("notes", ""),
            "status": "completed",
            "completed_at": datetime.now().strftime("%H:%M:%S"),
            "date": datetime.now().strftime("%d/%m/%Y"),
            "timestamp": datetime.now().isoformat()
        }
        
        orders_list.insert(0, new_order)
        print("ORDER SAVED: " + new_order["id"] + " - " + new_order["customer_name"] + " - " + new_order["total"])
        
        # Return Vapi expected format
        return jsonify({
            "results": [{
                "toolCallId": tool_call_id,
                "result": {"ok": True}
            }]
        }), 200
        
    except Exception as e:
        print("ERROR: " + str(e))
        return jsonify({
            "results": [{
                "toolCallId": "",
                "result": {"ok": True}
            }]
        }), 200

# ===========================================
# DASHBOARD - Shows all orders
# ===========================================

@app.route("/")
def dashboard():
    """Live order dashboard page"""
    today = datetime.now().strftime("%d/%m/%Y")
    today_count = len([o for o in orders_list if o.get("date") == today])
    total_count = len(orders_list)
    
    html = """<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<title>""" + os.environ.get("RESTAURANT_NAME", "Kebabish Original") + """ - Orders</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Arial,Helvetica,sans-serif;background:#0a0a0a;color:#fff;min-height:100vh}
.header{background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);padding:20px;text-align:center;border-bottom:2px solid #3b82f6}
.header h1{color:#3b82f6;font-size:28px}
.header p{color:#888;margin-top:5px}
.stats{display:flex;justify-content:center;gap:30px;padding:20px;background:#111}
.stat{text-align:center;padding:15px 30px;background:#1a1a2e;border-radius:10px;border:1px solid #3b82f6}
.stat h2{color:#22c55e;font-size:32px;margin:0}
.stat p{color:#888;margin:5px 0 0;font-size:14px}
.orders-container{padding:20px;max-width:800px;margin:0 auto}
.order-card{background:linear-gradient(135deg,#1a1a2e 0%,#0f3460 100%);border:1px solid #3b82f6;border-radius:12px;padding:20px;margin-bottom:15px;animation:slideIn 0.5s ease-out}
.order-card.new{border-color:#22c55e;box-shadow:0 0 20px rgba(34,197,94,0.3);animation:pulse 2s infinite}
@keyframes slideIn{from{transform:translateX(-100%);opacity:0}to{transform:translateX(0);opacity:1}}
@keyframes pulse{0%,100%{box-shadow:0 0 20px rgba(34,197,94,0.3)}50%{box-shadow:0 0 40px rgba(34,197,94,0.6)}}
.order-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.order-id{font-size:18px;font-weight:bold;color:#3b82f6}
.order-time{color:#888;font-size:14px}
.order-status{background:#22c55e;color:#000;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:bold}
.customer-name{font-size:20px;font-weight:bold;margin:5px 0}
.order-details p{margin:5px 0;color:#ccc}
.item-list{padding-left:15px}
.item-list p{margin:3px 0}
.order-total{font-size:24px;color:#22c55e;font-weight:bold;text-align:right;margin-top:10px}
.no-orders{text-align:center;padding:60px 20px;color:#555}
.empty-icon{font-size:48px;margin-bottom:10px}
</style></head><body>
<div class="header"><h1>Kebabish Original</h1><p>Live Order Dashboard</p></div>
<div class="stats">
<div class="stat"><h2>""" + str(today_count) + """</h2><p>Today's Orders</p></div>
<div class="stat"><h2>""" + str(total_count) + """</h2><p>Total Orders</p></div>
</div>
<div class="orders-container">
"""
    
    if not orders_list:
        html += """<div class="no-orders"><div class="empty-icon">&#128242;</div><h2>No orders yet</h2><p>When customers order through Vapi AI, orders appear here automatically.</p></div>"""
    else:
        for i, order in enumerate(orders_list[:50]):
            is_new = i < 3
            html += "<div class=\"order-card " + ("new\" if is_new else "\") + "\">"
            html += "<div class=\"order-header\"><span class=\"order-id\">#" + order.get("id", "---") + "</span>"
            html += "<span class=\"order-time\">" + order.get("completed_at", "--:--") + "</span>"
            html += "<span class=\"order-status\">NEW</span></div>"
            html += "<div class=\"order-details\"><p class=\"customer-name\">" + order.get("customer_name", "Walk-in") + "</p>"
            if order.get("customer_phone"):
                html += "<p>&#128222; " + order["customer_phone"] + "</p>"
            html += "<p>&#128230; " + order.get("order_type", "Pickup") + "</p>"
            html += "<hr style=\"border-color:#333;margin:10px 0\">"
            html += "<p><strong>Items:</strong></p><div class=\"item-list\">"
            for item in order.get("items", []):
                html += "<p>&bull; " + str(item.get("quantity", 1)) + "x " + item.get("name", "?")
                if item.get("options"):
                    html += " <span style=\"color:#fbbf24\">(" + item["options"] + ")</span>"
                if item.get("price"):
                    html += " <span style=\"color:#888\">" + str(item["price"]) + "</span>"
                html += "</p>"
            html += "</div>"
            if order.get("notes"):
                html += "<p style=\"color:#fbbf24\">&#128221; " + order["notes"] + "</p>"
            html += "<div class=\"order-total\">" + order.get("total", "0.00") + "</div></div></div>"
    
    html += """</div>
<script>
let lastCount = """ + str(len(orders_list)) + """;
setInterval(function(){
    fetch('/api/count').then(r=>r.json()).then(d=>{
        if(d.count > lastCount){location.reload();}
    });
},5000);
</script>
</body></html>"""
    
    return html

# ===========================================
# API ENDPOINTS
# ===========================================

@app.route("/api/orders")
def api_orders():
    """Get all orders as JSON"""
    return jsonify({"orders": orders_list})

@app.route("/api/count")
def api_count():
    """Get order count for auto-refresh"""
    return jsonify({"count": len(orders_list)})

@app.route("/api/orders/new")
def api_new_orders():
    """Get new unviewed orders"""
    new = [o for o in orders_list if not o.get("viewed", False)]
    for o in new:
        o["viewed"] = True
    return jsonify({"orders": new})

@app.route("/test")
def test():
    """Test if server is running"""
    return jsonify({
        "status": "ok",
        "message": "Dashboard server is running!",
        "time": datetime.now().strftime("%H:%M:%S"),
        "orders_count": len(orders_list)
    })

# ===========================================
# START
# ===========================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
