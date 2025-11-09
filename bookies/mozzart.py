"""Mozzart live football scraper (heuristic, minimal HTML assumptions).

Parses matches and extracts Under/Over 2.5 style odds if recognizable.
Note: Real site structure may need CSS selectors / JSON endpoints; adjust later.
"""
from __future__ import annotations
from typing import List
from bs4 import BeautifulSoup
import re
from .base import BookmakerScraper, MatchOdds, MarketOdds

class MozzartScraper(BookmakerScraper):
    name = 'MOZZART'
    url = 'https://www.mozzartbet.com/sr/uzivo/sport/1'

    def parse(self, html: str) -> List[MatchOdds]:
        soup = BeautifulSoup(html, 'html.parser')
        matches: List[MatchOdds] = []
        # Heuristic: find containers that have two team names and odds numbers
        team_re = re.compile(r'[A-Za-z].+\bvs\b.+', re.IGNORECASE)
        # If site lists teams in separate spans, collect sequences
        # Approach: gather candidate blocks with multiple odds buttons
        for block in soup.find_all(lambda t: t.name in ['div','li'] and t.get_text(strip=True)):
            txt = ' '.join(block.get_text(' ', strip=True).split())
            # Attempt to split by newline markers for teams
            # Fallback: look for patterns with numbers containing decimal odds
            odds_raw = re.findall(r'\b\d+(?:\.\d+)?\b', txt)
            if len(odds_raw) < 4: # need some numbers to consider
                continue
            # Extract potential team lines (heuristic: longest alpha segments)
            words = [w for w in re.split(r'\s{2,}', txt) if w]
            alpha_segments = [seg for seg in re.split(r'\d+\.\d+|\d+', txt) if re.search(r'[A-Za-z]', seg)]
            alpha_segments = [a.strip() for a in alpha_segments if 3 < len(a.strip()) < 60]
            # Simplify: take first two distinct alpha phrases as teams
            distinct = []
            for seg in alpha_segments:
                if seg not in distinct:
                    distinct.append(seg)
                if len(distinct) == 2:
                    break
            if len(distinct) != 2:
                continue
            home, away = distinct
            # Odds: look for possible Under/Over 2.5 markers; placeholder:
            # We try to pair two odds near tokens like '2-3', 'UG', etc. For now pick highest two mid-range odds as over/under
            odds_vals = [float(o) for o in odds_raw if 1.05 <= float(o) <= 10]
            if len(odds_vals) < 2:
                continue
            odds_vals.sort(reverse=True)
            # naive mapping: bigger might be 'Under' or 'Over' depending; we store both
            under, over = odds_vals[-1], odds_vals[0]  # spread extremes
            matches.append(MatchOdds(bookmaker=self.name, home=home, away=away, markets=MarketOdds(under=under, over=over)))
            if len(matches) > 120: # safety cutoff
                break
        return matches

__all__ = ['MozzartScraper']
