from flask import Flask, request, jsonify
from datetime import datetime
import json
import os

app = Flask(__name__)

orders_list = []
order_counter = 100
vapi_logs = []

STATUS_COLORS = {
    "new": "#f59e0b",
    "preparing": "#3b82f6",
    "ready": "#22c55e",
    "completed": "#6b7280"
}

STATUS_LABELS = {
    "new": "NEW ORDER",
    "preparing": "PREPARING",
    "ready": "READY FOR COLLECTION",
    "completed": "COMPLETED"
}


def save_log(direction, data):
    log_entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "direction": direction,
        "data": data
    }
    vapi_logs.insert(0, log_entry)
    if len(vapi_logs) > 100:
        vapi_logs.pop()


def extract_order_data(payload):
    """Extract order data from various Vapi webhook formats"""
    tool_call_id = ""
    order_data = {}

    # Save raw payload for debugging
    save_log("received", payload)

    # Format 1: message.toolCallList (Vapi standard)
    if "message" in payload and isinstance(payload["message"], dict):
        msg = payload["message"]
        if "toolCallList" in msg and isinstance(msg["toolCallList"], list):
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

    # Format 2: direct payload with toolCallId
    if not order_data:
        order_data = {k: v for k, v in payload.items() if k not in ["message", "toolCallId"]}
        tool_call_id = payload.get("toolCallId", "")

    # Format 3: nested under result or order
    if not order_data and "order" in payload:
        order_data = payload["order"]
    if not order_data and "result" in payload and isinstance(payload["result"], dict):
        order_data = payload["result"]

    return tool_call_id, order_data


def normalize_items(items):
    """Ensure items are in a consistent format"""
    if not items:
        return []
    if isinstance(items, str):
        try:
            items = json.loads(items)
        except:
            return [{"name": str(items), "quantity": 1}]
    if not isinstance(items, list):
        return [{"name": str(items), "quantity": 1}]
    
    normalized = []
    for item in items:
        if isinstance(item, str):
            normalized.append({"name": item, "quantity": 1})
        elif isinstance(item, dict):
            normalized.append({
                "name": item.get("name", item.get("item", "Unknown")),
                "quantity": item.get("quantity", item.get("qty", 1)),
                "options": item.get("options", item.get("extras", item.get("notes", ""))),
                "price": item.get("price", "")
            })
        else:
            normalized.append({"name": str(item), "quantity": 1})
    return normalized


@app.route("/print-order", methods=["POST"])
def receive_order():
    try:
        payload = request.get_json(force=True, silent=True) or {}
        print("VAPI PAYLOAD: " + json.dumps(payload)[:1000])

        tool_call_id, order_data = extract_order_data(payload)

        global order_counter
        order_counter += 1

        # Extract all possible fields with fallbacks
        items = normalize_items(order_data.get("items", order_data.get("order_items", order_data.get("orderItems", []))))
        
        # Handle items as a single string (Vapi sometimes sends it this way)
        if not items and "items_description" in order_data:
            items = [{"name": order_data["items_description"], "quantity": 1}]
        if not items and "orderSummary" in order_data:
            items = [{"name": order_data["orderSummary"], "quantity": 1}]

        new_order = {
            "id": "ORD-" + str(order_counter),
            "customer_name": order_data.get("customerName", order_data.get("customer_name", order_data.get("name", "Walk-in"))),
            "customer_phone": order_data.get("customerPhone", order_data.get("customer_phone", order_data.get("phone", ""))),
            "items": items,
            "total": order_data.get("total", order_data.get("amount", order_data.get("price", "0.00"))),
            "order_type": order_data.get("orderType", order_data.get("order_type", order_data.get("type", "Pickup"))),
            "notes": order_data.get("notes", order_data.get("specialInstructions", order_data.get("instructions", ""))),
            "delivery_address": order_data.get("deliveryAddress", order_data.get("address", "")),
            "status": "new",
            "created_at": datetime.now().strftime("%H:%M:%S"),
            "date": datetime.now().strftime("d/m/Y").replace("d", "%d").replace("m", "%m").replace("Y", "%Y"),
            "timestamp": datetime.now().isoformat(),
            "raw_data": order_data  # Save raw for debug view
        }
        # Fix date format
        new_order["date"] = datetime.now().strftime("%d/%m/%Y")

        orders_list.insert(0, new_order)
        print("ORDER SAVED: " + new_order["id"] + " - " + new_order["customer_name"])
        print("ITEMS: " + json.dumps(new_order["items"]))
        print("NOTES: " + new_order["notes"])

        return jsonify({
            "results": [{
                "toolCallId": tool_call_id,
                "result": {"ok": True, "message": "Order " + new_order["id"] + " received"}
            }]
        }), 200

    except Exception as e:
        error_msg = str(e)
        print("ERROR: " + error_msg)
        return jsonify({
            "results": [{
                "toolCallId": "",
                "result": {"ok": True}
            }]
        }), 200


