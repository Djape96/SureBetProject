from telegram_notifier import send_surebets_summary, format_surebets_summary

# Dummy surebets for dry run
surebets = [
    {
        'match': {'time': '09:15', 'player1': 'Alice', 'player2': 'Bob'},
        'type': 'Match Winner',
        'margin_pct': 3.12,
        'roi_pct': 3.22,
        'stakes': {'Home': 48.9, 'Away': 51.1},
        'odds_str': 'Home=2.10, Away=1.95'
    },
    {
        'match': {'time': '10:40', 'player1': 'Carol', 'player2': 'Dana'},
        'type': 'Totals',
        'margin_pct': 1.55,
        'roi_pct': 1.57,
        'stakes': {'Under': 49.4, 'Over': 50.6},
        'odds_str': 'Under=1.98, Over=2.02'
    }
]

print("--- Formatted Telegram Summary Preview (no header) ---")
print(format_surebets_summary(surebets, total_matches=5, include_header=False))
print("--- Formatted Telegram Summary Preview (with header) ---")
print(format_surebets_summary(surebets, total_matches=5, include_header=True))
print("(If env vars set, sending now - will use no header by default)\n")
send_surebets_summary(surebets, total_matches=5)
print("Done.")
