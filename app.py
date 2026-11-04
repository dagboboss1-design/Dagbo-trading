import os
import pandas as pd
import numpy as np
import yfinance as yf
from flask import Flask, render_template_string, jsonify

# 🔴 PASTE YOUR FINNHUB KEY HERE (Keep the quotes)
FINNHUB_KEY = "dbln3ahr01qpfa5madpgdbln3ahr01qpfa5madq0"

app = Flask(__name__)

PAIRS = ["XAUUSD","EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD","NZDUSD","USDCAD","BTCUSD","GBPJPY","EURJPY"]
YF_MAP = {
    "XAUUSD":"GC=F","EURUSD":"EURUSD=X","GBPUSD":"GBPUSD=X","USDJPY":"USDJPY=X",
    "USDCHF":"USDCHF=X","AUDUSD":"AUDUSD=X","NZDUSD":"NZDUSD=X","USDCAD":"USDCAD=X",
    "BTCUSD":"BTC-USD","GBPJPY":"GBPJPY=X","EURJPY":"EURJPY=X","DXY":"DX-Y.NYB"
}

# ---------- DATA ----------
def get_candles(pair, period="2d", interval="15m"):
    try:
        ticker = yf.Ticker(YF_MAP.get(pair, pair))
        hist = ticker.history(period=period, interval=interval)
        if not hist.empty:
            df = hist.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close"})[["open","high","low","close"]].tail(120)
            return df
    except: pass
    return pd.DataFrame()

def get_atr(df, period=14):
    if len(df) < period+2: return 0
    tr = pd.concat([(df["high"]-df["low"]), (df["high"]-df["close"].shift()).abs(), (df["low"]-df["close"].shift()).abs()], axis=1).max(axis=1)
    return float(tr.tail(period).mean())

# ---------- 4 ENGINES ----------
def engine_smc(df):
    if len(df) < 30: return {"engine":"SMC","direction":"NEUTRAL","confidence":0,"reasons":["No data"]}
    price = float(df["close"].iloc[-1])
    if price > float(df["high"].iloc[-10:].max()) * 0.999:
        return {"engine":"SMC","direction":"BUY","confidence":78,"reasons":["Bullish BOS - price break high, buyers in control"]}
    if price < float(df["low"].iloc[-10:].min()) * 1.001:
        return {"engine":"SMC","direction":"SELL","confidence":78,"reasons":["Bearish BOS - price break low, sellers in control"]}
    if price > float(df["close"].tail(20).mean()):
        return {"engine":"SMC","direction":"BUY","confidence":60,"reasons":["Price above 20-candle mean, bullish structure"]}
    return {"engine":"SMC","direction":"SELL","confidence":60,"reasons":["Price below 20-candle mean, bearish structure"]}

def engine_ict(df):
    if len(df) < 30: return {"engine":"ICT","direction":"NEUTRAL","confidence":0,"reasons":["No data"]}
    price = float(df["close"].iloc[-1])
    high_24 = float(df["high"].tail(24).max()); low_24 = float(df["low"].tail(24).min())
    if float(df["high"].iloc[-2]) >= high_24 and price < high_24:
        return {"engine":"ICT","direction":"SELL","confidence":85,"reasons":["Judas Swing: Swept high, closed back inside - trap buyers"]}
    if float(df["low"].iloc[-2]) <= low_24 and price > low_24:
        return {"engine":"ICT","direction":"BUY","confidence":85,"reasons":["Turtle Soup: Swept low, closed back inside - trap sellers"]}
    if price > float(df["close"].iloc[-3]):
        return {"engine":"ICT","direction":"BUY","confidence":62,"reasons":["Price pushing up from FVG, buyers active"]}
    return {"engine":"ICT","direction":"SELL","confidence":62,"reasons":["Price falling from FVG, sellers active"]}

def engine_pattern(df):
    if len(df) < 30: return {"engine":"Pattern","direction":"NEUTRAL","confidence":0,"reasons":["No data"]}
    last_high = float(df["high"].tail(10).max())
    prev_high = float(df["high"].iloc[-20:-10].max())
    last_low = float(df["low"].tail(10).min())
    prev_low = float(df["low"].iloc[-20:-10].min())
    if last_high > prev_high and last_low > prev_low:
        return {"engine":"Pattern","direction":"BUY","confidence":72,"reasons":["Pattern: Higher High + Higher Low - uptrend pattern"]}
    if last_high < prev_high and last_low < prev_low:
        return {"engine":"Pattern","direction":"SELL","confidence":72,"reasons":["Pattern: Lower High + Lower Low - downtrend pattern"]}
    if float(df["close"].iloc[-1]) > float(df["open"].iloc[-1]) and float(df["close"].iloc[-2]) < float(df["open"].iloc[-2]):
        return {"engine":"Pattern","direction":"BUY","confidence":68,"reasons":["Pattern: Bullish Engulfing candle"]}
    if float(df["close"].iloc[-1]) < float(df["open"].iloc[-1]) and float(df["close"].iloc[-2]) > float(df["open"].iloc[-2]):
        return {"engine":"Pattern","direction":"SELL","confidence":68,"reasons":["Pattern: Bearish Engulfing candle"]}
    return {"engine":"Pattern","direction":"NEUTRAL","confidence":45,"reasons":["No clear pattern"]}

