"""Live Surebet Tracker (Under 2.5 / Over 2.5) across multiple bookmakers.

Currently supports Mozzart & MaxBet via heuristic HTML parsing.
Refine selectors or add Selenium if accuracy needs improvement.
"""
from __future__ import annotations
import argparse, json, time, math
from typing import Dict, List, Any
from bookies.mozzart import MozzartScraper
from bookies.maxbet import MaxBetScraper
from bookies.base import match_key, reverse_key, normalize_team

def implied_prob_pair(u: float, o: float) -> float:
    return (1/u) + (1/o)

def surebet_profit(u: float, o: float) -> float | None:
    if u <= 0 or o <= 0: return None
    inv = implied_prob_pair(u,o)
    if inv < 1:
        return round((1 - inv) * 100, 2)
    return None

def compute_stakes(u: float, o: float, total: float = 100.0):
    inv_sum = (1/u) + (1/o)
    su = (total * (1/u)) / inv_sum
    so = (total * (1/o)) / inv_sum
    ret = su * u  # same for so * o
    profit = ret - total
    return round(su,2), round(so,2), round(profit,2)

def gather(min_profit: float = 0.0, include_all: bool = False, selenium: bool = False, wait: int = 6, scroll: int = 0, no_headless: bool = False):
    # configure scrapers
    scrapers = [MozzartScraper(), MaxBetScraper()]
    if selenium:
        for s in scrapers:
            s.use_selenium = True
            s.selenium_wait = wait
            s.selenium_scroll = scroll
            s.selenium_headless = not no_headless
    bookie_data = {}
    meta = {}
    for s in scrapers:
        start = time.time()
        matches = s.get_matches()
        dur = time.time() - start
        meta[s.name] = {
            'count': len(matches),
            'elapsed_sec': round(dur,2)
        }
        bookie_data[s.name] = matches
    # Merge by normalized key or reversed key
    index: Dict[str, Dict[str, Dict[str,float]]] = {}
    team_names: Dict[str, str] = {}
    for bname, matches in bookie_data.items():
        for m in matches:
            key = match_key(m.home, m.away)
            rkey = reverse_key(key)
            store_key = key
            if key not in index and rkey in index:
                store_key = rkey
            entry = index.setdefault(store_key, {})
            team_names.setdefault(store_key, f"{m.home} vs {m.away}")
            entry[bname] = {
                'under': m.markets.under,
                'over': m.markets.over
            }
    surebets = []
    comparisons: List[Dict[str, Any]] = []
    for k, bookies in index.items():
        # collect best under & over across bookies
        best_under = None; best_over = None; under_src=None; over_src=None
        for bname, mo in bookies.items():
            u = mo.get('under'); o = mo.get('over')
            if u and (best_under is None or u > best_under):
                best_under, under_src = u, bname
            if o and (best_over is None or o > best_over):
                best_over, over_src = o, bname
        # Build full comparison row
        if include_all and best_under and best_over:
            row = {
                'match': team_names[k],
                'books': bookies,
                'best_under': {'odd': best_under, 'book': under_src},
                'best_over': {'odd': best_over, 'book': over_src}
            }
            profit_all = surebet_profit(best_under, best_over)
            if profit_all is not None:
                row['potential_profit_percent'] = profit_all
            comparisons.append(row)
        if best_under and best_over:
            profit = surebet_profit(best_under, best_over)
            if profit is not None and profit >= min_profit:
                su, so, abs_profit = compute_stakes(best_under, best_over)
                surebets.append({
                    'match': team_names[k],
                    'under': {'odd': best_under, 'book': under_src},
                    'over': {'odd': best_over, 'book': over_src},
                    'profit_percent': profit,
                    'stakes': {'under': su, 'over': so, 'abs_profit': abs_profit}
                })
    out = {
        'timestamp': time.time(),
        'surebets': sorted(surebets, key=lambda x: -x['profit_percent']),
        'raw_counts': {k: len(v) for k,v in bookie_data.items()},
        'meta': meta,
        'bookmaker_raw': {
            b: [
                {
                    'home': m.home,
                    'away': m.away,
                    'under': m.markets.under,
                    'over': m.markets.over
                } for m in ms
            ] for b, ms in bookie_data.items()
        }
    }
    if include_all:
        out['comparisons'] = comparisons
    return out

