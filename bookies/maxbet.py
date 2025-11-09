"""MaxBet live football scraper (heuristic prototype)."""
from __future__ import annotations
from typing import List
from bs4 import BeautifulSoup
import re
from .base import BookmakerScraper, MatchOdds, MarketOdds

class MaxBetScraper(BookmakerScraper):
    name = 'MAXBET'
    url = 'https://www.maxbet.rs/sr/kladjenje-uzivo/fudbal/S'

    def parse(self, html: str) -> List[MatchOdds]:
        soup = BeautifulSoup(html, 'html.parser')
        matches: List[MatchOdds] = []
        # Simple heuristic: each row with two team names and several odds numbers
        rows = soup.find_all(lambda t: t.name in ['div','tr','li'] and t.get_text(strip=True))
        for row in rows:
            txt = ' '.join(row.get_text(' ', strip=True).split())
            odds_raw = re.findall(r'\b\d+(?:\.\d+)?\b', txt)
            if len(odds_raw) < 2:
                continue
            # Extract team name candidates: split on odds and trim
            alpha_segments = [seg.strip() for seg in re.split(r'\d+\.\d+|\d+', txt) if re.search(r'[A-Za-z]', seg)]
            alpha_segments = [a for a in alpha_segments if 3 < len(a) < 60]
            distinct = []
            for seg in alpha_segments:
                if seg not in distinct:
                    distinct.append(seg)
                if len(distinct) == 2:
                    break
            if len(distinct) != 2:
                continue
            home, away = distinct
            odds_vals = [float(o) for o in odds_raw if 1.05 <= float(o) <= 15]
            if len(odds_vals) < 2:
                continue
            odds_vals.sort()
            under, over = odds_vals[0], odds_vals[-1]
            matches.append(MatchOdds(bookmaker=self.name, home=home, away=away, markets=MarketOdds(under=under, over=over)))
            if len(matches) > 120:
                break
        return matches

__all__ = ['MaxBetScraper']
