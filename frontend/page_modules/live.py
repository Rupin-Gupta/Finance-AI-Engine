import json

import streamlit as st
import streamlit.components.v1 as components

from api_client import API_BASE, API_KEY

_DEFAULT = "AAPL,MSFT,GOOGL,TSLA,AMZN"


def _ws_url(api_base: str) -> str:
    """Derive the WebSocket URL from the REST base (http→ws, https→wss)."""
    base = api_base.rstrip("/")
    if base.startswith("https://"):
        base = "wss://" + base[len("https://"):]
    elif base.startswith("http://"):
        base = "ws://" + base[len("http://"):]
    return base + "/v1/stream"


# Single JSON injection point (__CONFIG__) keeps the dynamic values safely encoded.
_TEMPLATE = """
<div style="font-family:system-ui,sans-serif;color:#ccc">
  <div id="status" style="font-weight:700;margin-bottom:8px">connecting…</div>
  <div id="quotes" style="display:flex;flex-wrap:wrap;gap:8px"></div>
  <h4 style="margin:14px 0 4px">Decisions</h4><div id="decisions"></div>
  <h4 style="margin:14px 0 4px">Alerts</h4><div id="alerts"></div>
</div>
<script>
const CFG = __CONFIG__;
const $ = id => document.getElementById(id);
let ws, backoff = 1000, alerts = [];
const fmtPct = p => p == null ? '' : (p >= 0 ? '+' : '') + Number(p).toFixed(2) + '%';

function renderQuotes(q) {
  const el = $('quotes'); el.innerHTML = '';
  Object.keys(q).sort().forEach(sym => {
    const d = q[sym], up = (d.change_pct || 0) >= 0, col = up ? '#00c851' : '#ff4444';
    el.innerHTML += `<div style="background:#1a1a2e;border-left:4px solid ${col};border-radius:10px;padding:10px 14px;min-width:120px">
      <div style="font-size:.75rem;color:#aaa;font-weight:700">${sym}</div>
      <div style="font-size:1.3rem;font-weight:800;color:#fff">$${Number(d.price).toFixed(2)}</div>
      <div style="color:${col};font-weight:600">${fmtPct(d.change_pct)} <span style="color:#666">${d.source}</span></div>
    </div>`;
  });
}
function renderDecisions(dec) {
  const el = $('decisions'); el.innerHTML = '';
  const COL = {BUY:'#00c851', SELL:'#ff4444', HOLD:'#888'};
  Object.keys(dec).sort().forEach(sym => {
    const d = dec[sym], c = COL[d.recommendation] || '#888';
    el.innerHTML += `<span style="display:inline-block;margin:3px;padding:3px 8px;border-radius:6px;background:#15151f">
      <b>${sym}</b> <span style="color:${c};font-weight:700">${d.recommendation}</span>
      <span style="color:#888">${d.confidence != null ? (d.confidence*100).toFixed(0)+'%' : ''} ${d.risk_level || ''}</span></span>`;
  });
}
function addAlerts(list) {
  if (!list || !list.length) return;
  alerts = list.concat(alerts).slice(0, 30);
  const el = $('alerts'); el.innerHTML = '';
  alerts.forEach(a => {
    el.innerHTML += `<div style="border-left:3px solid #ffa500;padding:2px 8px;margin:2px 0;font-size:.85rem">
      <b>${a.symbol}</b> ${a.alert_type} — ${a.value} (thr ${a.threshold}) <span style="color:#666">${a.detected_at || ''}</span></div>`;
  });
}
function connect() {
  ws = new WebSocket(CFG.wsUrl + '?api_key=' + encodeURIComponent(CFG.apiKey));
  ws.onopen = () => { $('status').textContent = '● live'; $('status').style.color = '#00c851'; backoff = 1000;
    ws.send(JSON.stringify({action: 'subscribe', symbols: CFG.symbols})); };
  ws.onmessage = e => { const m = JSON.parse(e.data);
    if (m.type === 'tick') { renderQuotes(m.quotes || {}); renderDecisions(m.decisions || {}); addAlerts(m.alerts || []); } };
  ws.onclose = () => { $('status').textContent = '● reconnecting…'; $('status').style.color = '#ffa500';
    setTimeout(connect, backoff); backoff = Math.min(backoff * 2, 15000); };
  ws.onerror = () => { try { ws.close(); } catch (e) {} };
}
connect();
</script>
"""


def _build_widget_html(ws_url: str, api_key: str, symbols: list[str]) -> str:
    cfg = json.dumps({"wsUrl": ws_url, "apiKey": api_key, "symbols": symbols})
    return _TEMPLATE.replace("__CONFIG__", cfg)


def render():
    st.header("Live Dashboard")
    st.caption("Real-time quotes, decisions, and alerts streamed over WebSocket — no page refresh.")

    raw = st.text_input("Symbols (comma-separated)", _DEFAULT, key="live_symbols")
    symbols = [s.strip().upper() for s in raw.split(",") if s.strip()]

    ws_url = _ws_url(API_BASE)
    components.html(_build_widget_html(ws_url, API_KEY, symbols), height=640, scrolling=True)

    st.caption(f"Endpoint: {ws_url} · auth via api_key query param (use wss:// in production).")
