"""FastAPI application exposing surebets and matches.

Usage (dev):
  uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload

Endpoints:
  GET /health           – service & cache status
  GET /surebets         – latest surebets JSON (optional ?min_profit=1.0)
  GET /matches          – latest matches list
  POST /refresh         – force refresh (simple token optional)

Static frontend served from ./public (index.html fetches /surebets).
"""
from __future__ import annotations
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional
import asyncio
import time
import os

from core.engine import capture_and_analyze

REFRESH_INTERVAL_SEC = 180  # 3 minutes
STARTUP_DELAY = 2

app = FastAPI(title="SureBet Live API", version="0.1.0")

cache = {
    'data': None,          # full dict from engine
    'updated_at': None,    # epoch seconds
    'refreshing': False,
    'error': None
}

def _should_refresh() -> bool:
    if cache['data'] is None:
        return True
    if cache['updated_at'] is None:
        return True
    return (time.time() - cache['updated_at']) > REFRESH_INTERVAL_SEC

async def _refresh_loop():
    await asyncio.sleep(STARTUP_DELAY)
    while True:
        if _should_refresh() and not cache['refreshing']:
            await _run_refresh()
        await asyncio.sleep(5)

async def _run_refresh(force: bool = False):
    if cache['refreshing']:
        return
    if not force and not _should_refresh():
        return
    cache['refreshing'] = True
    try:
        data = await asyncio.get_event_loop().run_in_executor(None, capture_and_analyze, {
            'pages': 3,
            'scroll_steps': 8,
            'raw_lines_limit': 0,  # keep full
            'min_odds_per_match': 3,
            'min_profit': 0.0,
            'best_aggregate': True
        })
        cache['data'] = data
        cache['updated_at'] = time.time()
        cache['error'] = data.get('error')
    finally:
        cache['refreshing'] = False

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(_refresh_loop())

@app.get('/health')
async def health():
    return {
        'status': 'ok',
        'updated_at': cache['updated_at'],
        'refreshing': cache['refreshing'],
        'matches': (len(cache['data']['matches']) if cache['data'] else 0),
        'surebets': (len(cache['data']['surebets']) if cache['data'] else 0),
        'error': cache['error']
    }

@app.get('/surebets')
async def get_surebets(min_profit: float = Query(0.0, ge=0.0, description="Filter surebets by minimum profit %")):
    if cache['data'] is None:
        raise HTTPException(status_code=503, detail='Cache not ready')
    surebets = cache['data']['surebets']
    if min_profit > 0:
        surebets = [s for s in surebets if s['profit_percent'] >= min_profit]
    return {
        'generated_at': cache['data']['generated_at'],
        'count': len(surebets),
        'surebets': surebets
    }

@app.get('/matches')
async def get_matches():
    if cache['data'] is None:
        raise HTTPException(status_code=503, detail='Cache not ready')
    return {
        'generated_at': cache['data']['generated_at'],
        'count': len(cache['data']['matches']),
        'matches': cache['data']['matches']
    }

@app.post('/refresh')
async def force_refresh():
    await _run_refresh(force=True)
    return {'status': 'triggered'}

# Serve static frontend if present
public_dir = os.path.join(os.path.dirname(__file__), '..', 'public')
if os.path.isdir(public_dir):
    app.mount('/', StaticFiles(directory=public_dir, html=True), name='public')
