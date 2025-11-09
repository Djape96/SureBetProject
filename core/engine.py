"""Core engine to capture matches and compute surebets for reuse (API / UI).

This wraps selected functions from `enhanced_football_analyzer` without invoking
its CLI parser. Keeps side-effects minimal and returns structured JSON.

If later you refactor the analyzer, centralize logic here so the API and any
other interfaces (CLI, batch jobs) share one path.
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
import importlib
import traceback
import os

# Import the existing analyzer module dynamically so edits there are picked up.
analyzer = importlib.import_module('enhanced_football_analyzer')

DEFAULT_CAPTURE_CONF = dict(
    headless=True,
    verbose=False,
    scroll_steps=6,
    pages=3,
    raw_lines_limit=1500,
)

def _match_margin(match: Dict[str, Any]) -> float | None:
    """Return implied margin (%) for 1X2 if all three outcomes present."""
    odds_map = match.get('odds', {})
    if not all(k in odds_map for k in ('Home','Draw','Away')):
        return None
    try:
        inv_sum = sum(1/odds_map[k][0] for k in ('Home','Draw','Away') if odds_map[k][0] > 0)
        return round((inv_sum - 1) * 100, 3)
    except Exception:
        return None

def capture_and_analyze(config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Perform an auto snapshot capture + parse + surebet analysis.

    Parameters
    ----------
    config: dict overriding DEFAULT_CAPTURE_CONF. Recognized keys:
        headless, verbose, scroll_steps, pages, raw_lines_limit,
        min_odds_per_match, min_profit, flat_threshold, take_best, best_aggregate

    Returns
    -------
    dict with keys: generated_at, source_type, matches, surebets
    """
    cfg = {**DEFAULT_CAPTURE_CONF, **(config or {})}
    # Ensure global flags respected (BEST_AGGREGATE)
    if getattr(analyzer, 'BEST_AGGREGATE', None) is not None:
        analyzer.BEST_AGGREGATE = bool(cfg.get('best_aggregate', True))

    result: Dict[str, Any] = {
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'error': None,
        'matches': [],
        'surebets': [],
        'source_type': 'auto'
    }

    try:
        auto_file = analyzer.auto_capture_static(
            headless=cfg.get('headless', True),
            verbose=cfg.get('verbose', False),
            scroll_steps=cfg.get('scroll_steps', 6),
            pages=cfg.get('pages', 1),
            raw_lines_limit=cfg.get('raw_lines_limit', 1500)
        )
        if not auto_file or not os.path.exists(auto_file):
            result['error'] = 'capture_failed'
            return result
        matches = analyzer.parse_file(auto_file)
        # Optional min odds filter
        min_odds_per_match = cfg.get('min_odds_per_match', 3)
        if min_odds_per_match:
            matches = [m for m in matches if len(m.get('odds', {})) >= min_odds_per_match]
        # Compute margins & shape
        shaped_matches = []
        for m in matches:
            shaped_matches.append({
                'match': m['teams'],
                'odds': {k: {'odd': v[0], 'book': v[1]} for k,v in m['odds'].items()},
                'margin_percent': _match_margin(m)
            })
        surebets_raw = analyzer.analyze_surebets(matches, verbose=False, min_profit=cfg.get('min_profit', 0.0))
        shaped_surebets = []
        for sb in surebets_raw:
            shaped_surebets.append({
                'match': sb['match'],
                'type': sb['type'],
                'profit_percent': sb['profit'],
                'odds': {k: {'odd': v[0], 'book': v[1]} for k,v in sb['odds'].items()},
                'stakes': [
                    {'stake': s[0], 'odd': s[1], 'book': s[2]} for s in (sb.get('stakes') or [])
                ],
                'abs_profit': sb.get('abs_profit')
            })
        result.update({
            'matches': shaped_matches,
            'surebets': shaped_surebets,
            'source_type': 'auto'
        })
        return result
    except Exception as e:
        result['error'] = str(e)
        result['trace'] = traceback.format_exc(limit=5)
        return result

__all__ = [
    'capture_and_analyze'
]
