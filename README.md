# SureBet Project

## New: Lightweight API & Mobile-Friendly Web View

You can now run a FastAPI service that periodically captures odds (auto snapshot) and serves JSON plus a simple mobile-friendly page you can open on your phone (same Wi‑Fi).

### Quick Start

1. Install dependencies:
  ```powershell
  pip install -r requirements.txt
  ```
2. Start API:
  ```powershell
  ./run_api.ps1 -Port 8000
  ```
3. From your phone browser (on same LAN) open:
  ```
  http://<YOUR_PC_LAN_IP>:8000/
  ```
4. Adjust minimum profit at bottom; list auto-refreshes every 60s.

### API Endpoints

| Method | Path       | Description                      |
|--------|------------|----------------------------------|
| GET    | /health    | Service status / counts          |
| GET    | /surebets  | Latest surebets (?min_profit=)   |
| GET    | /matches   | Latest matches + margins         |
| POST   | /refresh   | Force immediate refresh          |

### How It Works
Background task triggers `auto_capture_static` (Selenium + parsing) every ~3 minutes, converts to structured JSON and caches. The frontend fetches `/surebets` and renders cards.

### Notes
* Selenium still runs headless on the server machine; phone only views data.
* Increase capture frequency: adjust `REFRESH_INTERVAL_SEC` in `api/app.py`.
* To raise depth (more matches): tweak pages / scroll in `_run_refresh` config.
* For native mobile app later, reuse these JSON endpoints.

## O/U 2.5 Surebet Tracker (Mozzart + MaxBet)

Prototype tracker combining two bookmakers to find arbitrage on Total Goals 2.5 (Under = 0-2, Over = 3+).

### Run
Single run (show surebets with profit >= 0.5%):
```powershell
python tracker.py --min-profit 0.5
```

Loop every 2 minutes and write JSON:
```powershell
python tracker.py --loop 120 --min-profit 0.3
```

Creates/updates `surebets_ou.json` with structured results.

### Current Limitations
Heuristic HTML parsing (picks extreme odds numbers in nearby text blocks). It may:
* Miss real Under/Over 2.5 market if layout differs
* Confuse other totals (1.5 / 3.5) if numbers cluster

### Improving Accuracy (Next Steps)
1. Open bookmaker pages, capture HTML, identify CSS/path for exact 2.5 market rows.
2. Replace generic scans in `bookies/mozzart.py` & `bookies/maxbet.py` with targeted selectors.
3. Add validation: ignore odds outside plausible 1.10–10.0 range.
4. Distinguish multiple total lines (store line=2.5, 3.5 etc.).
5. Optional: integrate into FastAPI (`/ou_surebets`).

### Extending
Add another bookmaker: create `bookies/<name>.py` implementing `BookmakerScraper.parse()` returning `MatchOdds` with a `total_25` entry.

---

# SureBet Football Analyzer

Enhanced tool to parse static bookmaker text dumps or scrape live odds (TopTiket) and detect arbitrage (surebet) opportunities.

## Features
- Static file parsing (`index_*.txt` fallback)
- Multi-strategy live fetch: plain HTTP -> Selenium (headless / visible)
- Dynamic retries, scrolling, selector wait
- Heuristic odds detection + embedded JSON discovery
- Surebet detection for 1X2 and 0-2 / 3+
- Stake allocation & estimated profit
- Verbose diagnostics & optional log file
- Min profit filter (--min-profit)

## Installation
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Basic Usage
```powershell
python .\enhanced_football_analyzer.py              # Try live then fallback
python .\enhanced_football_analyzer.py --no-live    # Force static only
python .\enhanced_football_analyzer.py --live-only  # Fail if live not available
```

## Advanced Live Options
```powershell
python .\enhanced_football_analyzer.py \
  --verbose \
  --no-headless \
  --selenium-wait 20 \
  --scroll-steps 10 \
  --min-content-kb 25 \
  --retries 3 \
  --selector "div[class*=odd]" \
  --min-profit 0.8 \
  --log-file fetch.log
```

### Flags Explained
- `--verbose` Extra debug output.
- `--no-live` Skip live attempts completely.
- `--live-only` Do not fallback to static files.
- `--no-headless` Show browser window (useful for debugging selectors / consent popups).
- `--selenium-wait` Seconds to wait for initial body load.
- `--scroll-steps` How many scroll cycles to trigger lazy load.
- `--min-content-kb` Minimum HTML size (kilobytes) to accept as a valid page.
- `--retries` Selenium retry attempts.
- `--selector` Optional CSS selector to explicitly wait for odds container.
- `--min-profit` Filter out surebets below this percent.
- `--log-file` Append diagnostic lines to a file.

## Output
- `live_data.txt` Raw HTML from live fetch.
- `live_extracted.txt` Text-extracted content (used for parsing with existing logic).
- `live_embedded.json` (optional) First embedded JSON blob containing odds (heuristic).
- `static_football_matches_*.txt` Snapshot of parsed matches.
- `static_football_surebets_*.txt` Surebet results.

## Surebet Calculation
A surebet is detected when sum(1/odd_i) < 1 across mutually exclusive outcomes. Profit% = (1 - sum(1/odd_i))*100. Stake allocation distributes a constant return for the chosen total stake (default 100 units).

## Troubleshooting
1. Live fetch returns placeholder: Run with `--no-headless` and inspect site (check for consent modals). Increase `--selenium-wait` and `--scroll-steps`.
2. No surebets: Try lowering `--min-profit` (default 0). Ensure odds parsed correctly with `--verbose`.
3. Selenium not installed: `pip install selenium webdriver-manager`.
4. API approach: Open DevTools > Network > Fetch/XHR and identify a JSON endpoint for odds; replicate with `requests` for more performance.

