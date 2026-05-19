from flask import Flask, request, jsonify
from datetime import datetime
import json
import os

app = Flask(__name__)

orders_list = []
order_counter = 100

@app.route("/print-order", methods=["POST"])
def receive_order():
    try:
        payload = request.get_json(force=True, silent=True) or {}
        print("VAPI DATA: " + json.dumps(payload)[:500])
        
        tool_call_id = ""
        order_data = {}
        
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
        
        if not order_data:
            order_data = {k: v for k, v in payload.items() if k not in ["message", "toolCallId"]}
            tool_call_id = payload.get("toolCallId", "")
        
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
        print("ORDER SAVED: " + new_order["id"] + " - " + new_order["customer_name"])
        
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

@app.route("/")
def dashboard():
    today = datetime.now().strftime("%d/%m/%Y")
    today_count = len([o for o in orders_list if o.get("date") == today])
    total_count = len(orders_list)
    
    html = '<!DOCTYPE html><html><head><meta charset="UTF-8">'
    html += '<title>Kebabish Original - Orders</title>'
    html += '<style>'
    html += '*{margin:0;padding:0;box-sizing:border-box}'
    html += 'body{font-family:Arial;background:#0a0a0a;color:#fff;min-height:100vh}'
    html += '.header{background:linear-gradient(135deg,#1a1a2e,#16213e);padding:20px;text-align:center;border-bottom:2px solid #3b82f6}'
    html += '.header h1{color:#3b82f6;font-size:28px}'
    html += '.stats{display:flex;justify-content:center;gap:30px;padding:20px;background:#111}'
    html += '.stat{text-align:center;padding:15px 30px;background:#1a1a2e;border-radius:10px;border:1px solid #3b82f6}'
    html += '.stat h2{color:#22c55e;font-size:32px;margin:0}'
    html += '.stat p{color:#888;margin-top:5px;font-size:14px}'
    html += '.orders{padding:20px;max-width:800px;margin:0 auto}'
    html += '.card{background:#1a1a2e;border:1px solid #3b82f6;border-radius:12px;padding:20px;margin-bottom:15px}'
    html += '.card.new{border-color:#22c55e;box-shadow:0 0 20px rgba(34,197,94,0.3)}'
    html += '.top{display:flex;justify-content:space-between;margin-bottom:10px}'
    html += '.id{font-size:18px;font-weight:bold;color:#3b82f6}'
    html += '.time{color:#888;font-size:14px}'
    html += '.badge{background:#22c55e;color:#000;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:bold}'
    html += '.name{font-size:20px;font-weight:bold;margin:5px 0}'
    html += '.detail{color:#ccc;margin:5px 0}'
    html += '.total{font-size:24px;color:#22c55e;font-weight:bold;text-align:right;margin-top:10px}'
    html += '.empty{text-align:center;padding:60px;color:#555}'
    html += '</style></head><body>'
    
    html += '<div class="header"><h1>Kebabish Original</h1><p>Live Order Dashboard</p></div>'
    html += '<div class="stats">'
    html += '<div class="stat"><h2>' + str(today_count) + '</h2><p>Today</p></div>'
    html += '<div class="stat"><h2>' + str(total_count) + '</h2><p>Total</p></div>'
    html += '</div>'
    html += '<div class="orders">'
    
    if not orders_list:
        html += '<div class="empty"><h1>&#128242;</h1><h2>No orders yet</h2>'
        html += '<p>Orders from Vapi AI will appear here automatically.</p></div>'
    else:
        for i, order in enumerate(orders_list[:50]):
            is_new = ' new' if i < 3 else ''
            html += '<div class="card' + is_new + '">'
            html += '<div class="top"><span class="id">#' + order.get("id", "---") + '</span>'
            html += '<span class="time">' + order.get("completed_at", "--:--") + '</span>'
            html += '<span class="badge">NEW</span></div>'
            html += '<div class="name">' + order.get("customer_name", "Walk-in") + '</div>'
            if order.get("customer_phone"):
                html += '<div class="detail">&#128222; ' + order["customer_phone"] + '</div>'
            html += '<div class="detail">&#128230; ' + order.get("order_type", "Pickup") + '</div>'
            html += '<hr style="border-color:#333;margin:10px 0">'
            html += '<div class="detail"><strong>Items:</strong></div>'
            for item in order.get("items", []):
                html += '<div class="detail">&bull; ' + str(item.get("quantity", 1)) + 'x ' + item.get("name", "?")
                if item.get("options"):
                    html += ' <span style="color:#fbbf24">(' + item["options"] + ')</span>'
                html += '</div>'
            html += '<div class="total">' + order.get("total", "0.00") + '</div>'
            html += '</div>'
    
    html += '</div>'
    html += '<script>'
    html += 'let lastCount=' + str(len(orders_list)) + ';'
    html += 'setInterval(function(){'
    html += 'fetch("/api/count").then(r=>r.json()).then(d=>{'
    html += 'if(d.count>lastCount){location.reload();}'
    html += '});},5000);'
    html += '</script></body></html>'
    
    return html

@app.route("/api/orders")
def api_orders():
    return jsonify({"orders": orders_list})

@app.route("/api/count")
def api_count():
    return jsonify({"count": len(orders_list)})

@app.route("/api/orders/new")
def api_new_orders():
    new = [o for o in orders_list if not o.get("viewed", False)]
    for o in new:
        o["viewed"] = True
    return jsonify({"orders": new})

@app.route("/test")
def test():
    return jsonify({
        "status": "ok",
        "message": "Dashboard server running!",
        "time": datetime.now().strftime("%H:%M:%S"),
        "orders": len(orders_list)
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
