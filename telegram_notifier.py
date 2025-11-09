import os
import time
import requests
from typing import List, Dict, Any, Optional

# Auto-load .env if python-dotenv is installed (optional convenience)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

TELEGRAM_API_BASE = "https://api.telegram.org"
MAX_MSG_LEN = 3900  # keep under hard 4096 limit with a safety buffer

class TelegramConfigError(Exception):
    pass

def _get_bot_config() -> (Optional[str], Optional[str]):
    return os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")

def send_raw_message(text: str, parse_mode: Optional[str] = None) -> bool:
    token, chat_id = _get_bot_config()
    if not token or not chat_id:
        print("[Telegram] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID environment variables. Skipping send.")
        return False
    url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code != 200:
            print(f"[Telegram] sendMessage failed {resp.status_code}: {resp.text[:300]}")
            return False
        return True
    except Exception as e:
        print(f"[Telegram] Exception sending message: {e}")
        return False

def _chunk(text: str) -> List[str]:
    if len(text) <= MAX_MSG_LEN:
        return [text]
    chunks = []
    current = []
    current_len = 0
    for line in text.splitlines():
        line_len = len(line) + 1
        if current_len + line_len > MAX_MSG_LEN:
            chunks.append("\n".join(current))
            current = [line]
            current_len = line_len
        else:
            current.append(line)
            current_len += line_len
    if current:
        chunks.append("\n".join(current))
    return chunks

def send_long_message(text: str) -> None:
    for part in _chunk(text):
        ok = send_raw_message(part)
        time.sleep(0.6)  # mild pacing
        if not ok:
            break

def format_surebets_summary(
    surebets: List[Dict[str, Any]],
    total_matches: int,
    include_header: bool = True,
) -> str:
    """Format the surebets list for Telegram.

    Args:
        surebets: List of surebet dicts each containing keys: match, type, roi_pct, margin_pct, odds_str.
        total_matches: Count of unique matches scraped.
        include_header: When False, suppress the decorative/report header lines the user no longer wants.

    Returns:
        A newline separated string ready for Telegram sending.
    """
    header: List[str] = []
    if include_header:
        header = [
            "🏓 Tennis Surebets Report",
            f"Total unique matches scraped: {total_matches}",
            f"Surebets detected: {len(surebets)}",
            "",
        ]
    if not surebets:
        # When header suppressed, keep a concise message.
        if include_header:
            header.append("No surebets (single bookmaker scenario) — waiting for cross-book odds.")
            return "\n".join(header)
        return "No surebets available yet."  # short variant

    # Sort by ROI desc and take top 12 for brevity
    top = sorted(surebets, key=lambda x: x['roi_pct'], reverse=True)[:12]
    lines = header
    if include_header:
        lines.append("Top opportunities (ROI desc):")
    for sb in top:
        m = sb['match']
        tm = m.get('time') or '?'  # time
        vs = f"{m['player1']} vs {m['player2']}"
        t = sb['type']
        roi = sb['roi_pct']
        margin = sb['margin_pct']
        odds = sb['odds_str']
        # Simplified line (no stakes, no aggregate stats section)
        lines.append(f"{tm} | {vs}\n  {t}: ROI {roi}% | Margin {margin}% | {odds}")
    return "\n".join(lines)

def send_surebets_summary(surebets: List[Dict[str, Any]], total_matches: int, include_header: bool = False) -> None:
    """Send the surebets summary to Telegram.

    Default behavior now suppresses the header to match user preference.
    Set include_header=True if you want the full report style again.
    """
    text = format_surebets_summary(surebets, total_matches, include_header=include_header)
    send_long_message(text)

if __name__ == "__main__":
    # Tiny manual test with dummy data
    demo = [{
        'match': {'time': '12:00', 'player1': 'Player A', 'player2': 'Player B'},
        'type': 'Match Winner',
        'margin_pct': 2.5,
        'roi_pct': 2.56,
        'stakes': {'Home': 49.5, 'Away': 50.5},
        'odds_str': 'Home=2.05, Away=1.95'
    }]
    print(format_surebets_summary(demo, 1, include_header=False))