def engine_indicator(df):
    if len(df) < 30: return {"engine":"Indicator","direction":"NEUTRAL","confidence":0,"reasons":["No data"]}
    closes = df["close"]
    ema20 = float(closes.ewm(span=20).mean().iloc[-1])
    ema50 = float(closes.ewm(span=50).mean().iloc[-1])
    price = float(closes.iloc[-1])
    delta = closes.diff()
    gain = delta.where(delta>0,0).rolling(14).mean()
    loss = (-delta.where(delta<0,0)).rolling(14).mean()
    rs = gain.iloc[-1] / (loss.iloc[-1] + 1e-9)
    rsi = 100 - (100/(1+rs))
    if price > ema20 and price > ema50 and rsi < 70:
        return {"engine":"Indicator","direction":"BUY","confidence":74,"reasons":[f"EMA: Price above EMA20/50, RSI {rsi:.0f} - bullish momentum"]}
    if price < ema20 and price < ema50 and rsi > 30:
        return {"engine":"Indicator","direction":"SELL","confidence":74,"reasons":[f"EMA: Price below EMA20/50, RSI {rsi:.0f} - bearish momentum"]}
    return {"engine":"Indicator","direction":"NEUTRAL","confidence":50,"reasons":[f"RSI {rsi:.0f} - mixed, no clear momentum"]}

def fundamental_check(pair):
    try:
        dxy = get_candles("DXY", period="2d", interval="1h")
        if not dxy.empty:
            dxy_up = float(dxy["close"].iloc[-1]) > float(dxy["close"].iloc[-5])
            usd_pairs = ["XAUUSD","EURUSD","GBPUSD","AUDUSD","NZDUSD"]
            if pair in usd_pairs:
                return {"direction":"SELL" if dxy_up else "BUY","score":75,"reason":f"DXY {'strong - USD up, so SELL '+pair if dxy_up else 'weak - USD down, so BUY '+pair}"}
            if pair in ["USDJPY","USDCAD"]:
                return {"direction":"BUY" if dxy_up else "SELL","score":75,"reason":f"DXY {'strong - BUY '+pair if dxy_up else 'weak - SELL '+pair}"}
    except: pass
    return {"direction":"NEUTRAL","score":50,"reason":"DXY neutral"}

def position_check(df):
    if len(df) < 30: return {"direction":"NEUTRAL","score":50,"reason":"No position data"}
    price = float(df["close"].iloc[-1])
    high_24 = float(df["high"].tail(24).max()); low_24 = float(df["low"].tail(24).min())
    dist_high = abs(price - high_24) / (high_24 - low_24 + 1e-9)
    dist_low = abs(price - low_24) / (high_24 - low_24 + 1e-9)
    if dist_low < 0.15:
        return {"direction":"BUY","score":80,"reason":"Position: Price near liquidity low, big buyers dey there, retail sellers go trap"}
    if dist_high < 0.15:
        return {"direction":"SELL","score":80,"reason":"Position: Price near liquidity high, big sellers dey there, retail buyers go trap"}
    return {"direction":"NEUTRAL","score":55,"reason":"Position: Price for middle, no clear big money zone"}

