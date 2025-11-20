"""Run multiple analytics scripts (tennis + basketball) concurrently and send a single aggregated Telegram message.

Usage (PowerShell):
  python run_multi.py --basketball-args "--three-days --all-pages --pages 10 --min-profit 0 --verbose"

If enhanced_basketball_analyzer.py is missing, it will be skipped gracefully.
Environment: expects TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID set or present in .env.
"""
import os
import locale
import shlex
import subprocess
import threading
import time
import sys
from pathlib import Path
from typing import Optional, Dict

try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

from telegram_notifier import send_long_message  # reuse chunked sending

ROOT = Path(__file__).resolve().parent
# Optional: write detailed logs for debugging
LOG_DIR = ROOT / 'logs'
LOG_DIR.mkdir(exist_ok=True)

TENNIS_SCRIPT = ROOT / 'arbitrage_tennis_full.py'
BASKETBALL_SCRIPT = ROOT / 'enhanced_basketball_analyzer.py'  # may not exist
FOOTBALL_SCRIPT = ROOT / 'arbitrage_football.py'

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def run_script(path: Path, extra_args: str = "") -> Dict[str, str]:
    start = time.time()
    result = {
        'name': path.name,
        'status': 'skipped',
        'stdout': '',
        'stderr': '',
        'duration_s': '0'
    }
    if not path.exists():
        result['stderr'] = f"File {path.name} not found."
        return result
    cmd = [sys.executable, str(path)]
    if extra_args.strip():
        # naive parse via shlex (works for simple args)
        cmd.extend(shlex.split(extra_args))
    try:
        # Force UTF-8 in child processes to avoid Windows cp1252 emoji crashes
        child_env = os.environ.copy()
        child_env['PYTHONIOENCODING'] = 'utf-8'
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=child_env,
        )
        out, err = proc.communicate()
        result['stdout'] = out
        result['stderr'] = err
        result['status'] = 'ok' if proc.returncode == 0 else f"exit_{proc.returncode}"
        # Persist logs for full visibility
        stamp = time.strftime('%Y%m%d_%H%M%S')
        with open(LOG_DIR / f"{path.stem}_{stamp}.out.log", 'w', encoding='utf-8') as f:
            f.write(out)
        if err:
            with open(LOG_DIR / f"{path.stem}_{stamp}.err.log", 'w', encoding='utf-8') as f:
                f.write(err)
    except Exception as e:
        result['stderr'] = f"Execution error: {e}"
        result['status'] = 'error'
    finally:
        result['duration_s'] = f"{time.time()-start:.1f}"
    return result

# ---------------------------------------------------------------------------
# Concurrent runner
# ---------------------------------------------------------------------------

def run_concurrently(basketball_args: str = "", football_args: str = ""):
    results = {}
    threads = []

    def target(key: str, path: Path, args: str):
        results[key] = run_script(path, args)

    threads.append(threading.Thread(target=target, args=('tennis', TENNIS_SCRIPT, '')))
    threads.append(threading.Thread(target=target, args=('basketball', BASKETBALL_SCRIPT, basketball_args)))
    threads.append(threading.Thread(target=target, args=('football', FOOTBALL_SCRIPT, football_args)))

    for t in threads: t.start()
    for t in threads: t.join()
    return results

# ---------------------------------------------------------------------------
# Aggregation / Telegram
# ---------------------------------------------------------------------------

def format_aggregate(results: Dict[str, Dict[str, str]]) -> str:
    lines: list[str] = []
    lines.append("🏁 Multi-run summary")
    for key, res in results.items():
        lines.append(f"▶ {res['name']} | status={res['status']} | duration={res['duration_s']}s")
        # Extract surebet counts heuristically from stdout
        surebet_count = None
        for ln in (res['stdout'] or '').splitlines():
            if 'Found' in ln and 'surebets' in ln.lower():
                try:
                    parts = ln.split()
                    for p in parts:
                        if p.isdigit():
                            surebet_count = p
                            break
                except Exception:
                    pass
        if surebet_count is not None:
            lines.append(f"   • Detected surebets: {surebet_count}")
        if res['stderr']:
            first_line = res['stderr'].splitlines()[0] if res['stderr'].splitlines() else ''
            lines.append(f"   ⚠ stderr(first): {first_line[:300]}")
            if len(res['stderr']) > 400:
                lines.append(f"   ⚠ stderr(trunc tail): {res['stderr'][-300:]}")
        clip = '\n'.join((res['stdout'] or '').splitlines()[-15:])  # last 15 lines
        if clip.strip():
            lines.append("   --- tail stdout (last 15 lines) ---")
            for ln in clip.splitlines():
                lines.append(f"   {ln}")
    return '\n'.join(lines)

# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def _force_utf8():
    # On some Windows shells the default encoding is cp1252; force UTF-8 for emoji output.
    if os.name == 'nt':
        try:
            import sys
            # Reconfigure stdout/stderr to utf-8 if possible (Python 3.7+)
            if hasattr(sys.stdout, 'reconfigure'):
                sys.stdout.reconfigure(encoding='utf-8')
                sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass

