import re
import json
import argparse
from pathlib import Path
from typing import Dict, List

# Simple NFL TD yes/no arbitrage detector between two bookmakers' flat text dumps.
# Expected pattern (book A or B file):
# <PlayerName>
# <YesOdd>
# <NoOdd>
# ... repeated. (From Mozzart sample: appears as Yes (da) first, then No (ne))
# Some lines may contain control strings, URLs, or plus symbols (+2) that should be ignored.

VALID_ODDS_RANGE = (1.05, 50.0)
# Player line: capitalized words (1-3 parts) possibly with initials, diacritics
PLAYER_LINE_RE = re.compile(r"^[A-ZČĆŽŠĐ][A-Za-zČĆŽŠĐčćžšđ0-9\.'\- ()]{1,48}$")
FLOAT_RE = re.compile(r"^\d+(?:[\.,]\d+)?$")

# Tokens that should cause skipping while scanning odds after a player name
SKIP_TOKENS = {
    'manje', 'više', 'vise', 'da', 'ne', 'yes', 'no', '2-', '1-', '0-', 'ftot1', 'ftot2'
}
CONTROL_PREFIXES = ('http', '<', '+')

# Map localized markers if present
YES_TOKENS = {"da","yes"}
NO_TOKENS = {"ne","no"}

def normalize_odd(token: str, adjust_leading_one: bool=True):
    token = token.strip()
    token = token.replace(',', '.')
    if FLOAT_RE.match(token):
        try:
            val = float(token)
            # Heuristic: some MaxBet dumps prepend a stray '1' (e.g. 12.20 meaning 2.20, 11.60 meaning 1.60)
            # Apply only when: 10 <= val < 20 and (val-10) still within valid range.
            if adjust_leading_one and 10 <= val < 20:
                alt = round(val - 10, 2)
                if VALID_ODDS_RANGE[0] <= alt <= VALID_ODDS_RANGE[1]:
                    val = alt
            if VALID_ODDS_RANGE[0] <= val <= VALID_ODDS_RANGE[1]:
                return val
        except ValueError:
            return None
    return None

def parse_book_file(path: Path, book_name: str, verbose: bool=False, adjust_leading_one: bool=True) -> Dict[str, Dict[str, Dict[str, float]]]:
    """Parse a bookmaker text dump and extract touchdown scorer YES/NO odds.

    Heuristics:
      - Player line matches PLAYER_LINE_RE and contains a space (at least name + surname)
      - Scan forward up to 12 subsequent lines collecting the first two numeric odds
        skipping control / label tokens (SKIP_TOKENS) and structural markers.
      - Accept odds even if separated by other non-numeric lines.
    """
    players: Dict[str, Dict[str, Dict[str, float]]] = {}
    if not path.exists():
        print(f"⚠️ Missing file: {path}")
        return players
    with path.open('r', encoding='utf-8', errors='ignore') as f:
        raw_lines = f.readlines()
    # Pre-trim and filter empty lines
    lines: List[str] = []
    for ln in raw_lines:
        ln = ln.strip()
        if not ln:
            continue
        # unify weird spacing / trailing dots
        ln = ln.replace('\u00a0',' ').strip('. ')
        lines.append(ln)

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if PLAYER_LINE_RE.match(line) and ' ' in line and 1 <= len(line.split()) <= 4:
            player = line
            yes_odd = None
            no_odd = None
            j = i + 1
            lookahead_limit = j + 12  # broaden search window
            while j < n and j < lookahead_limit and (yes_odd is None or no_odd is None):
                tok = lines[j]
                low = tok.lower()
                # Skip obvious control/separator lines
                if low in SKIP_TOKENS or any(tok.startswith(pref) for pref in CONTROL_PREFIXES):
                    j += 1
                    continue
                # Skip tokens that are pure punctuation or end with '-' (labels like "2-" or "Manje-")
                if tok.endswith('-') or tok in {'|','/','.'}:
                    j += 1
                    continue
                val = normalize_odd(tok, adjust_leading_one=adjust_leading_one)
                if val is not None:
                    if yes_odd is None:
                        yes_odd = val
                    elif no_odd is None:
                        no_odd = val
                    j += 1
                    continue
                j += 1
            # Allow storing single YES odd (book without NO market). We'll fill only 'yes'.
            if yes_odd:
                entry = {'yes': yes_odd}
                if no_odd:
                    entry['no'] = no_odd
                players[player] = {book_name: entry}
                if verbose:
                    if 'no' in entry:
                        print(f"[{book_name}] {player}: YES {yes_odd} / NO {no_odd}")
                    else:
                        print(f"[{book_name}] {player}: YES {yes_odd} / NO -")
                i = j
                continue
        i += 1
    return players

def merge_books(bookA: dict, bookB: dict):
    merged = {}
    # Start with bookA
    for player, data in bookA.items():
        merged[player] = data
    # Merge bookB
    for player, data in bookB.items():
        if player in merged:
            merged[player].update(data)
        else:
            merged[player] = data
    return merged

