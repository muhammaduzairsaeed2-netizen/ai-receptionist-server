from flask import Flask, request, jsonify
from datetime import datetime
import json
import os
import time

app = Flask(__name__)

orders_list = []
order_counter = 100
recent_signatures = {}
DUPLICATE_WINDOW = 30


def is_duplicate(order_data):
    items = order_data.get("items", order_data.get("orderItems", []))
    items_str = json.dumps(items, sort_keys=True) if items else ""
    signature = "|".join([
        str(order_data.get("customerName", order_data.get("customer_name", ""))),
        items_str,
        str(order_data.get("notes", "")),
        str(order_data.get("total", "")),
        str(order_data.get("orderType", order_data.get("order_type", "")))
    ])
    now = time.time()
    global recent_signatures
    recent_signatures = {k: v for k, v in recent_signatures.items() if now - v < DUPLICATE_WINDOW}
    if signature in recent_signatures:
        print("DUPLICATE BLOCKED")
        return True
    recent_signatures[signature] = now
    return False


def extract_order_data(payload):
    tool_call_id = ""
    order_data = {}

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

    if not order_data:
        order_data = {k: v for k, v in payload.items() if k not in ["message", "toolCallId"]}
        tool_call_id = payload.get("toolCallId", "")

    if not order_data and "order" in payload:
        order_data = payload["order"]
    if not order_data and "result" in payload and isinstance(payload["result"], dict):
        order_data = payload["result"]

    return tool_call_id, order_data


def normalize_items(items):
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
                "options": item.get("options", item.get("extras", "")),
                "price": item.get("price", "")
            })
        else:
            normalized.append({"name": str(item), "quantity": 1})
    return normalized


@app.route("/print-order", methods=["POST"])
def receive_order():
    try:
        payload = request.get_json(force=True, silent=True) or {}
        print("VAPI: " + json.dumps(payload)[:500])

        tool_call_id, order_data = extract_order_data(payload)

        if is_duplicate(order_data):
            return jsonify({"results": [{"toolCallId": tool_call_id, "result": {"ok": True}}]}), 200

        global order_counter
        order_counter += 1

        items = normalize_items(order_data.get("items", order_data.get("orderItems", [])))

        new_order = {
            "id": "ORD-" + str(order_counter),
            "customer_name": order_data.get("customerName", order_data.get("customer_name", "Walk-in")),
            "customer_phone": order_data.get("customerPhone", order_data.get("customer_phone", "")),
            "items": items,
            "total": order_data.get("total", order_data.get("amount", "0.00")),
            "order_type": order_data.get("orderType", order_data.get("order_type", "Pickup")),
            "notes": order_data.get("notes", order_data.get("instructions", "")),
            "delivery_address": order_data.get("deliveryAddress", order_data.get("address", "")),
            "status": "new",
            "created_at": datetime.now().strftime("%H:%M:%S"),
            "timestamp": datetime.now().isoformat()
        }

        orders_list.insert(0, new_order)
        print("SAVED: " + new_order["id"] + " - " + new_order["customer_name"])

        return jsonify({"results": [{"toolCallId": tool_call_id, "result": {"ok": True}}]}), 200

    except Exception as e:
        print("ERROR: " + str(e))
        return jsonify({"results": [{"toolCallId": "", "result": {"ok": True}}]}), 200


@app.route("/api/order/<order_id>/status", methods=["POST"])
def update_status(order_id):
    data = request.get_json() or {}
    new_status = data.get("status", "")
    for order in orders_list:
        if order["id"] == order_id:
            order["status"] = new_status
            return jsonify({"ok": True})
    return jsonify({"ok": False}), 404


@app.route("/api/count")
def api_count():
    return jsonify({
        "new": len([o for o in orders_list if o["status"] == "new"]),
        "ready": len([o for o in orders_list if o["status"] == "ready"])
    })


@app.route("/test")
def test():
    return jsonify({"status": "ok", "orders": len(orders_list)})