@app.route("/api/order/<order_id>/status", methods=["POST"])
def update_status(order_id):
    data = request.get_json() or {}
    new_status = data.get("status", "")
    for order in orders_list:
        if order["id"] == order_id:
            order["status"] = new_status
            if new_status == "completed":
                order["completed_at"] = datetime.now().strftime("%H:%M:%S")
            return jsonify({"ok": True, "order": order})
    return jsonify({"ok": False, "error": "Order not found"}), 404


@app.route("/api/order/<order_id>", methods=["GET"])
def get_order(order_id):
    for order in orders_list:
        if order["id"] == order_id:
            return jsonify(order)
    return jsonify({"error": "Not found"}), 404


@app.route("/api/orders")
def api_orders():
    return jsonify({"orders": orders_list})


@app.route("/api/count")
def api_count():
    return jsonify({
        "total": len(orders_list),
        "new": len([o for o in orders_list if o["status"] == "new"]),
        "preparing": len([o for o in orders_list if o["status"] == "preparing"]),
        "ready": len([o for o in orders_list if o["status"] == "ready"]),
        "completed": len([o for o in orders_list if o["status"] == "completed"])
    })


@app.route("/api/logs")
def api_logs():
    return jsonify({"logs": vapi_logs[:50]})


@app.route("/test")
def test():
    return jsonify({
        "status": "ok",
        "message": "Dashboard server running!",
        "time": datetime.now().strftime("%H:%M:%S"),
        "orders": len(orders_list)
    })


