# Telegram Integration Setup

## 1. Create a Bot
1. Open Telegram and start a chat with **@BotFather**.
2. Send `/newbot` and follow prompts (name + username ending in `bot`).
3. BotFather returns a token like `123456789:ABCDEFGH...` — this is `TELEGRAM_BOT_TOKEN`.

## 2. Get Your Chat ID
Option A (direct chat):
1. Start a conversation with your new bot (press Start so it can message you).
2. Visit: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser after sending any message to the bot.
3. Look for `"chat":{"id":123456789,...}` — that's your `TELEGRAM_CHAT_ID`.

Option B (group):
1. Add the bot to the group.
2. Send a message in the group.
3. Use `getUpdates` as above and take the `chat.id` (may be negative for supergroups).

## 3. Set Environment Variables (Windows PowerShell)
Temporary (current session only):
```powershell
$env:TELEGRAM_BOT_TOKEN = "123456789:ABCDEF..."
$env:TELEGRAM_CHAT_ID = "123456789"
```
Permanent (new shells):
```powershell
setx TELEGRAM_BOT_TOKEN "123456789:ABCDEF..."
setx TELEGRAM_CHAT_ID "123456789"
```
(You must open a NEW PowerShell window after `setx` for them to appear.)

## 4. Run the Tennis Arbitrage Script
```powershell
python arbitrage_tennis_full.py
```
After completion it will attempt sending a summary to Telegram. If env vars are missing, it prints a skip message.

## 5. Message Size
Large reports are chunked (< 3900 chars each) to satisfy Telegram's 4096 char limit.

## 6. Troubleshooting
- 401 / unauthorized: Token incorrect — regenerate via BotFather `/token`.
- No messages: Ensure you pressed Start in the chat with your bot.
- Chat ID empty: You didn't send a message before calling `getUpdates`.
- Corporate network blocks calls: Try a different network or VPN.

## 7. Optional: .env File Support
If you prefer a `.env` file, install `python-dotenv` and add at script start:
```python
from dotenv import load_dotenv
load_dotenv()
```
Then create `.env` from `.env.example`.

## 8. Rate Limits
Script sends just 1–3 messages; well below Telegram limits.

Happy surebet hunting!