@app.route("/")
def dashboard():
    new_orders = [o for o in orders_list if o["status"] == "new"]
    ready_orders = [o for o in orders_list if o["status"] == "ready"]

    html = '<!DOCTYPE html><html><head><meta charset="UTF-8">'
    html += '<meta name="viewport" content="width=device-width,initial-scale=1">'
    html += '<title>Kebabish - Orders</title>'
    html += '<style>'
    html += '*{margin:0;padding:0;box-sizing:border-box}'
    html += 'body{font-family:system-ui,-apple-system,Arial,sans-serif;background:#0a0a0a;color:#fff;padding:16px}'
    html += '.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}'
    html += 'h1{font-size:24px}'
    html += '.badge{background:#22c55e;color:#000;padding:4px 14px;border-radius:20px;font-size:14px;font-weight:700}'

    html += '.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}'
    html += '@media(max-width:768px){.grid{grid-template-columns:1fr}}'

    html += '.col{background:#141414;border-radius:16px;padding:16px;min-height:200px}'
    html += '.col-title{font-size:16px;font-weight:700;margin-bottom:12px;padding-bottom:12px;border-bottom:2px solid #222}'
    html += '.col-new .col-title{color:#f59e0b;border-color:#f59e0b}'
    html += '.col-ready .col-title{color:#22c55e;border-color:#22c55e}'

    html += '.card{background:#1a1a1a;border:1px solid #2a2a2a;border-radius:14px;padding:16px;margin-bottom:12px}'
    html += '.card-new{border-left:4px solid #f59e0b}'
    html += '.card-ready{border-left:4px solid #22c55e}'

    html += '.row{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}'
    html += '.order-id{font-weight:700;color:#3b82f6;font-size:16px}'
    html += '.time{color:#888;font-size:12px}'
    html += '.name{font-size:20px;font-weight:700;margin:8px 0}'
    html += '.phone{color:#aaa;font-size:14px}'
    html += '.type{display:inline-block;background:#1e3a5f;color:#60a5fa;padding:2px 10px;border-radius:6px;font-size:12px;font-weight:600}'

    html += '.items{margin:12px 0}'
    html += '.item{background:#222;border-radius:10px;padding:10px 12px;margin-bottom:8px;display:flex;justify-content:space-between;align-items:center}'
    html += '.item-name{font-weight:600}'
    html += '.item-options{color:#fbbf24;font-size:13px;margin-top:2px}'
    html += '.item-qty{background:#3b82f6;color:#fff;padding:4px 12px;border-radius:8px;font-weight:700;font-size:14px}'

    html += '.notes{background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.2);border-radius:10px;padding:12px;color:#fca5a5;font-size:14px;margin:10px 0}'
    html += '.notes-label{color:#ef4444;font-size:11px;font-weight:700;margin-bottom:4px;text-transform:uppercase}'

    html += '.total{font-size:22px;font-weight:800;color:#22c55e}'

    html += '.btn{width:100%;padding:14px;border:none;border-radius:12px;font-size:16px;font-weight:700;cursor:pointer;margin-top:12px}'
    html += '.btn-green{background:#22c55e;color:#000}'
    html += '.btn-green:hover{background:#16a34a}'
    html += '.btn-gray{background:#374151;color:#fff}'
    html += '.btn-gray:hover{background:#4b5563}'
    html += '.btn-red{background:#dc2626;color:#fff}'

    html += '.empty{text-align:center;color:#555;padding:40px;font-size:14px}'
    html += '.addr{color:#aaa;font-size:13px;margin-top:4px}'

    html += '.notif{position:fixed;top:16px;right:16px;background:#22c55e;color:#000;padding:14px 24px;border-radius:12px;font-weight:700;display:none;z-index:1000}'

    html += '</style></head><body>'

    html += '<div class="top"><h1>Kebabish Original</h1>'
    html += '<span class="badge">' + str(len(new_orders)) + ' New</span></div>'

    html += '<div class="grid">'

    # NEW COLUMN
    html += '<div class="col col-new">'
    html += '<div class="col-title">New Orders (' + str(len(new_orders)) + ')</div>'
    if not new_orders:
        html += '<div class="empty">No new orders yet. Orders will appear here when Vapi sends them.</div>'
    for order in new_orders:
        html += build_card(order, True)
    html += '</div>'

    # READY COLUMN
    html += '<div class="col col-ready">'
    html += '<div class="col-title">Ready for Collection (' + str(len(ready_orders)) + ')</div>'
    if not ready_orders:
        html += '<div class="empty">No orders ready yet. Press "ORDER READY" on a new order to move it here.</div>'
    for order in ready_orders:
        html += build_card(order, False)
    html += '</div>'

    html += '</div>'

    html += '<div class="notif" id="notif">New order!</div>'

    # JS
    html += '<script>'
    html += 'var lastNew=' + str(len(new_orders)) + ';'

    html += 'function playSound(){'
    html += 'try{var c=new(window.AudioContext||window.webkitAudioContext)();'
    html += 'for(var i=0;i<3;i++){var o=c.createOscillator(),g=c.createGain();'
    html += 'o.connect(g);g.connect(c.destination);o.frequency.value=900+i*150;'
    html += 'o.type="sine";g.gain.setValueAtTime(0.3,c.currentTime+i*0.12);'
    html += 'g.gain.exponentialRampToValueAtTime(0.01,c.currentTime+i*0.12+0.08);'
    html += 'o.start(c.currentTime+i*0.12);o.stop(c.currentTime+i*0.12+0.08)}'
    html += '}catch(e){}}'

    html += 'function move(orderId,status){'
    html += 'fetch("/api/order/"+orderId+"/status",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({status:status})})'
    html += '.then(function(r){return r.json()}).then(function(d){if(d.ok)location.reload()});'
    html += '}'

    html += 'setInterval(function(){'
    html += 'fetch("/api/count").then(function(r){return r.json()})'
    html += '.then(function(d){'
    html += 'if(d.new>lastNew){playSound();var n=document.getElementById("notif");n.style.display="block";setTimeout(function(){n.style.display="none"},3000);setTimeout(function(){location.reload()},1000)}'
    html += 'lastNew=d.new;'
    html += '});},4000);'

    html += '</script></body></html>'
    return html


