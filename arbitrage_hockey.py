import re
import glob

def check_surebet(odds):
    """Calculate surebet profit % for 2-way or 3-way odds"""
    clean_odds = [o for o in odds if 0 < o < 50]
    if len(clean_odds) < 2:
        return None
    inv_sum = sum(1 / o for o in clean_odds)
    if inv_sum < 1:
        return round((1 - inv_sum) * 100, 2)
    return None

def parse_file(filename):
    matches = []
    with open(filename, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    i = 0
    while i < len(lines):
        line = lines[i]

        # Skip junk lines
        if any(x in line.lower() for x in ["fudbal", "košarka", "tenis", "promo", "banner", "http"]) \
           or re.match(r'^[\-\+\*]', line) \
           or line.isdigit():
            i += 1
            continue

        # Detect team lines (assume two consecutive lines are teams)
        if re.match(r'^[A-Za-zČĆŽŠĐ0-9][A-Za-zČĆŽŠĐ\s\-\.0-9]+$', line):
            if i + 1 < len(lines) and re.match(r'^[A-Za-zČĆŽŠĐ0-9][A-Za-zČĆŽŠĐ\s\-\.0-9]+$', lines[i + 1]):
                team1, team2 = line, lines[i + 1]
                current_match = {"teams": f"{team1} vs {team2}", "odds": {}}
                i += 2

                # Scan next 30 lines for odds
                end = min(len(lines), i + 30)
                odds_order = ["Home", "Draw", "Away", "H1", "H2", "manje", "vise"]
                odds_index = 0
                goal_line = None

                for j in range(i, end):
                    l = lines[j].replace(',', '.')
                    if re.match(r'^[\-\+]', l):
                        continue
                    m = re.match(r'^(\d+(\.\d+)?)(.*)$', l)
                    if m:
                        odd = float(m.group(1))
                        book = m.group(3).strip()

                        if odds_index < 5:  # 1/X/2 or H1/H2
                            current_match["odds"][odds_order[odds_index]] = (odd, book)
                        else:  # manje/vise
                            # check if previous line is goal line
                            goal_match = re.search(r'(\d+(\.\d+)?)', lines[j-1])
                            if not goal_line and goal_match:
                                goal_line = float(goal_match.group(1))
                            if odds_index == 5:
                                current_match["odds"]["manje"] = (odd, book, goal_line)
                            elif odds_index == 6:
                                current_match["odds"]["vise"] = (odd, book, goal_line)
                        odds_index += 1

                matches.append(current_match)
            else:
                i += 1
        else:
            i += 1
    return matches

# --- Main ---
all_matches = []

for filename in sorted(glob.glob("hockey_*.txt")):
    print(f"Parsing {filename} ...")
    matches = parse_file(filename)
    all_matches.extend(matches)

# Write all surebets
with open("hockey_surebets.txt", "w", encoding="utf-8") as f:
    count_surebets = 0
    for match in all_matches:
        odds = match["odds"]
        surebet_lines = []

        # 1/X/2 surebet
        if all(k in odds for k in ["Home","Draw","Away"]):
            profit = check_surebet([odds["Home"][0], odds["Draw"][0], odds["Away"][0]])
            if profit:
                surebet_lines.append(f"✅ 1/X/2 SUREBET → Profit: {profit}% "
                                     f"(Home={odds['Home'][0]}, Draw={odds['Draw'][0]}, Away={odds['Away'][0]})")

        # H1/H2 surebet
        if all(k in odds for k in ["H1","H2"]):
            profit = check_surebet([odds["H1"][0], odds["H2"][0]])
            if profit:
                surebet_lines.append(f"✅ H1/H2 SUREBET → Profit: {profit}% "
                                     f"(H1={odds['H1'][0]}, H2={odds['H2'][0]})")

        # Manje/Vise surebet
        if all(k in odds for k in ["manje","vise"]):
            profit = check_surebet([odds["manje"][0], odds["vise"][0]])
            if profit:
                surebet_lines.append(f"✅ Manje/Vise SUREBET → Profit: {profit}% "
                                     f"(manje={odds['manje'][0]}, vise={odds['vise'][0]}, line={odds['manje'][2]})")

        # Write to file if any surebet
        if surebet_lines:
            f.write(match["teams"] + "\n")
            for key in odds:
                if key in ["manje","vise"]:
                    f.write(f"  {key}: {odds[key][0]} @ {odds[key][1]} (line {odds[key][2]})\n")
                else:
                    f.write(f"  {key}: {odds[key][0]} @ {odds[key][1]}\n")
            for line in surebet_lines:
                f.write(line + "\n")
            f.write("\n")
            count_surebets += 1

print(f"✅ Found {count_surebets} hockey matches with surebets → hockey_surebets.txt created")
