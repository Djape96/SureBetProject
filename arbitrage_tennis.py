import glob
import re

def check_surebet(odds):
    clean_odds = [o for o, _ in odds if o > 0]
    if len(clean_odds) < 2:
        return None
    inv_sum = sum(1 / o for o in clean_odds)
    if inv_sum < 1:
        return round((1 - inv_sum) * 100, 2)
    return None

def parse_tennis_file(filename):
    matches = []
    with open(filename, encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    i = 0
    while i < len(lines):
        line = lines[i]
        # Detect two consecutive lines with player names
        if re.match(r'^[A-Za-zČĆŽŠĐ][A-Za-zČĆŽŠĐ\s\.\-\,]+$', line):
            if i + 1 < len(lines) and re.match(r'^[A-Za-zČĆŽŠĐ][A-Za-zČĆŽŠĐ\s\.\-\,]+$', lines[i + 1]):
                player1, player2 = line, lines[i + 1]
                current_match = {"match": f"{player1} vs {player2}", "odds": {}}
                i += 2

                # Read next lines until next match or end
                while i < len(lines):
                    l = lines[i].lower()
                    # Stop if next match starts
                    if re.match(r'^[A-Za-zČĆŽŠĐ][A-Za-zČĆŽŠĐ\s\.\-\,]+$', lines[i]) and i+1 < len(lines) and re.match(r'^[A-Za-zČĆŽŠĐ][A-Za-zČĆŽŠĐ\s\.\-\,]+$', lines[i+1]):
                        break

                    # Check for known labels
                    for label in ["h1","h2","1","2","handicap1","handicap2","manje","više","vise"]:
                        if l.startswith(label):
                            # Next line should contain the odds + bookmaker
                            if i + 1 < len(lines):
                                m = re.match(r'^(\-?\d+(\.\d+)?)(.*)$', lines[i+1].replace(',','.'))
                                if m:
                                    odd = float(m.group(1))
                                    book = m.group(3).strip()
                                    key = label
                                    if key == "vise":  # unify spelling
                                        key = "više"
                                    current_match["odds"][key] = (odd, book)
                                i += 1  # skip odds line
                    i += 1
                matches.append(current_match)
            else:
                i += 1
        else:
            i += 1
    return matches

# --- Main ---
all_matches = []
for filename in sorted(glob.glob("tenis_*.txt")):
    print(f"Parsing {filename} ...")
    matches = parse_tennis_file(filename)
    all_matches.extend(matches)

# Write tennis surebets
with open("tennis_surebets.txt", "w", encoding="utf-8") as f:
    count_surebets = 0
    for match in all_matches:
        for cat in [("H1","H2"),("1","2"),("Handicap1","Handicap2"),("manje","više")]:
            if cat[0] in match["odds"] and cat[1] in match["odds"]:
                odds_list = [match["odds"][cat[0]], match["odds"][cat[1]]]
                profit = check_surebet(odds_list)
                if profit:
                    f.write(match["match"] + "\n")
                    f.write(f"  {cat[0]}: {match['odds'][cat[0]][0]} @ {match['odds'][cat[0]][1]}\n")
                    f.write(f"  {cat[1]}: {match['odds'][cat[1]][0]} @ {match['odds'][cat[1]][1]}\n")
                    f.write(f"  ✅ {cat[0]} / {cat[1]} SUREBET → Profit: {profit}%\n\n")
                    count_surebets += 1

print(f"✅ Found {count_surebets} tennis surebets → tennis_surebets.txt created")