def build_page():
    today = datetime.now().strftime("%d/%m/%Y")
    counts = {
        "total": len(orders_list),
        "new": len([o for o in orders_list if o["status"] == "new"]),
        "preparing": len([o for o in orders_list if o["status"] == "preparing"]),
        "ready": len([o for o in orders_list if o["status"] == "ready"]),
        "completed": len([o for o in orders_list if o["status"] == "completed"])
    }

    active_orders = [o for o in orders_list if o["status"] != "completed"]
    completed_orders = [o for o in orders_list if o["status"] == "completed"]

    html = '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">'
    html += '<meta name="viewport" content="width=device-width,initial-scale=1">'
    html += '<title>Kebabish Original - Order Dashboard</title>'
    html += '<link rel="preconnect" href="https://fonts.googleapis.com">'
    html += '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">'
    html += '<style>'
    html += ':root{--bg:#0c0e12;--card:#181b24;--card2:#1e2230;--blue:#3b82f6;--green:#22c55e;--yellow:#f59e0b;--red:#ef4444;--gray:#6b7280;--text:#e5e7eb;--text2:#9ca3af}'
    html += '*{margin:0;padding:0;box-sizing:border-box}'
    html += 'body{font-family:Inter,Arial,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;line-height:1.5}'

    # Header
    html += '.header{background:linear-gradient(135deg,#1a1a3e,#0f1630);padding:24px 20px;text-align:center;border-bottom:1px solid #2a2d3e;position:sticky;top:0;z-index:100}'
    html += '.header h1{font-size:32px;font-weight:900;color:#fff;letter-spacing:-0.5px}'
    html += '.header p{color:var(--text2);font-size:14px;margin-top:4px}'

    # Stats bar
    html += '.stats-bar{display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:12px;padding:16px 20px;background:#141824;border-bottom:1px solid #1e2230;position:sticky;top:75px;z-index:99}'
    html += '.stat-card{background:var(--card);border-radius:12px;padding:14px;text-align:center;border:1px solid #252a3d}'
    html += '.stat-card h3{font-size:28px;font-weight:800}'
    html += '.stat-card p{font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:0.5px;margin-top:2px}'
    html += '.stat-card.blue h3{color:var(--blue)}.stat-card.yellow h3{color:var(--yellow)}'
    html += '.stat-card.orange h3{color:#f97316}.stat-card.green h3{color:var(--green)}.stat-card.gray h3{color:var(--gray)}'

    # Tabs
    html += '.tabs{display:flex;gap:4px;padding:12px 20px;background:#141824;border-bottom:1px solid #1e2230;overflow-x:auto}'
    html += '.tab-btn{background:transparent;border:1px solid #2a2d3e;color:var(--text2);padding:10px 20px;border-radius:8px;cursor:pointer;font-size:13px;font-weight:600;white-space:nowrap;transition:all 0.2s}'
    html += '.tab-btn:hover{background:#1e2230;color:#fff}'
    html += '.tab-btn.active{background:var(--blue);color:#fff;border-color:var(--blue)}'

    # Section headers
    html += '.section{padding:20px;max-width:900px;margin:0 auto}'
    html += '.section-title{font-size:18px;font-weight:700;margin-bottom:16px;display:flex;align-items:center;gap:8px}'

    # Order card
    html += '.order-card{background:var(--card);border:1px solid #252a3d;border-radius:16px;margin-bottom:16px;overflow:hidden;transition:all 0.2s}'
    html += '.order-card:hover{border-color:var(--blue)}'
    html += '.order-card.new{border-left:4px solid var(--yellow)}'
    html += '.order-card.preparing{border-left:4px solid var(--blue)}'
    html += '.order-card.ready{border-left:4px solid var(--green)}'
    html += '.order-card.completed{border-left:4px solid var(--gray);opacity:0.7}'

    # Card header
    html += '.card-header{padding:16px 20px;display:flex;justify-content:space-between;align-items:center;cursor:pointer}'
    html += '.order-id{font-size:18px;font-weight:800;color:var(--blue)}'
    html += '.order-time{font-size:12px;color:var(--text2)}'
    html += '.status-badge{padding:5px 14px;border-radius:20px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px}'
    html += '.status-badge.new{background:rgba(245,158,11,0.15);color:var(--yellow)}'
    html += '.status-badge.preparing{background:rgba(59,130,246,0.15);color:var(--blue)}'
    html += '.status-badge.ready{background:rgba(34,197,94,0.15);color:var(--green)}'
    html += '.status-badge.completed{background:rgba(107,114,128,0.15);color:var(--gray)}'

    # Customer info
    html += '.customer{padding:0 20px 16px}'
    html += '.customer-name{font-size:22px;font-weight:800;margin-bottom:6px}'
    html += '.customer-detail{font-size:14px;color:var(--text2);display:flex;align-items:center;gap:6px;margin:3px 0}'
    html += '.type-badge{display:inline-block;background:#1e3a5f;color:#60a5fa;padding:3px 10px;border-radius:6px;font-size:12px;font-weight:600;margin-left:8px}'

    # Items
    html += '.items{padding:0 20px 16px}'
    html += '.section-label{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--text2);margin-bottom:8px;font-weight:600}'
    html += '.item-row{display:flex;justify-content:space-between;align-items:flex-start;padding:10px 14px;background:var(--card2);border-radius:10px;margin-bottom:8px;border:1px solid #252a3d}'
    html += '.item-info{flex:1}'
    html += '.item-name{font-size:15px;font-weight:600}'
    html += '.item-options{font-size:12px;color:#fbbf24;margin-top:3px}'
    html += '.item-qty{background:var(--blue);color:#fff;padding:3px 10px;border-radius:6px;font-size:13px;font-weight:700}'
    html += '.item-price{font-size:14px;color:var(--text2);margin-left:10px;font-weight:500}'

    # Notes
    html += '.notes{padding:0 20px 16px}'
    html += '.notes-box{background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.2);border-radius:10px;padding:12px 14px;color:#fca5a5;font-size:14px}'
    html += '.notes-label{font-size:11px;text-transform:uppercase;color:#ef4444;font-weight:700;margin-bottom:4px;letter-spacing:0.5px}'

    # Total + Actions
    html += '.footer{padding:16px 20px;display:flex;justify-content:space-between;align-items:center;border-top:1px solid #252a3d;background:rgba(0,0,0,0.2)}'
    html += '.total{font-size:28px;font-weight:900;color:var(--green)}'
    html += '.actions{display:flex;gap:8px;flex-wrap:wrap}'
    html += '.btn{border:none;padding:10px 20px;border-radius:10px;font-size:13px;font-weight:700;cursor:pointer;transition:all 0.15s}'
    html += '.btn:hover{transform:translateY(-1px)}'
    html += '.btn:active{transform:translateY(0)}'
    html += '.btn-blue{background:var(--blue);color:#fff}'
    html += '.btn-green{background:var(--green);color:#fff}'
    html += '.btn-yellow{background:var(--yellow);color:#000}'
    html += '.btn-gray{background:var(--gray);color:#fff}'
    html += '.btn-red{background:var(--red);color:#fff}'
    html += '.btn:disabled{opacity:0.4;cursor:not-allowed;transform:none}'

    # Expand/collapse
    html += '.details{display:none}'
    html += '.details.open{display:block}'
    html += '.expand-btn{font-size:12px;color:var(--blue);cursor:pointer;font-weight:600;margin-left:auto}'

    # Empty state
    html += '.empty{text-align:center;padding:80px 20px}'
    html += '.empty-icon{font-size:64px;margin-bottom:16px}'
    html += '.empty h2{font-size:22px;color:var(--text2);margin-bottom:8px}'
    html += '.empty p{font-size:14px;color:var(--gray)}'

    # Completed section collapsed
    html += '.completed-section{opacity:0.7}'
    html += '.hidden{display:none}'

    # Notifications
    html += '.notif{position:fixed;top:20px;right:20px;background:var(--green);color:#fff;padding:14px 24px;border-radius:12px;font-weight:700;z-index:1000;display:none;animation:slideIn 0.3s ease;box-shadow:0 10px 40px rgba(34,197,94,0.3)}'
    html += '@keyframes slideIn{from{transform:translateX(400px);opacity:0}to{transform:translateX(0);opacity:1}}'

    # Audio icon
    html += '.audio-toggle{position:fixed;bottom:20px;right:20px;background:var(--card);border:1px solid #252a3d;padding:12px;border-radius:50%;cursor:pointer;z-index:100;font-size:20px}'

    html += '</style></head><body>'

    # Header
    html += '<div class="header"><h1>Kebabish Original</h1><p>Order Management Dashboard</p></div>'

    # Stats
    html += '<div class="stats-bar">'
    html += '<div class="stat-card blue"><h3>' + str(counts["total"]) + '</h3><p>Total Today</p></div>'
    html += '<div class="stat-card yellow"><h3>' + str(counts["new"]) + '</h3><p>New</p></div>'
    html += '<div class="stat-card orange"><h3>' + str(counts["preparing"]) + '</h3><p>Preparing</p></div>'
    html += '<div class="stat-card green"><h3>' + str(counts["ready"]) + '</h3><p>Ready</p></div>'
    html += '<div class="stat-card gray"><h3>' + str(counts["completed"]) + '</h3><p>Done</p></div>'
    html += '</div>'

    # Tabs
    html += '<div class="tabs">'
    html += '<button class="tab-btn active" onclick="showTab(\'active\')">Active Orders (' + str(len(active_orders)) + ')</button>'
    html += '<button class="tab-btn" onclick="showTab(\'completed\')">Completed (' + str(len(completed_orders)) + ')</button>'
    html += '<button class="tab-btn" onclick="showTab(\'debug\')" style="margin-left:auto;background:transparent;color:var(--text2)">Debug Vapi Data</button>'
    html += '</div>'

    # Notification
    html += '<div class="notif" id="notif"></div>'

    # Active Orders Tab
    html += '<div id="tab-active" class="section">'
    if not active_orders:
        html += '<div class="empty">'
        html += '<div class="empty-icon">&#128241;</div>'
        html += '<h2>No active orders</h2>'
        html += '<p>Orders from Vapi AI will appear here automatically.<br>New orders play a sound alert.</p>'
        html += '</div>'
    else:
        for order in active_orders:
            html += build_order_card(order)
    html += '</div>'

    # Completed Orders Tab
    html += '<div id="tab-completed" class="section hidden">'
    if not completed_orders:
        html += '<div class="empty">'
        html += '<div class="empty-icon">&#9989;</div>'
        html += '<h2>No completed orders yet</h2>'
        html += '</div>'
    else:
        for order in completed_orders:
            html += build_order_card(order)
    html += '</div>'

    # Debug Tab
    html += '<div id="tab-debug" class="section hidden">'
    html += '<h2 class="section-title">&#128269; What Vapi Sends You</h2>'
    html += '<p style="color:var(--text2);margin-bottom:16px;font-size:14px">This shows the exact data Vapi sends. Use this to check if customer details, items, and notes are being captured correctly.</p>'
    html += '<div id="debug-content">'
    html += '<p style="color:var(--text2);text-align:center;padding:40px">Loading latest Vapi payloads...</p>'
    html += '</div>'
    html += '</div>'

    # Audio toggle
    html += '<button class="audio-toggle" onclick="toggleAudio()" title="Toggle sound">&#128266;</button>'

    # JavaScript
    html += build_js()

    html += '</body></html>'
    return html


