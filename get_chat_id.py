import os, sys, requests, json

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or (len(sys.argv) > 1 and sys.argv[1])
if not TOKEN:
    print("Usage: set TELEGRAM_BOT_TOKEN env var or pass as arg: python get_chat_id.py <TOKEN>")
    sys.exit(1)

url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
try:
    r = requests.get(url, timeout=15)
    if r.status_code != 200:
        print(f"HTTP {r.status_code}: {r.text[:400]}")
        sys.exit(2)
    data = r.json()
except Exception as e:
    print(f"Error contacting Telegram: {e}")
    sys.exit(3)

if not data.get("ok"):
    print("Telegram response not ok:", json.dumps(data, indent=2))
    sys.exit(4)

updates = data.get("result", [])
if not updates:
    print("No updates yet. Send a message to your bot in Telegram first, then re-run.")
    sys.exit(0)

seen = {}
for upd in updates:
    chat = upd.get("message", {}).get("chat") or upd.get("edited_message", {}).get("chat")
    if not chat: continue
    cid = chat.get("id")
    if cid in seen: continue
    seen[cid] = chat

print("Discovered chat IDs:")
for cid, chat in seen.items():
    ctype = chat.get("type")
    title = chat.get("title") or f"{chat.get('first_name','')} {chat.get('last_name','')}".strip()
    username = chat.get("username")
    print(f"  id={cid} type={ctype} title={title!r} username={username}")

print("\nSet TELEGRAM_CHAT_ID to the id you want. Example (PowerShell):")
print("  setx TELEGRAM_CHAT_ID \"<ID HERE>\"")
