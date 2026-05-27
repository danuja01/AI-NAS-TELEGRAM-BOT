"""FastAPI app for uptime dashboard."""

from __future__ import annotations

import asyncio
import hmac
from typing import Any, Dict, List

from fastapi import FastAPI, Header, HTTPException, WebSocket
from fastapi.responses import HTMLResponse

import config
from monitoring.uptime import store

app = FastAPI(title="NAS Uptime Dashboard", docs_url=None, redoc_url=None)

_DASHBOARD_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>NAS Monitors</title>
<style>
body{font-family:system-ui,sans-serif;margin:1rem;background:#0f1419;color:#e7e9ea}
h1{font-size:1.25rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:.75rem}
.card{border-radius:8px;padding:.75rem;background:#1a2332;border:1px solid #2f3b4a}
.up{border-left:4px solid #00ba7c}.down{border-left:4px solid #f4212e}
.name{font-weight:600}.meta{font-size:.85rem;color:#8b98a5;margin-top:.35rem}
</style></head><body>
<h1>NAS Monitor Grid</h1>
<div id="grid" class="grid">Loading…</div>
<script>
const ws=new WebSocket((location.protocol==='https:'?'wss:':'ws:')+location.host+'/ws');
ws.onmessage=e=>{const d=JSON.parse(e.data);const g=document.getElementById('grid');
g.innerHTML=d.monitors.map(m=>`<div class="card ${m.last_status==='up'?'up':'down'}">
<div class="name">${m.name}</div><div class="meta">${m.type} · ${m.last_status||'?'}
 · ${m.uptime_percentage!=null?m.uptime_percentage.toFixed(1)+'% uptime':''}
${m.response_time_ms!=null?' · '+Math.round(m.response_time_ms)+'ms':''}</div></div>`).join('')};
ws.onerror=()=>{document.getElementById('grid').textContent='WebSocket error'};
</script></body></html>"""


def _auth_ok(secret: str | None) -> bool:
    expected = config.UPTIME_DASHBOARD_SECRET or ""
    if not expected:
        return True  # dev only — set secret in production
    return bool(secret) and hmac.compare_digest(secret, expected)


@app.get("/", response_class=HTMLResponse)
async def index(x_dashboard_secret: str | None = Header(None, alias="X-Dashboard-Secret")):
    if not _auth_ok(x_dashboard_secret):
        raise HTTPException(401, "Unauthorized")
    return HTMLResponse(_DASHBOARD_HTML)


@app.get("/api/monitors")
async def api_monitors(
    x_dashboard_secret: str | None = Header(None, alias="X-Dashboard-Secret"),
) -> List[Dict[str, Any]]:
    if not _auth_ok(x_dashboard_secret):
        raise HTTPException(401, "Unauthorized")
    return await store.list_monitors()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            monitors = await store.list_monitors()
            payload = {
                "monitors": [
                    {
                        "name": m["name"],
                        "type": m["type"],
                        "last_status": m.get("last_status"),
                        "uptime_percentage": m.get("uptime_percentage"),
                        "response_time_ms": m.get("response_time_ms"),
                    }
                    for m in monitors
                ]
            }
            await websocket.send_json(payload)
            await asyncio.sleep(5)
    except Exception:
        pass