def build_order_card(order):
    s = order["status"]
    html = '<div class="order-card ' + s + '" id="order-' + order["id"] + '">'

    # Header
    html += '<div class="card-header" onclick="toggleDetails(\'' + order["id"] + '\')">'
    html += '<div><span class="order-id">#' + order["id"] + '</span>'
    html += '<span class="order-time"> ' + order.get("created_at", "--:--") + '</span></div>'
    html += '<div style="display:flex;align-items:center;gap:12px">'
    html += '<span class="status-badge ' + s + '">' + STATUS_LABELS.get(s, s.upper()) + '</span>'
    html += '<span class="expand-btn" id="expand-' + order["id"] + '">Show Details &#9660;</span>'
    html += '</div></div>'

    # Details
    html += '<div class="details" id="details-' + order["id"] + '">'

    # Customer
    html += '<div class="customer">'
    html += '<div class="customer-name">' + order.get("customer_name", "Walk-in")
    html += '<span class="type-badge">' + order.get("order_type", "Pickup") + '</span></div>'
    if order.get("customer_phone"):
        html += '<div class="customer-detail">&#128222; ' + order["customer_phone"] + '</div>'
    if order.get("delivery_address"):
        html += '<div class="customer-detail">&#128205; ' + order["delivery_address"] + '</div>'
    html += '</div>'

    # Items
    items = order.get("items", [])
    if items:
        html += '<div class="items">'
        html += '<div class="section-label">Order Items</div>'
        for item in items:
            html += '<div class="item-row">'
            html += '<div class="item-info">'
            html += '<div class="item-name">' + str(item.get("name", "Unknown")) + '</div>'
            if item.get("options"):
                html += '<div class="item-options">' + str(item["options"]) + '</div>'
            if item.get("price"):
                html += '<div class="item-price">' + str(item["price"]) + '</div>'
            html += '</div>'
            html += '<span class="item-qty">x' + str(item.get("quantity", 1)) + '</span>'
            html += '</div>'
        html += '</div>'

    # Notes
    if order.get("notes"):
        html += '<div class="notes">'
        html += '<div class="notes-box">'
        html += '<div class="notes-label">Special Instructions</div>'
        html += order["notes"]
        html += '</div></div>'

    # Footer with actions
    html += '<div class="footer">'
    html += '<div class="total">' + str(order.get("total", "0.00")) + '</div>'
    html += '<div class="actions">'

    if s == "new":
        html += '<button class="btn btn-blue" onclick="updateStatus(event,\'' + order["id"] + '\',\'preparing\')">&#9889; Start Preparing</button>'
        html += '<button class="btn btn-red" onclick="updateStatus(event,\'' + order["id"] + '\',\'completed\')">Cancel</button>'
    elif s == "preparing":
        html += '<button class="btn btn-green" onclick="updateStatus(event,\'' + order["id"] + '\',\'ready\')">&#9989; Mark Ready</button>'
        html += '<button class="btn btn-yellow" onclick="updateStatus(event,\'' + order["id"] + '\',\'new\')">Back to New</button>'
    elif s == "ready":
        html += '<button class="btn btn-gray" onclick="updateStatus(event,\'' + order["id"] + '\',\'completed\')">&#128230; Collected</button>'

    html += '</div></div>'
    html += '</div></div>'
    return html