def main():
    _force_utf8()
    import argparse
    ap = argparse.ArgumentParser(description='Run multiple arbitrage scripts concurrently and send Telegram summary.')
    ap.add_argument('--basketball-args', default='--three-days --all-pages --pages 10 --min-profit 0 --verbose', help='Args passed to enhanced_basketball_analyzer.py (if present).')
    ap.add_argument('--football-args', default='--notify-min-roi 2.5 --notify-max-roi 20', help='Args passed to arbitrage_football.py (if present).')
    ap.add_argument('--no-telegram', action='store_true', help='Do not send Telegram message, just print.')
    ap.add_argument('--sequential', action='store_true', help='Run scripts sequentially (avoid parallel WebDriver conflicts).')
    ap.add_argument('--skip-tennis', action='store_true', help='Skip running tennis script.')
    ap.add_argument('--skip-basketball', action='store_true', help='Skip running basketball script.')
    ap.add_argument('--skip-football', action='store_true', help='Skip running football script.')
    ap.add_argument('--no-aggregate', action='store_true', help='Suppress multi-run aggregated summary and its Telegram message.')
    args = ap.parse_args()

    print('🚀 Launching concurrent runs...')
    results = {}
    if args.sequential:
        print('🔁 Sequential mode enabled.')
        if not args.skip_tennis:
            results['tennis'] = run_script(TENNIS_SCRIPT, '--notify-min-roi 2.5 --notify-max-roi 20')
        else:
            results['tennis'] = {'name': TENNIS_SCRIPT.name, 'status':'skipped','stdout':'','stderr':'(skipped by flag)','duration_s':'0'}
        if not args.skip_basketball:
            results['basketball'] = run_script(BASKETBALL_SCRIPT, args.basketball_args + ' --notify-min-roi 2.5 --notify-max-roi 20')
        else:
            results['basketball'] = {'name': BASKETBALL_SCRIPT.name, 'status':'skipped','stdout':'','stderr':'(skipped by flag)','duration_s':'0'}
        if not args.skip_football:
            results['football'] = run_script(FOOTBALL_SCRIPT, args.football_args)
        else:
            results['football'] = {'name': FOOTBALL_SCRIPT.name, 'status':'skipped','stdout':'','stderr':'(skipped by flag)','duration_s':'0'}
    else:
        if args.skip_tennis and args.skip_basketball and args.skip_football:
            print('⚠️ Both scripts skipped; nothing to run.')
        else:
            # Build threads conditionally
            if args.skip_tennis and args.skip_basketball and not args.skip_football:
                # Only football
                results['tennis'] = {'name': TENNIS_SCRIPT.name, 'status':'skipped','stdout':'','stderr':'(skipped by flag)','duration_s':'0'}
                results['basketball'] = {'name': BASKETBALL_SCRIPT.name, 'status':'skipped','stdout':'','stderr':'(skipped by flag)','duration_s':'0'}
                results['football'] = run_script(FOOTBALL_SCRIPT, args.football_args)
            else:
                # Use concurrent runner with provided args (skips handled inside runner by path existence)
                # We still need to build proper args list excluding skipped scripts; easiest: run concurrently and then overwrite skipped entries.
                results = run_concurrently(args.basketball_args + ' --notify-min-roi 2.5 --notify-max-roi 20', args.football_args)
                if args.skip_tennis:
                    results['tennis'] = {'name': TENNIS_SCRIPT.name, 'status':'skipped','stdout':'','stderr':'(skipped by flag)','duration_s':'0'}
                if args.skip_basketball:
                    results['basketball'] = {'name': BASKETBALL_SCRIPT.name, 'status':'skipped','stdout':'','stderr':'(skipped by flag)','duration_s':'0'}
                if args.skip_football:
                    results['football'] = {'name': FOOTBALL_SCRIPT.name, 'status':'skipped','stdout':'','stderr':'(skipped by flag)','duration_s':'0'}
    if args.no_aggregate:
        print('ℹ Multi-run aggregate summary suppressed (--no-aggregate).')
    else:
        aggregate = format_aggregate(results)
        print('\n' + aggregate)
        if not args.no_telegram:
            # Use long message handler (will chunk automatically)
            try:
                send_long_message(aggregate)
                print('📨 Telegram multi summary attempted.')
            except Exception as e:
                print(f'⚠️ Telegram send failed: {e}')
        else:
            print('ℹ Telegram sending disabled by flag.')
    # Provide hint if selenium import failures likely
    need_selenium_hint = any('selenium' in (r.get('stderr') or '').lower() for r in results.values())
    if need_selenium_hint:
        print('\n💡 It looks like Selenium may not be installed. Install dependencies:')
        print('   pip install selenium webdriver-manager beautifulsoup4 requests python-dotenv')
        print('   (Then re-run with: python run_multi.py --sequential to test)')

if __name__ == '__main__':
    main()
