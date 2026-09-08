"""Walk EVERY sidebar route (plus detail/public pages) in headless Chrome over raw
CDP after a real form login, and fail on: placeholder text ("not available in
this release" / "coming soon" / "being built"), the NotFound page, uncaught page
errors, console errors, or any /api/ response >= 400 (401 on public pages excluded).
Writes one screenshot per route to $OUT.
"""
import base64, json, os, subprocess, sys, tempfile, time, urllib.request
import websocket

BASE = "http://127.0.0.1:5173"
OUT = os.environ.get("OUT", ".")
EMAIL = os.environ.get("EMAIL", "khadar.demo@example.com")
PASSWORD = os.environ.get("PASSWORD", "DemoPassw0rd!2026")
PORT = 9334
PLACEHOLDER_MARKERS = ["not available in this release", "This screen is being built", "coming soon", "Page not found"]

ROUTES = [
    "/dashboard", "/customers", "/customers/new", "/catalog",
    "/quotes", "/cpq", "/invoices", "/payments", "/collections",
    "/plans-pricing", "/subscriptions", "/trials", "/usage", "/proration", "/dunning",
    "/customer-lifecycle", "/customer-portal", "/hosted-payment-pages",
    "/expenses", "/projects", "/timesheets",
    "/revenue-intelligence", "/reports", "/ai-billing", "/activity",
    "/platforms/mobile", "/platforms/desktop",
    "/control-center/action-center", "/control-center/approvals", "/control-center/calendar",
    "/control-center/reconciliation", "/control-center/audit-log", "/control-center/migration",
    "/automation", "/customization", "/settings?tab=integrations", "/settings",
]
EXTRA = [r for r in os.environ.get("EXTRA_ROUTES", "").split(",") if r]

profile = tempfile.mkdtemp(prefix="rooman-verify-")
chrome = subprocess.Popen(["/usr/bin/google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                           f"--remote-debugging-port={PORT}", f"--user-data-dir={profile}", "--window-size=1440,900", "about:blank"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
for _ in range(100):
    try:
        page = next(t for t in json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json")) if t["type"] == "page"); break
    except Exception:
        time.sleep(0.2)
else:
    sys.exit("chrome debugger never came up")

ws = websocket.create_connection(page["webSocketDebuggerUrl"], suppress_origin=True); ws.settimeout(60)
_id = 0; load_events = 0
cur = {"console": [], "api": []}

def _ev(msg):
    global load_events
    m, p = msg.get("method"), msg.get("params", {})
    if m == "Page.loadEventFired": load_events += 1
    elif m == "Runtime.exceptionThrown":
        cur["console"].append("pageerror: " + str(p["exceptionDetails"].get("exception", {}).get("description", p["exceptionDetails"].get("text", "")))[:220])
    elif m == "Runtime.consoleAPICalled" and p.get("type") == "error":
        cur["console"].append(" ".join(str(a.get("value", a.get("description", ""))) for a in p.get("args", []))[:220])
    elif m == "Network.responseReceived":
        r = p["response"]
        if "/api/" in r["url"] and r["status"] >= 400: cur["api"].append(f'{r["status"]} {r["url"].split("/api/v1")[-1]}')

def send(method, **params):
    global _id; _id += 1
    ws.send(json.dumps({"id": _id, "method": method, "params": params}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == _id:
            if "error" in msg: raise RuntimeError(f"{method}: {msg['error']}")
            return msg.get("result", {})
        _ev(msg)

def pump(sec):
    end = time.time() + sec; ws.settimeout(0.2)
    try:
        while time.time() < end:
            try: _ev(json.loads(ws.recv()))
            except websocket.WebSocketTimeoutException: pass
    finally: ws.settimeout(60)

def ev(expr): return send("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True).get("result", {}).get("value")
def wait_for(expr, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        if ev(expr): return True
        pump(0.3)
    return False
def goto(url, settle=2.0):
    global load_events
    before = load_events; send("Page.navigate", url=url); end = time.time() + 30
    while load_events == before and time.time() < end: pump(0.2)
    pump(settle)
def shot(name):
    with open(os.path.join(OUT, f"{name}.png"), "wb") as f: f.write(base64.b64decode(send("Page.captureScreenshot", format="png")["data"]))

send("Page.enable"); send("Runtime.enable"); send("Network.enable")
send("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)

# login through the real form
goto(f"{BASE}/login"); assert wait_for("!!document.querySelector('input[type=email]')"), "login form missing"
ev(f"""(()=>{{const s=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;const f=(q,v)=>{{const e=document.querySelector(q);s.call(e,v);e.dispatchEvent(new Event('input',{{bubbles:true}}))}};f('input[type=email]',{json.dumps(EMAIL)});f('input[type=password]',{json.dumps(PASSWORD)});return true}})()""")
pump(0.3); ev("document.querySelector('button[type=submit]').click();true")
assert wait_for("!location.pathname.startsWith('/login')"), "login did not redirect"
pump(2)

failures = []
for route in ROUTES + EXTRA:
    cur["console"].clear(); cur["api"].clear()
    goto(f"{BASE}{route}")
    text = ev("document.body.innerText") or ""
    heading = ev("document.querySelector('main h1, h1, h2')?.textContent?.trim() ?? '(none)'")
    problems = []
    for mk in PLACEHOLDER_MARKERS:
        if mk.lower() in text.lower(): problems.append(f"placeholder text: '{mk}'")
    if cur["console"]: problems.append(f"{len(cur['console'])} console error(s): " + " | ".join(cur["console"][:2]))
    api = [a for a in cur["api"] if not (route.startswith("/pay/") or route.startswith("/quote/") or route.startswith("/checkout/"))]
    if api: problems.append("API errors: " + " | ".join(api[:3]))
    name = route.strip("/").replace("/", "_").replace("?", "_").replace("=", "-") or "root"
    shot(name)
    status = "OK " if not problems else "FAIL"
    print(f"[{status}] {route:<38} heading={heading[:40]!r}" + ("" if not problems else "\n        " + "\n        ".join(problems)))
    if problems: failures.append((route, problems))

print(f"\n{len(ROUTES)+len(EXTRA)} routes checked, {len(failures)} with problems")
ws.close(); chrome.terminate()
sys.exit(1 if failures else 0)
