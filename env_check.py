import os, requests, sys
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent / '.env'

# Load .env manually if variables not already present
if not os.getenv('TELEGRAM_BOT_TOKEN') or not os.getenv('TELEGRAM_CHAT_ID'):
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            if not line.strip() or line.strip().startswith('#'):
                continue
            if '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

print('TOKEN present:', bool(TOKEN))
print('CHAT_ID:', CHAT_ID or 'MISSING')

if not TOKEN or not CHAT_ID:
    print('Missing TOKEN or CHAT_ID. Set them and re-run.')
    sys.exit(1)

# Basic getMe test
try:
    r = requests.get(f'https://api.telegram.org/bot{TOKEN}/getMe', timeout=10)
    print('getMe status:', r.status_code)
    if r.status_code == 200:
        print('Bot info:', r.json())
    else:
        print('Response snippet:', r.text[:300])
except Exception as e:
    print('Error calling getMe:', e)

# Dry-run send (won't actually send if you comment out) - safe small message
msg = 'Telegram env check OK.'
try:
    send_url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
    resp = requests.post(send_url, json={'chat_id': CHAT_ID, 'text': msg, 'disable_web_page_preview': True}, timeout=10)
    print('sendMessage status:', resp.status_code)
    if resp.status_code != 200:
        print('sendMessage error snippet:', resp.text[:300])
except Exception as e:
    print('Error sending test message:', e)