def print_table(data, show_all: bool = False, show_solo: bool = False, show_raw: bool = False):
    sbs = data['surebets']
    had_output = False
    if sbs:
        header = f"{'Match':50}  {'U2.5':>6} {'Bk':>7}  {'O2.5':>6} {'Bk':>7}  {'Profit%':>7}  {'StakeU':>7} {'StakeO':>7}"
        print(header)
        print('-'*len(header))
        for sb in sbs[:60]:
            m = (sb['match'][:47]+'...') if len(sb['match'])>50 else sb['match']
            print(f"{m:50}  {sb['under']['odd']:>6.2f} {sb['under']['book'][:7]:>7}  {sb['over']['odd']:>6.2f} {sb['over']['book'][:7]:>7}  {sb['profit_percent']:>7.2f}  {sb['stakes']['under']:>7.2f} {sb['stakes']['over']:>7.2f}")
        had_output = True
    elif not (show_all or show_solo):
        print('No surebets found.')
    # Show comparisons (all matched games) if requested
    if show_all and 'comparisons' in data:
        if had_output:
            print('\nAll matched games (best odds per side):')
        else:
            print('Matched games (no surebets, best odds per side):')
        print(f"{'Match':50}  {'BestU':>6} {'Bk':>6}  {'BestO':>6} {'Bk':>6}  {'Pot%':>6}")
        print('-'*92)
        for row in data['comparisons'][:120]:
            pot = row.get('potential_profit_percent')
            pot_s = f"{pot:>6.2f}" if pot is not None else ' ' * 6
            m = (row['match'][:47]+'...') if len(row['match'])>50 else row['match']
            print(f"{m:50}  {row['best_under']['odd']:>6.2f} {row['best_under']['book'][:6]:>6}  {row['best_over']['odd']:>6.2f} {row['best_over']['book'][:6]:>6}  {pot_s}")
        had_output = True
    # Show solo bookmaker odds where only one side present (if requested)
    if show_solo and 'comparisons' in data:
        print('\nSingle-source matches (one bookmaker only):')
        print(f"{'Match':50}  {'Under':>6} {'Bk':>6}  {'Over':>6} {'Bk':>6}")
        print('-'*86)
        for row in data['comparisons']:
            if len(row['books']) == 1:
                bname, vals = next(iter(row['books'].items()))
                m = (row['match'][:47]+'...') if len(row['match'])>50 else row['match']
                u = vals.get('under'); o = vals.get('over')
                u_s = f"{u:.2f}" if u else '  -  '
                o_s = f"{o:.2f}" if o else '  -  '
                print(f"{m:50}  {u_s:>6} {bname[:6]:>6}  {o_s:>6} {bname[:6]:>6}")
    if show_raw:
        print('\nRaw bookmaker listings:')
        for bname, rows in data.get('bookmaker_raw', {}).items():
            meta = data.get('meta', {}).get(bname, {})
            print(f"\n[{bname}] {len(rows)} matches  elapsed={meta.get('elapsed_sec','?')}s")
            for r in rows[:100]:
                u = f"{r['under']:.2f}" if r['under'] else '-' ; o = f"{r['over']:.2f}" if r['over'] else '-'
                print(f"  {r['home']} vs {r['away']}  U:{u} O:{o}")

def main():
    ap = argparse.ArgumentParser(description='Live O/U (2.5) Surebet Tracker (Mozzart + MaxBet)')
    ap.add_argument('--min-profit', type=float, default=0.0)
    ap.add_argument('--json-out', type=str, default='surebets_ou.json')
    ap.add_argument('--loop', type=int, default=0, help='Seconds interval; 0 = single run')
    ap.add_argument('--show-all', action='store_true', help='Show all matched games with best odds even if no surebet')
    ap.add_argument('--show-solo', action='store_true', help='Show games found only at one bookmaker')
    ap.add_argument('--show-raw', action='store_true', help='Show raw bookmaker parsed matches')
    ap.add_argument('--selenium', action='store_true', help='Use Selenium (rendered HTML) for dynamic sites')
    ap.add_argument('--wait', type=int, default=6, help='Selenium wait seconds before parsing')
    ap.add_argument('--scroll', type=int, default=0, help='Scroll times (lazy load) in Selenium mode')
    ap.add_argument('--no-headless', action='store_true', help='Show browser window (Selenium)')
    args = ap.parse_args()

    def run_once():
        data = gather(
            min_profit=args.min_profit,
            include_all=(args.show_all or args.show_solo),
            selenium=args.selenium,
            wait=args.wait,
            scroll=args.scroll,
            no_headless=args.no_headless
        )
        print_table(data, show_all=args.show_all, show_solo=args.show_solo, show_raw=args.show_raw)
        with open(args.json_out,'w',encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return data

    if args.loop > 0:
        while True:
            print(time.strftime('%Y-%m-%d %H:%M:%S'), 'RUN')
            run_once()
            time.sleep(args.loop)
    else:
        run_once()

if __name__ == '__main__':
    main()