def scan_pair(pair):
    df15 = get_candles(pair, period="2d", interval="15m")
    df1h = get_candles(pair, period="5d", interval="60m")
    df4h = get_candles(pair, period="1mo", interval="60m")
    dfD = get_candles(pair, period="3mo", interval="1d")
    if df15.empty: return None

    tf_results = {}
    for name, df in [("H15",df15),("H1",df1h),("H4",df4h),("Daily",dfD)]:
        if not df.empty:
            s = engine_smc(df)
            tf_results[name] = s["direction"]

    e1 = engine_smc(df15); e2 = engine_ict(df15); e3 = engine_pattern(df15); e4 = engine_indicator(df15)
    engines = [e1,e2,e3,e4]
    buy_votes = sum(1 for e in engines if e["direction"]=="BUY")
    sell_votes = sum(1 for e in engines if e["direction"]=="SELL")

    if buy_votes >= 3: tech_dir = "BUY"
    elif sell_votes >= 3: tech_dir = "SELL"
    else: tech_dir = "NEUTRAL"

    fund = fundamental_check(pair)
    pos = position_check(df15)

    tech_score = 80 if tech_dir != "NEUTRAL" else 0
    fund_score = fund["score"] if fund["direction"]==tech_dir else 30
    pos_score = pos["score"] if pos["direction"]==tech_dir else 30
    final_rate = int(tech_score*0.4 + fund_score*0.3 + pos_score*0.3) if tech_dir!="NEUTRAL" else 0

    if tech_dir=="NEUTRAL" or final_rate < 70:
        return {"pair":pair,"direction":"NEUTRAL","confidence":final_rate,"reasons":["Wait - no trade, concepts no agree"],"tech":tech_dir,"fund":fund["direction"],"pos":pos["direction"],"tf":tf_results}

    atr = get_atr(df15)
    if atr==0: atr = float(df15["close"].iloc[-1])*0.002
    price = float(df15["close"].iloc[-1])
    if tech_dir=="BUY":
        entry = price; sl = price - atr*1.5; tp1 = price + atr*1.5; tp2 = price + atr*3.0
    else:
        entry = price; sl = price + atr*1.5; tp1 = price - atr*1.5; tp2 = price - atr*3.0

    all_reasons = [e["reasons"][0] for e in engines if e["direction"]==tech_dir] + [fund["reason"], pos["reason"]]
    return {
        "pair":pair,"direction":tech_dir,"confidence":final_rate,
        "entry":round(entry,5),"sl":round(sl,5),"tp1":round(tp1,5),"tp2":round(tp2,5),
        "tech":tech_dir,"fund":fund["direction"],"pos":pos["direction"],
        "tf":tf_results,"reasons":all_reasons,
        "engines":{"SMC":e1["direction"],"ICT":e2["direction"],"Pattern":e3["direction"],"Indicator":e4["direction"]}
    }

HTML = """
<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>body{background:#0A0E1A;color:#E6EDF7;font-family:sans-serif;padding:16px;}
.card{background:#141A2A;padding:18px;border-radius:15px;margin-bottom:12px;border:1px solid #00E676;}
button{background:#00E676;color:#000;padding:15px;border:none;border-radius:10px;font-weight:bold;width:100%;font-size:16px;}
#chat{margin-top:16px;white-space:pre-wrap;font-size:14px;line-height:1.6;background:#141A2A;padding:16px;border-radius:12px;}
</style></head>
<body><h1>⚡ Spark News Trading</h1>
<div class="card"><h2>⚡ Swing Scanner</h2><p>Scan 11 pairs • 4 Engines • Multi-TF • Fundamental + Position</p></div>
<button onclick="scan()">SCAN NOW - ALL PAIRS</button><div id="chat">Press SCAN when ready.</div>
<script>
async function scan(){
  document.getElementById('chat').innerText = "🔍 Scanning 11 pairs... 4 engines... DXY... Position... Wait small...";
  try {
    let res = await fetch('/api/scan');
    let data = await res.json();
    if(!data.ok){ document.getElementById('chat').innerText = "⏳ WAIT - No trade now.\\n\\n" + (data.all||[]).map(r=>r.pair+": "+r.direction+" ("+r.confidence+"%)").join("\\n"); return; }
    let r = data.result;
    let t = "✅ BEST SETUP FOUND\\n\\n";
    t += "Pair: " + r.pair + "\\nDirection: " + r.direction + "\\nWin Rate: " + r.confidence + "%\\n\\n";
    t += "🎯 ENTRY: " + r.entry + "\\n🛑 SL: " + r.sl + "\\n✅ TP1: " + r.tp1 + "\\n✅ TP2: " + r.tp2 + "\\n\\n";
    t += "Technical: " + r.tech + " | Fundamental: " + r.fund + " | Position: " + r.pos + "\\n";
    t += "Engines: SMC " + r.engines.SMC + " | ICT " + r.engines.ICT + " | Pattern " + r.engines.Pattern + " | Indicator " + r.engines.Indicator + "\\n";
    t += "Timeframes: " + JSON.stringify(r.tf) + "\\n\\nWhy:\\n- " + r.reasons.join("\\n- ");
    t += "\\n\\n👉 Confirmation: Wait for price reach Entry, then check H15 candle close for your direction before you enter.";
    document.getElementById('chat').innerText = t;
  } catch(e){ document.getElementById('chat').innerText = "Error: " + e.message; }
}
</script></body></html>
"""

@app.route("/")
def home(): return render_template_string(HTML)

@app.route("/api/scan")
def api_scan():
    best = None
    all_res = []
    for p in PAIRS:
        r = scan_pair(p)
        if r:
            all_res.append(r)
            if r["direction"] != "NEUTRAL" and (best is None or r["confidence"] > best["confidence"]):
                best = r
    if best:
        return jsonify({"ok": True, "result": best, "all": all_res})
    return jsonify({"ok": False, "msg": "No trade setup right now", "all": all_res})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
