#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MD Khider International Market - Version 2
لوحة أسعار الذهب والفضة والنفط + إشارات توقع
"""

import json
import math
import os
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    print("Installing required packages...")
    import subprocess
    subprocess.check_call(["pip", "install", "yfinance", "pandas", "numpy", "-q"])
    import yfinance as yf
    import pandas as pd

# ====================== الإعدادات ======================
PORT = int(os.environ.get("PORT", 8080))
HOST = "0.0.0.0"

# بيانات التواصل
PHONE = "+256773395517"
WHATSAPP = "+250793902079"
WHATSAPP_LINK = "https://wa.me/250793902079"

SYMBOLS = {
    "gold":   {"ticker": "GC=F", "name": "الذهب", "unit": "دولار / أونصة", "icon": "🥇"},
    "silver": {"ticker": "SI=F", "name": "الفضة", "unit": "دولار / أونصة", "icon": "🥈"},
    "wti":    {"ticker": "CL=F", "name": "نفط WTI", "unit": "دولار / برميل", "icon": "🛢️"},
    "brent":  {"ticker": "BZ=F", "name": "نفط Brent", "unit": "دولار / برميل", "icon": "🛢️"},
}

_cache = {}
CACHE_SECONDS = 90

def get_cached(key, fn):
    now = time.time()
    if key in _cache and now - _cache[key]["t"] < CACHE_SECONDS:
        return _cache[key]["d"]
    data = fn()
    _cache[key] = {"d": data, "t": now}
    return data

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def make_signal(df):
    if len(df) < 50:
        return {"text": "بيانات غير كافية", "color": "neutral", "score": 0, "details": []}

    close = df["Close"]
    rsi = float(calc_rsi(close).iloc[-1])
    ma20 = float(close.rolling(20).mean().iloc[-1])
    ma50 = float(close.rolling(50).mean().iloc[-1])
    last = float(close.iloc[-1])
    prev = float(close.iloc[-2])

    score = 0
    details = []

    if rsi < 30:
        score += 30
        details.append(f"RSI = {rsi:.1f} → تشبع بيعي (فرصة صعود)")
    elif rsi > 70:
        score -= 30
        details.append(f"RSI = {rsi:.1f} → تشبع شرائي (احتمال هبوط)")
    else:
        details.append(f"RSI = {rsi:.1f} (محايد)")

    if ma20 > ma50 and last > ma20:
        score += 25
        details.append("اتجاه صاعد (السعر فوق المتوسطات)")
    elif ma20 < ma50 and last < ma20:
        score -= 25
        details.append("اتجاه هابط (السعر تحت المتوسطات)")
    else:
        details.append("المتوسطات مختلطة")

    change = ((last - prev) / prev) * 100
    if change > 0.4:
        score += 10
        details.append(f"زخم يومي إيجابي ({change:+.2f}%)")
    elif change < -0.4:
        score -= 10
        details.append(f"زخم يومي سلبي ({change:+.2f}%)")

    if score >= 25:
        text, color = "ارتفاع محتمل", "bullish"
    elif score <= -25:
        text, color = "انخفاض محتمل", "bearish"
    else:
        text, color = "محايد / تقلب", "neutral"

    return {
        "text": text,
        "color": color,
        "score": score,
        "confidence": min(90, abs(score) * 2 + 25),
        "details": details,
        "rsi": round(rsi, 1)
    }

def fetch_one(key):
    info = SYMBOLS[key]
    def _do():
        t = yf.Ticker(info["ticker"])
        hist = t.history(period="3mo", interval="1d")
        if hist.empty:
            return None
        last = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else last
        change = last - prev
        change_pct = (change / prev) * 100 if prev else 0

        # سعر الجرام للذهب والفضة
        gram = round(last / 31.1035, 2) if key in ("gold", "silver") else None

        signal = make_signal(hist)
        chart = {
            "dates": [d.strftime("%m-%d") for d in hist.tail(20).index],
            "prices": [round(float(x), 2) for x in hist["Close"].tail(20).tolist()]
        }
        return {
            "key": key,
            "name": info["name"],
            "icon": info["icon"],
            "unit": info["unit"],
            "price": round(last, 2),
            "gram": gram,
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "high": round(float(hist["High"].max()), 2),
            "low": round(float(hist["Low"].min()), 2),
            "signal": signal,
            "chart": chart,
            "updated": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
    return get_cached(f"p_{key}", _do)

def fetch_all():
    result = {}
    for k in SYMBOLS:
        try:
            result[k] = fetch_one(k)
        except Exception as e:
            result[k] = {"error": str(e), "name": SYMBOLS[k]["name"]}
    return result

# ====================== الواجهة ======================
HTML = r'''<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>MD Khider International Market</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
:root {
  --bg: #0a0e17;
  --card: #121826;
  --border: #1e2a3a;
  --gold: #f0c14b;
  --text: #e8eef7;
  --muted: #8b9bb4;
  --green: #22c55e;
  --red: #ef4444;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Tahoma, sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  line-height: 1.5;
}
.header {
  background: linear-gradient(135deg, #0f172a, #1e293b);
  border-bottom: 1px solid var(--border);
  padding: 1rem 1.25rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  position: sticky;
  top: 0;
  z-index: 50;
}
.logo {
  display: flex;
  align-items: center;
  gap: 0.7rem;
}
.logo-icon {
  width: 42px; height: 42px;
  background: linear-gradient(135deg, #f0c14b, #d4a017);
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  font-weight: 800; font-size: 1rem; color: #111;
}
.logo h1 { font-size: 1.1rem; font-weight: 700; }
.logo span { font-size: 0.7rem; color: var(--muted); display: block; }
.btn {
  background: #2563eb;
  color: white;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 8px;
  font-size: 0.85rem;
  cursor: pointer;
}
.container { max-width: 1100px; margin: 0 auto; padding: 1.25rem; }
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 1.1rem;
  position: relative;
  overflow: hidden;
}
.card::before {
  content: "";
  position: absolute; top: 0; left: 0; right: 0; height: 3px;
}
.card.gold::before { background: linear-gradient(90deg, #f0c14b, #d4a017); }
.card.silver::before { background: linear-gradient(90deg, #c0c7d4, #8a94a6); }
.card.wti::before, .card.brent::before { background: linear-gradient(90deg, #ff8c42, #e85d04); }
.card-title { font-size: 0.9rem; color: var(--muted); margin-bottom: 0.3rem; }
.price { font-size: 1.7rem; font-weight: 700; letter-spacing: -0.5px; }
.change {
  display: inline-block;
  margin-top: 0.35rem;
  padding: 0.2rem 0.55rem;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 600;
}
.change.up { background: rgba(34,197,94,0.15); color: var(--green); }
.change.down { background: rgba(239,68,68,0.15); color: var(--red); }
.meta { font-size: 0.75rem; color: var(--muted); margin-top: 0.6rem; }
.signal {
  margin-top: 0.9rem;
  padding: 0.7rem;
  border-radius: 10px;
  background: rgba(0,0,0,0.25);
  border: 1px solid var(--border);
  font-size: 0.8rem;
}
.signal.bullish { border-color: rgba(34,197,94,0.4); background: rgba(34,197,94,0.08); }
.signal.bearish { border-color: rgba(239,68,68,0.4); background: rgba(239,68,68,0.08); }
.signal-title { font-weight: 600; margin-bottom: 0.3rem; }
.signal ul { list-style: none; color: var(--muted); font-size: 0.75rem; }
.signal li { margin: 0.15rem 0; }
.section { font-size: 1.05rem; font-weight: 600; margin: 1.5rem 0 0.8rem; }
.charts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1rem;
}
.chart-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 1rem;
}
.chart-card h3 { font-size: 0.9rem; color: var(--muted); margin-bottom: 0.6rem; }
.contact {
  margin-top: 2rem;
  padding: 1.25rem;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  text-align: center;
}
.contact h3 { margin-bottom: 0.8rem; font-size: 1rem; }
.contact a {
  display: inline-block;
  margin: 0.35rem 0.5rem;
  padding: 0.55rem 1.1rem;
  border-radius: 8px;
  text-decoration: none;
  font-weight: 600;
  font-size: 0.9rem;
}
.phone-btn { background: #1e293b; color: #e2e8f0; border: 1px solid var(--border); }
.wa-btn { background: #25d366; color: #fff; }
.note {
  margin-top: 1.5rem;
  padding: 0.9rem;
  background: rgba(239,68,68,0.08);
  border: 1px solid rgba(239,68,68,0.25);
  border-radius: 10px;
  font-size: 0.78rem;
  color: var(--muted);
  text-align: center;
}
.loading { text-align: center; padding: 3rem; color: var(--muted); }
.spinner {
  width: 36px; height: 36px;
  border: 3px solid var(--border);
  border-top-color: var(--gold);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 0 auto 1rem;
}
@keyframes spin { to { transform: rotate(360deg); } }
footer {
  text-align: center;
  padding: 1.5rem;
  color: var(--muted);
  font-size: 0.75rem;
  border-top: 1px solid var(--border);
  margin-top: 2rem;
}
@media (max-width: 500px) {
  .price { font-size: 1.45rem; }
  .logo h1 { font-size: 0.95rem; }
}
</style>
</head>
<body>
<header class="header">
  <div class="logo">
    <div class="logo-icon">MK</div>
    <div>
      <h1>MD Khider International Market</h1>
      <span>أسعار الذهب • الفضة • النفط</span>
    </div>
  </div>
  <button class="btn" onclick="loadData(true)">تحديث</button>
</header>

<main class="container">
  <div id="loading" class="loading">
    <div class="spinner"></div>
    <p>جاري جلب أحدث الأسعار...</p>
  </div>

  <div id="content" style="display:none">
    <div class="grid" id="cards"></div>
    <div class="section">الرسوم البيانية (آخر 20 يوم)</div>
    <div class="charts" id="charts"></div>
  </div>

  <div class="contact">
    <h3>للتواصل معنا</h3>
    <a class="phone-btn" href="tel:+256773395517">📞 +256 773 395 517</a>
    <a class="wa-btn" href="https://wa.me/250793902079" target="_blank">💬 واتساب +250 793 902 079</a>
  </div>

  <div class="note">
    ⚠️ تنويه هام: البيانات مستمدة من عقود الآجلة (Yahoo Finance) وقد تختلف قليلاً عن سعر الـ Spot الفوري.
    الإشارات الفنية تقديرية وليست نصيحة استثمارية. استخدم المعلومات على مسؤوليتك.
  </div>
</main>

<footer>
  MD Khider International Market © 2026 — للاستخدام الشخصي
</footer>

<script>
const charts = {};
function fmt(n, d=2) {
  if (n == null || isNaN(n)) return "—";
  return Number(n).toLocaleString("en-US", {minimumFractionDigits:d, maximumFractionDigits:d});
}

function render(data) {
  const cards = document.getElementById("cards");
  cards.innerHTML = "";
  const order = ["gold","silver","wti","brent"];
  order.forEach(k => {
    const d = data[k];
    if (!d || d.error) {
      cards.innerHTML += `<div class="card"><p>خطأ في ${k}</p></div>`;
      return;
    }
    const up = d.change >= 0;
    const sig = d.signal || {};
    let gramHtml = d.gram ? `<div class="meta">سعر الجرام ≈ ${fmt(d.gram)} دولار</div>` : "";
    cards.innerHTML += `
      <div class="card ${k}">
        <div class="card-title">${d.icon} ${d.name}</div>
        <div class="price">${fmt(d.price)}</div>
        <div class="meta">${d.unit}</div>
        <div>
          <span class="change ${up?'up':'down'}">
            ${up?'▲':'▼'} ${fmt(Math.abs(d.change))} (${fmt(d.change_pct)}%)
          </span>
        </div>
        ${gramHtml}
        <div class="meta">أعلى 3 أشهر: ${fmt(d.high)} | أدنى: ${fmt(d.low)}</div>
        <div class="signal ${sig.color||'neutral'}">
          <div class="signal-title">
            ${sig.color==='bullish'?'📈':sig.color==='bearish'?'📉':'➖'} 
            التوقع: <strong>${sig.text||'—'}</strong>
            <span style="opacity:0.7;font-size:0.75rem"> (ثقة ${sig.confidence||0}%)</span>
          </div>
          <ul>${(sig.details||[]).map(x=>`<li>• ${x}</li>`).join('')}</ul>
        </div>
      </div>`;
  });

  // Charts
  const chartsEl = document.getElementById("charts");
  chartsEl.innerHTML = "";
  const colors = {gold:"#f0c14b", silver:"#c0c7d4", wti:"#ff8c42", brent:"#e85d04"};
  order.forEach(k => {
    const d = data[k];
    if (!d || !d.chart) return;
    const id = "c-"+k;
    chartsEl.innerHTML += `<div class="chart-card"><h3>${d.icon} ${d.name}</h3><canvas id="${id}" height="160"></canvas></div>`;
    setTimeout(() => {
      if (charts[k]) charts[k].destroy();
      charts[k] = new Chart(document.getElementById(id), {
        type: "line",
        data: {
          labels: d.chart.dates,
          datasets: [{
            data: d.chart.prices,
            borderColor: colors[k],
            backgroundColor: colors[k]+"22",
            fill: true, tension: 0.3, pointRadius: 0, borderWidth: 2
          }]
        },
        options: {
          responsive: true,
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { color: "#8b9bb4", maxTicksLimit: 6 }, grid: { color: "#1e2a3a" } },
            y: { ticks: { color: "#8b9bb4" }, grid: { color: "#1e2a3a" } }
          }
        }
      });
    }, 30);
  });
}

async function loadData(force=false) {
  try {
    document.getElementById("loading").style.display = "block";
    document.getElementById("content").style.display = "none";
    const res = await fetch("/api/prices" + (force ? "?t="+Date.now() : ""));
    const data = await res.json();
    render(data);
    document.getElementById("loading").style.display = "none";
    document.getElementById("content").style.display = "block";
  } catch(e) {
    document.getElementById("loading").innerHTML = `<p style="color:#ef4444">خطأ: ${e.message}<br>حاول مرة أخرى بعد قليل</p>`;
  }
}
loadData();
setInterval(() => loadData(), 180000);
</script>
</body>
</html>
'''

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html") or self.path.startswith("/?"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))
            return

        if self.path.startswith("/api/prices"):
            try:
                data = fetch_all()
                body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
            return

        self.send_error(404)

    def log_message(self, fmt, *args):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]}")

def main():
    print("=" * 55)
    print("  MD Khider International Market v2")
    print("=" * 55)
    print(f"  Port: {PORT}")
    print(f"  Host: {HOST}")
    if os.environ.get("PORT"):
        print("  Running on cloud server (Render)")
    print("-" * 55)
    server = HTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()

if __name__ == "__main__":
    main()