def detect_td_surebets(merged):
    results = []
    for player, by_book in merged.items():
        # Need at least two books with yes/no odds
        yes_odds = []
        no_odds = []
        for book, odds in by_book.items():
            y = odds.get('yes')
            n = odds.get('no')
            if y and VALID_ODDS_RANGE[0] <= y <= VALID_ODDS_RANGE[1]:
                yes_odds.append((y, book))
            if n and VALID_ODDS_RANGE[0] <= n <= VALID_ODDS_RANGE[1]:
                no_odds.append((n, book))
        if len(yes_odds) == 0 or len(no_odds) == 0:
            continue
        # We want highest yes and highest no from possibly different books
        best_yes = max(yes_odds, key=lambda x: x[0])
        best_no = max(no_odds, key=lambda x: x[0])
        # Ensure they come from different bookmakers; if same, arbitrage might still exist but less meaningful (single-book overround check)
        if best_yes[1] == best_no[1]:
            continue
        inv_sum = (1 / best_yes[0]) + (1 / best_no[0])
        if inv_sum < 1:
            margin_pct = (1 - inv_sum) * 100
            roi_pct = ((1 / inv_sum) - 1) * 100
            total = 100.0
            stake_yes = (1 / best_yes[0]) / inv_sum * total
            stake_no = (1 / best_no[0]) / inv_sum * total
            results.append({
                'player': player,
                'yes': {'odd': best_yes[0], 'book': best_yes[1]},
                'no': {'odd': best_no[0], 'book': best_no[1]},
                'margin_pct': round(margin_pct, 2),
                'roi_pct': round(roi_pct, 2),
                'stakes': {'yes': round(stake_yes, 2), 'no': round(stake_no, 2)},
                'inv_sum': round(inv_sum, 5)
            })
    # Sort by ROI descending
    return sorted(results, key=lambda x: x['roi_pct'], reverse=True)

def main():
    parser = argparse.ArgumentParser(description='NFL Touchdown (Any Time) TD Surebet Detector')
    parser.add_argument('--file-a', type=str, default=r"c:/Users/Jelena/Desktop/maxbet_nfl.txt", help='Path to bookmaker A dump (default MaxBet path)')
    parser.add_argument('--file-b', type=str, default=r"c:/Users/Jelena/Desktop/mozzart_nfl.txt", help='Path to bookmaker B dump (default Mozzart path)')
    parser.add_argument('--book-a', type=str, default='MaxBet', help='Bookmaker name for file A')
    parser.add_argument('--book-b', type=str, default='Mozzart', help='Bookmaker name for file B')
    parser.add_argument('--min-roi', type=float, default=0.0, help='Minimum ROI% to include in output')
    parser.add_argument('--no-adjust-leading-one', action='store_true', help='Disable heuristic that converts 12.20 -> 2.20 etc.')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()

    path_a = Path(args.file_a)
    path_b = Path(args.file_b)
    if args.verbose:
        print(f"📄 Parsing A: {path_a} ({args.book_a})")
    bookA_players = parse_book_file(path_a, args.book_a, verbose=args.verbose, adjust_leading_one=not args.no_adjust_leading_one)
    if args.verbose:
        print(f"📄 Parsing B: {path_b} ({args.book_b})")
    bookB_players = parse_book_file(path_b, args.book_b, verbose=args.verbose, adjust_leading_one=not args.no_adjust_leading_one)
    merged = merge_books(bookA_players, bookB_players)
    surebets_all = detect_td_surebets(merged)
    surebets = [s for s in surebets_all if s['roi_pct'] >= args.min_roi]
    out_file = Path('nfl_td_surebets.txt')
    with out_file.open('w', encoding='utf-8') as f:
        f.write('NFL TOUCHDOWN SUREBET ANALYSIS\n')
        f.write(f'Total players parsed (any book): {len(merged)}\n')
        f.write(f'Surebets found (ROI>={args.min_roi}%): {len(surebets)}\n\n')
        if surebets:
            f.write('SUREBETS (Yes TD vs No TD)\n')
            f.write('--------------------------------\n')
            for sb in surebets:
                f.write(f"{sb['player']}\n")
                f.write(f"  YES: {sb['yes']['odd']} @ {sb['yes']['book']}\n")
                f.write(f"  NO : {sb['no']['odd']} @ {sb['no']['book']}\n")
                f.write(f"  Margin {sb['margin_pct']}% | ROI {sb['roi_pct']}% | inv_sum {sb['inv_sum']} | stakes(YES={sb['stakes']['yes']}, NO={sb['stakes']['no']})\n\n")
        else:
            f.write('No cross-book touchdown surebets detected.\n')
    print(f"✅ Completed. Surebets: {len(surebets)} (ROI>={args.min_roi}%) -> {out_file}")

if __name__ == '__main__':
    main()
