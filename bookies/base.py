"""Base classes & helpers for bookmaker scrapers (Mozzart, MaxBet, etc.)."""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Optional, Iterable
import unicodedata, re, time
import requests
from typing import Optional as _Opt
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.common.by import By
    SELENIUM_AVAILABLE = True
except Exception:
    SELENIUM_AVAILABLE = False

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'

@dataclass
class MarketOdds:
    under: Optional[float] = None  # 0-2 goals (Under 2.5)
    over: Optional[float] = None   # 3+ goals (Over 2.5)

@dataclass
class MatchOdds:
    bookmaker: str
    home: str
    away: str
    markets: MarketOdds

def normalize_team(name: str) -> str:
    if not name:
        return ''
    n = unicodedata.normalize('NFKD', name).encode('ascii','ignore').decode('ascii')
    n = n.lower()
    n = re.sub(r'[^a-z0-9]+', ' ', n).strip()
    return n

def fetch_html(url: str, timeout: int = 12) -> str:
    headers = {'User-Agent': USER_AGENT, 'Accept': 'text/html,application/xhtml+xml'}
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.text

class BookmakerScraper:
    name: str = 'BASE'
    url: str = ''
    use_selenium: bool = False
    selenium_wait: int = 6
    selenium_scroll: int = 0
    selenium_headless: bool = True

    def fetch(self) -> str:
        if not self.use_selenium:
            return fetch_html(self.url)
        if not SELENIUM_AVAILABLE:
            return fetch_html(self.url)
        opts = ChromeOptions()
        if self.selenium_headless:
            opts.add_argument('--headless=new')
        opts.add_argument('--no-sandbox')
        opts.add_argument('--disable-gpu')
        opts.add_argument('--disable-dev-shm-usage')
        driver = webdriver.Chrome(options=opts)
        try:
            driver.get(self.url)
            end = time.time() + self.selenium_wait
            while time.time() < end:
                time.sleep(0.25)
            # basic scroll
            for _ in range(self.selenium_scroll):
                driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
                time.sleep(0.6)
            html = driver.page_source
        finally:
            try:
                driver.quit()
            except Exception:
                pass
        return html

    def parse(self, html: str) -> List[MatchOdds]:  # to override
        raise NotImplementedError

    def get_matches(self) -> List[MatchOdds]:
        try:
            html = self.fetch()
            return self.parse(html)
        except Exception:
            return []

def match_key(home: str, away: str) -> str:
    return normalize_team(home)+'__'+normalize_team(away)

def reverse_key(key: str) -> str:
    a,b = key.split('__',1)
    return b+'__'+a
