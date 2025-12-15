import asyncio
from aiohttp import web
from aiowebostv import WebOsClient, WebOsTvState
import json
import dataclasses

async def handle_index(request):
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no"/>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/hammer.js/2.0.8/hammer.js"></script>
  <title>Trackpad</title>
<style>
  html, body {
    margin: 0;
    height: 100%;
    background: #111;
    color: #fff; /* make all text pure white */
    touch-action: none; /* prevent browser gestures */
    user-select: none;
  }
  #pad {
    position: absolute;
    inset: 0;
    background: #222;
  }
  #status {
    position: fixed;
    top: 8px;
    left: 12px;
    font-size: 14px;
    color: #fff; /* override to white */
    z-index: 10; /* ensure on top */
  }
</style>
</head>
<body>
<div id="status">Connecting…</div>
<div id="pad"></div>

<script src="https://cdn.jsdelivr.net/npm/hammerjs@2.0.8/hammer.min.js"></script>
<script>
const ws = new WebSocket("ws://" + location.hostname + ":8080/ws");
const statusEl = document.getElementById("status");
const pad = document.getElementById("pad");

ws.onopen = () => statusEl.textContent = "Connected to server";
ws.onclose = () => statusEl.textContent = "Disconnected from server";
ws.onerror = () => statusEl.textContent = "Error";
ws.onmessage = function(event) { statusEl.textContent = event.data.toString(); }

function send(type, payload) {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type, ...payload }));
  }
}

// --- Hammer.js setup ---
const hammer = new Hammer(pad);

// enable tap, press, and pan
hammer.get('tap').set({ taps: 1 });
hammer.get('press').set({ time: 600 }); // long press threshold
hammer.get('pan').set({ direction: Hammer.DIRECTION_ALL, threshold: 0 });

// tap → left click
hammer.on("tap", ev => {
  send("click", { button: "left" });
});

// press → long press
hammer.on("press", ev => {
  send("longpress", { button: "left" });
});

// --- Accumulate deltas ---
let accumulatedDX = 0;
let accumulatedDY = 0;
let accumulatedScrollDX = 0;
let accumulatedScrollDY = 0;
let lastX = null;
let lastY = null;

// track movement
hammer.on("panstart", ev => {
  lastX = ev.center.x;
  lastY = ev.center.y;
});

hammer.on("panmove", ev => {
  const dx = ev.center.x - lastX;
  const dy = ev.center.y - lastY;
  
  if (ev.pointers.length === 2) {
    // two fingers → scroll
    accumulatedScrollDX += dx;
    accumulatedScrollDY += dy;
  } else {
    // single finger → move
    accumulatedDX += dx;
    accumulatedDY += dy;
  }

  lastX = ev.center.x;
  lastY = ev.center.y;
});

hammer.on("panend", () => {
  lastX = null;
  lastY = null;
});


// --- Send at 30Hz ---
setInterval(() => {
  if (accumulatedDX !== 0 || accumulatedDY !== 0) {
    if (accumulatedDX !== 0 && accumulatedDY !== 0) {
      // single finger move
      send("move", { dx: accumulatedDX, dy: accumulatedDY });
    }
    accumulatedDX = 0;
    accumulatedDY = 0;
  } else if (accumulatedScrollDY !== 0 || accumulatedScrollDX !== 0) {
    if (accumulatedScrollDY !== 0 && accumulatedScrollDX !== 0) {
      // two finger scroll (only vertical)
      send("scroll", { dx:accumulatedScrollDX, dy: accumulatedScrollDY });
    }
    accumulatedScrollDX = 0;
    accumulatedScrollDY = 0;
  }

}, 33); // ~30 times per second
</script>

</body>
</html>
    """
    return web.Response(text=html_content, content_type='text/html')
async def on_state_change(tv_state: WebOsTvState) -> None:
    """State changed callback."""
    # for the example, remove apps and inputs to make the output more readable
    state = dataclasses.replace(tv_state, apps={}, inputs={})
    #pprint(state)

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    await ws.send_str("Connecting to TV...");
    config = request.app["config"]
    client = WebOsClient(config["tv_ip"], config["client_key"])
    await client.register_state_update_callback(on_state_change)
    await client.connect()
    await ws.send_str("Connected to TV");

    async for msg in ws:
        if msg.type == web.WSMsgType.TEXT:
            data = json.loads(msg.data)
            if (data["type"] == "move"):
                await client.move(data["dx"], data["dy"]) 
            elif (data["type"] == "scroll"):
                await client.scroll(data["dx"], data["dy"]) 
            elif (data["type"] == "click"):
                await client.click()
        elif msg.type == web.WSMsgType.CLOSED:
            print("WebSocket connection closed")
            break   
        elif msg.type == web.WSMsgType.ERROR:
            print(f"WebSocket connection closed with exception {ws.exception()}")
            break

    await client.disconnect() 

    return ws

def main():
    with open("config.json", "r") as f:
        config = json.load(f)
        
    app = web.Application()
    app["config"] = config
    app.router.add_get("/", handle_index)
    app.router.add_get("/ws", websocket_handler) 
    web.run_app(app, port=8080)

if __name__ == "__main__":
    main()