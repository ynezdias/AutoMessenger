"""Local browser chat to test Walter with no AWS or Salesforce.

Usage:  python -m server.webchat        then open http://localhost:8765

You play the merchant — pick any contact from testing.csv in the dropdown; each
one has its own conversation thread. Walter answers through the exact
production pipeline: same model, guardrails, classification, and history
handling. State lives in a local JSON file only - the real DynamoDB table, SQS
queues, and SNS topic are never touched.
"""
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config

# Force everything local before other modules read the config.
config.CONVERSATIONS_TABLE = ""
config.OUTBOUND_QUEUE_URL = ""
config.ESCALATIONS_TOPIC_ARN = ""

from . import history, main as worker  # noqa: E402
from .outreach import OPENER, load_contacts  # noqa: E402

PORT = 8765
CONTACTS: dict[str, dict] = {}
try:
    for row in load_contacts(str(config.ROOT / "testing.csv"), None):
        contact = {**row, "phone": "sim-" + row["phone"]}
        CONTACTS[contact["phone"]] = contact
except OSError:
    pass
if not CONTACTS:
    CONTACTS["sim-ynez"] = {"first_name": "Ynez", "company": "Google",
                            "phone": "sim-ynez"}

store = history.ConversationStore()


def seed() -> None:
    for contact in CONTACTS.values():
        convo = store.get(contact["phone"])
        if not convo["messages"]:
            convo["merchant_first"] = contact["first_name"]
            convo["company"] = contact.get("company", "")
            store.append(convo, "walter", OPENER.format(first=contact["first_name"]))
            store.save(convo)


def state(phone: str) -> dict:
    contact = CONTACTS[phone]
    convo = store.get(phone)
    return {
        "phone": phone,
        "first": contact["first_name"],
        "status": convo["status"],
        "contacts": [
            {"phone": c["phone"], "first": c["first_name"],
             "company": c.get("company", "")}
            for c in CONTACTS.values()
        ],
        "messages": [{"role": m["role"], "text": m["text"]} for m in convo["messages"]],
    }


def _default_contact() -> str:
    return next(iter(CONTACTS))


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Walter local test</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body { font-family: system-ui, sans-serif; background: #111; color: #eee;
         max-width: 480px; margin: 0 auto; padding: 16px; }
  h3 { font-weight: 600; } small { color: #888; }
  select { padding: 8px; border-radius: 8px; border: 1px solid #444;
           background: #1c1c1e; color: #eee; width: 100%; }
  #thread { display: flex; flex-direction: column; gap: 6px; margin: 16px 0; }
  .b { padding: 9px 13px; border-radius: 16px; max-width: 80%; line-height: 1.35; }
  .walter { background: #2b2b2e; align-self: flex-start; }
  .merchant { background: #0a84ff; color: white; align-self: flex-end; }
  .sys { color: #999; font-size: 12px; text-align: center; margin: 4px 0; }
  form { display: flex; gap: 8px; }
  input { flex: 1; padding: 10px; border-radius: 8px; border: 1px solid #444;
          background: #1c1c1e; color: #eee; }
  button { padding: 10px 16px; border-radius: 8px; border: 0;
           background: #0a84ff; color: white; }
  button:disabled { opacity: .5; }
  a { color: #6ab7ff; font-size: 12px; }
</style></head><body>
<h3>Walter &mdash; local test line <small id="status"></small></h3>
<select id="who"></select>
<div class="sys">you are texting as <span id="asname"></span>. replies take a
minute while the local model thinks.</div>
<div id="thread"></div>
<form id="f"><input id="msg" autocomplete="off" placeholder="text Walter back...">
<button id="send">Send</button></form>
<p><a href="#" id="reset">start this conversation over</a></p>
<script>
const thread = document.getElementById('thread');
const who = document.getElementById('who');
let current = '';
function render(s) {
  current = s.phone;
  document.getElementById('status').textContent =
    s.status === 'active' ? '' : '(' + s.status + ')';
  document.getElementById('asname').textContent = s.first;
  who.innerHTML = '';
  for (const c of s.contacts) {
    const o = document.createElement('option');
    o.value = c.phone;
    o.textContent = c.first + (c.company ? ' (' + c.company + ')' : '');
    o.selected = c.phone === s.phone;
    who.appendChild(o);
  }
  thread.innerHTML = '';
  for (const m of s.messages) {
    const d = document.createElement('div');
    d.className = 'b ' + (m.role === 'walter' ? 'walter' : 'merchant');
    d.textContent = m.text;
    thread.appendChild(d);
  }
  window.scrollTo(0, document.body.scrollHeight);
}
async function refresh() {
  const q = current ? '?c=' + encodeURIComponent(current) : '';
  render(await (await fetch('/state' + q)).json());
}
who.onchange = () => { current = who.value; refresh(); };
document.getElementById('f').onsubmit = async (e) => {
  e.preventDefault();
  const box = document.getElementById('msg'), btn = document.getElementById('send');
  const text = box.value.trim();
  if (!text) return;
  box.value = ''; btn.disabled = true; btn.textContent = '...';
  const d = document.createElement('div');
  d.className = 'b merchant'; d.textContent = text; thread.appendChild(d);
  const note = document.createElement('div');
  note.className = 'sys'; note.textContent = 'Walter is typing...';
  thread.appendChild(note);
  window.scrollTo(0, document.body.scrollHeight);
  try {
    const r = await (await fetch('/send', {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: text, contact: current})})).json();
    render(r.state);
    if (r.action !== 'reply') {
      const n = document.createElement('div');
      n.className = 'sys';
      n.textContent = 'no auto reply: ' + r.action +
        (r.notify_rep ? ' (rep notified)' : '');
      thread.appendChild(n);
    }
  } catch (err) { note.textContent = 'error: ' + err; }
  btn.disabled = false; btn.textContent = 'Send';
};
document.getElementById('reset').onclick = async (e) => {
  e.preventDefault();
  await fetch('/reset', {method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({contact: current})});
  refresh();
};
refresh();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _contact_key(self, requested: str) -> str:
        return requested if requested in CONTACTS else _default_contact()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/state":
            requested = urllib.parse.parse_qs(parsed.query).get("c", [""])[0]
            return self._json(state(self._contact_key(requested)))
        page = PAGE.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(length)) if length else {}
        key = self._contact_key(data.get("contact", ""))
        contact = CONTACTS[key]
        if self.path == "/reset":
            convo = store.get(key)
            convo.update(status="active", messages=[], identity_streak=0,
                         merchant_interested=False)
            store.save(convo)
            seed()
            return self._json({"ok": True})
        if self.path == "/send":
            text = data.get("message", "").strip()
            if not text:
                return self._json({"error": "empty"}, 400)
            result = worker.handle_inbound(
                store,
                {"phone": key, "message": text,
                 "merchantFirst": contact["first_name"],
                 "company": contact.get("company", "")},
            )
            return self._json({**result, "state": state(key)})
        self._json({"error": "not found"}, 404)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    seed()
    print(f"Walter local test chat: http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