## Next Enhancements (Ideas)
- Direct JSON API integration (if endpoint discovered)
- Multiprocessing / async for multiple bookmakers
- Database persistence (SQLite) + historical ROI tracking
- Alert system (email / webhook) when new surebet above threshold

## Disclaimer
Use responsibly. Odds scraping may violate terms of service of some providers; ensure compliance with local laws and site policies.

---

## NFL Surebet Analyzer (New)

A streamlined script `arbitrage_nfl.py` that mirrors the football arbitrage workflow for the NFL (American Football) 1/2 (Home/Away) market on TopTiket.

### Features
- Automated capture (requests + Selenium fallback)
- Text + DOM heuristic parsing (reuses logic from `enhanced_nfl_analyzer.py`)
- 2-way surebet detection (Home vs Away)
- Stake allocation for a configurable bankroll (default 100 units)
- Clean summary output -> `nfl_surebets.txt`

### Run
```powershell
python arbitrage_nfl.py                # Default (min-profit=0, stake=100)
python arbitrage_nfl.py --min-profit 1.0 --stake 250
python arbitrage_nfl.py --three-days   # Try to enable 3-day range like football script
python arbitrage_nfl.py --verbose
```

### Environment Overrides
- `NFL_MIN_PROFIT`  Minimum ROI% to include (default 0)
- `NFL_STAKE_TOTAL` Total stake allocated across the two outcomes (default 100)

Example:
```powershell
$env:NFL_MIN_PROFIT=1.0; $env:NFL_STAKE_TOTAL=200; python arbitrage_nfl.py
```

### Output File Structure (`nfl_surebets.txt`)
```
TOPTIKET NFL ANALYSIS
Total matches: <N>
Surebets found: <M>

SUREBETS (Risk-Free Profit)
--------------------------------
<Match Name>
   - 1/2: Margin <overround_edge>% | ROI <roi>% | odds[Home=<odd1>, Away=<odd2>] | stakes(Home=<amt1>, Away=<amt2>)
```

If no surebets are detected (common when using a single bookmaker feed) the file will state this and advise adding more bookmakers.

### Next Extensions
- Merge with additional bookmaker sources (e.g., MaxBet/Mozzart) for cross-book 1/2 edges
- Add Moneyline / Handicap / Totals once reliably parsed
- Integrate into FastAPI endpoints (`/nfl/surebets`)

---

## Player Specials Surebet Analyzer (New)

A specialized script `arbitrage_player_specials.py` for analyzing player special bets (points, assists, rebounds) from TopTiket's Player Specials page, focusing on Under/Over markets.

### Features
- JavaScript-heavy page scraping with Selenium
- Multi-page support (3-4 pages as available)
- Player name and team extraction  
- Under/Over odds parsing for player statistics
- Surebet detection for two-way player prop markets
- Stake allocation for configurable bankroll (default 100 units)
- Clean summary output -> `player_specials_surebets.txt`

### Run
```powershell
python arbitrage_player_specials.py                    # Default (min-profit=0, stake=100, pages=4)
python arbitrage_player_specials.py --min-profit 1.0 --stake 250
python arbitrage_player_specials.py --pages 2          # Scrape fewer pages for faster execution
python arbitrage_player_specials.py --verbose          # Show detailed parsing info
```

### Environment Overrides
- `PLAYER_MIN_PROFIT`  Minimum ROI% to include (default 0)
- `PLAYER_STAKE_TOTAL` Total stake allocated across Under/Over outcomes (default 100)

Example:
```powershell
$env:PLAYER_MIN_PROFIT=0.5; $env:PLAYER_STAKE_TOTAL=150; python arbitrage_player_specials.py
```

### Output File Structure (`player_specials_surebets.txt`)
```
TOPTIKET PLAYER SPECIALS ANALYSIS
Total player specials: <N>
Surebets found: <M>
Pages scraped: <P>

SUREBETS (Risk-Free Profit)
--------------------------------
<Player Name>
   - Points: Margin <margin>% | ROI <roi>% | odds[Under=<odd1>, Over=<odd2>] | stakes(Under=<amt1>, Over=<amt2>)
```

### Enhanced Analyzer
Also includes `enhanced_player_specials_analyzer.py` for detailed analysis and match export:

```powershell
python enhanced_player_specials_analyzer.py --verbose --pages 4 --min-profit 0.5
```

### Page Structure Support
The analyzer supports the TopTiket player specials format:
- Player names (e.g., "Moneke C.")
- Team names (e.g., "Crvena zvezda", "Fenerbahce")
- Three-number sequences: Under odds, stat value, Over odds
- Currently focuses on Points markets but easily extensible

### Typical Output Example
```
[player_specials] Moneke C. (Crvena zvezda) 13.5 pts -> Under=1.93, Over=1.92
[player_specials] Baldwin W. (Fenerbahce) 15.5 pts -> Under=1.9, Over=1.99
[player_specials] Vezenkov S. (Olympiacos) 21.5 pts -> Under=1.92, Over=1.96
```

### Next Extensions
- Add support for other player stats (assists, rebounds, steals, etc.)
- Cross-bookmaker integration for better arbitrage opportunities
- Historical tracking of player performance vs. lines
- Integration with main FastAPI endpoints (`/player_specials/surebets`)