def build_card(order, is_new):
    html = '<div class="card card-' + order["status"] + '">'

    html += '<div class="row">'
    html += '<span class="order-id">#' + order["id"] + '</span>'
    html += '<span class="time">' + order.get("created_at", "") + '</span>'
    html += '</div>'

    html += '<div class="name">' + order.get("customer_name", "Walk-in")
    html += ' <span class="type">' + order.get("order_type", "Pickup") + '</span></div>'

    if order.get("customer_phone"):
        html += '<div class="phone">' + order["customer_phone"] + '</div>'
    if order.get("delivery_address"):
        html += '<div class="addr">' + order["delivery_address"] + '</div>'

    if order.get("items"):
        html += '<div class="items">'
        for item in order["items"]:
            html += '<div class="item">'
            html += '<div><div class="item-name">' + str(item.get("name", "")) + '</div>'
            if item.get("options"):
                html += '<div class="item-options">' + str(item["options"]) + '</div>'
            html += '</div>'
            html += '<span class="item-qty">x' + str(item.get("quantity", 1)) + '</span>'
            html += '</div>'
        html += '</div>'

    if order.get("notes"):
        html += '<div class="notes">'
        html += '<div class="notes-label">Special Instructions</div>'
        html += order["notes"] + '</div>'

    html += '<div class="row">'
    html += '<span class="total">' + str(order.get("total", "0.00")) + '</span>'
    html += '</div>'

    if is_new:
        html += '<button class="btn btn-green" onclick="move(\'' + order["id"] + '\',\'ready\')">ORDER READY</button>'
        html += '<button class="btn btn-red" style="margin-top:6px;background:#7f1d1d" onclick="move(\'' + order["id"] + '\',\'completed\')">Delete</button>'
    else:
        html += '<button class="btn btn-gray" onclick="move(\'' + order["id"] + '\',\'completed\')">COLLECTED</button>'

    html += '</div>'
    return html


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