def build_js():
    html = '<script>'

    # Audio context for beep
    html += 'var audioEnabled=true;'
    html += 'var lastTotal=' + str(len(orders_list)) + ';'
    html += 'var lastCounts={new:' + str(len([o for o in orders_list if o["status"]=="new"])) + '};'

    html += 'function toggleAudio(){'
    html += 'audioEnabled=!audioEnabled;'
    html += 'document.querySelector(\'.audio-toggle\').innerHTML=audioEnabled?\'&#128266;\':\'&#128263;\';'
    html += '}'

    html += 'function playAlert(){'
    html += 'if(!audioEnabled)return;'
    html += 'try{var ctx=new(window.AudioContext||window.webkitAudioContext)();'
    html += 'for(var i=0;i<3;i++){var o=ctx.createOscillator();var g=ctx.createGain();'
    html += 'o.connect(g);g.connect(ctx.destination);o.frequency.value=800+i*200;'
    html += 'o.type=\'sine\';g.gain.setValueAtTime(0.3,ctx.currentTime+i*0.15);'
    html += 'g.gain.exponentialRampToValueAtTime(0.01,ctx.currentTime+i*0.15+0.1);'
    html += 'o.start(ctx.currentTime+i*0.15);o.stop(ctx.currentTime+i*0.15+0.1)}'
    html += '}catch(e){console.log(\'Audio error:\',e)}'
    html += '}'

    html += 'function showNotif(msg){'
    html += 'var n=document.getElementById(\'notif\');n.textContent=msg;'
    html += 'n.style.display=\'block\';setTimeout(function(){n.style.display=\'none\'},3000);'
    html += '}'

    # Tab switching
    html += 'function showTab(tab){'
    html += 'document.querySelectorAll(\'.tab-btn\').forEach(function(b){b.classList.remove(\'active\')});'
    html += 'event.target.classList.add(\'active\');'
    html += 'document.getElementById(\'tab-active\').classList.add(\'hidden\');'
    html += 'document.getElementById(\'tab-completed\').classList.add(\'hidden\');'
    html += 'document.getElementById(\'tab-debug\').classList.add(\'hidden\');'
    html += 'document.getElementById(\'tab-\'+tab).classList.remove(\'hidden\');'
    html += 'if(tab===\'debug\')loadDebug();'
    html += '}'

    # Toggle details
    html += 'function toggleDetails(id){'
    html += 'var el=document.getElementById(\'details-\'+id);'
    html += 'var btn=document.getElementById(\'expand-\'+id);'
    html += 'if(el.classList.contains(\'open\')){el.classList.remove(\'open\');btn.innerHTML=\'Show Details &#9660;\';}'
    html += 'else{el.classList.add(\'open\');btn.innerHTML=\'Hide Details &#9650;\';}'
    html += '}'

    # Update status
    html += 'function updateStatus(e,id,status){'
    html += 'e.stopPropagation();'
    html += 'fetch(\'/api/order/\'+id+\'/status\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify({status:status})})'
    html += '.then(function(r){return r.json()})'
    html += '.then(function(d){if(d.ok){location.reload()}})'
    html += '}'

    # Load debug data
    html += 'function loadDebug(){'
    html += 'fetch(\'/api/logs\').then(function(r){return r.json()})'
    html += '.then(function(d){'
    html += 'var html=\'\';'
    html += 'if(!d.logs||d.logs.length===0){'
    html += 'document.getElementById(\'debug-content\').innerHTML=\'<p style="color:var(--text2);text-align:center;padding:40px">No Vapi data received yet. Place a test order to see data here.</p>\';'
    html += 'return;}'
    html += 'd.logs.forEach(function(log,i){'
    html += 'html+=\'<div style="background:var(--card);border:1px solid #252a3d;border-radius:12px;padding:16px;margin-bottom:12px">\';'
    html += 'html+=\'<div style="display:flex;justify-content:space-between;margin-bottom:8px"><span style="color:var(--blue);font-weight:700;font-size:13px">\'+(i===0?\'LATEST\':\'#\'+(i+1))+\'</span><span style="color:var(--text2);font-size:12px">\'+log.time+\'</span></div>\';'
    html += 'html+=\'<pre style="background:#0c0e12;padding:12px;border-radius:8px;font-size:12px;overflow-x:auto;color:#a5b4fc;line-height:1.6">\'+JSON.stringify(log.data,null,2)+\'</pre>\';'
    html += 'html+=\'</div>\';'
    html += '});'
    html += 'document.getElementById(\'debug-content\').innerHTML=html;'
    html += '});'
    html += '}'

    # Auto-refresh
    html += 'setInterval(function(){'
    html += 'fetch(\'/api/count\').then(function(r){return r.json()})'
    html += '.then(function(d){'
    html += 'if(d.total>lastTotal){playAlert();showNotif(\'New order received!\');setTimeout(function(){location.reload()},800)}'
    html += 'lastTotal=d.total;'
    html += '});'
    html += '},4000);'

    html += '</script>'
    return html


@app.route("/")
def dashboard():
    return build_page()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
