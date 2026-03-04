# engine.py — v4: Klickbare Email-Links, Signal-Klassifikation, Futures

import yfinance as yf
import pandas as pd
import numpy as np
import smtplib
import time
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from database import get_currency

APP_URL = "https://stockupdate-65qjxum6gq2gpjpr5exqfd.streamlit.app"


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL KLASSIFIKATION
# ─────────────────────────────────────────────────────────────────────────────

def classify_signal(stoch_rsi=None, stoch_fast=None, stoch_slow=None, cci=None) -> dict:
    os_hits = ob_hits = 0
    if stoch_rsi  is not None:
        if stoch_rsi  < 0.15:  os_hits += 2
        elif stoch_rsi  > 0.85: ob_hits += 2
    if stoch_fast is not None:
        if stoch_fast < 20:    os_hits += 1
        elif stoch_fast > 80:  ob_hits += 1
    if stoch_slow is not None:
        if stoch_slow < 25:    os_hits += 1
        elif stoch_slow > 75:  ob_hits += 1
    if cci is not None:
        if cci < -100:  os_hits += 1
        elif cci > 100: ob_hits += 1
    if os_hits >= 2 and os_hits > ob_hits:
        return {"label":"OVERSOLD",   "emoji":"🟢","color":"#1a9e3f","bg":"#e8f9ed","short":"OS"}
    elif ob_hits >= 2 and ob_hits > os_hits:
        return {"label":"OVERBOUGHT", "emoji":"🔴","color":"#c0392b","bg":"#fdecea","short":"OB"}
    else:
        return {"label":"NEUTRAL",    "emoji":"⚪","color":"#7f8c8d","bg":"#f4f4f4","short":"NT"}


# ─────────────────────────────────────────────────────────────────────────────
# SCANNER ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def get_analysis(ticker: str, retries: int = 2) -> dict | None:
    for attempt in range(retries + 1):
        try:
            stock = yf.Ticker(ticker)
            df    = stock.history(period="2y", auto_adjust=False)
            if df.empty or len(df) < 50:
                return None

            has_70  = len(df) >= 70
            has_200 = len(df) >= 200
            rsi_w   = 70 if has_70 else 14

            delta = df['Close'].diff()
            gain  = delta.where(delta > 0, 0.0).rolling(rsi_w).mean()
            loss  = (-delta.where(delta < 0, 0.0)).rolling(rsi_w).mean()
            df['RSI'] = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))
            rsi_r     = (df['RSI'].rolling(rsi_w).max() - df['RSI'].rolling(rsi_w).min()).replace(0, np.nan)
            df['StochRSI'] = (df['RSI'] - df['RSI'].rolling(rsi_w).min()) / rsi_r

            slow_w = 200 if has_200 else 70
            hl_f   = (df['High'].rolling(70).max() - df['Low'].rolling(70).min()).replace(0, np.nan)
            df['Stoch_Fast'] = 100 * (df['Close'] - df['Low'].rolling(70).min()) / hl_f
            hl_s   = (df['High'].rolling(slow_w).max() - df['Low'].rolling(slow_w).min()).replace(0, np.nan)
            df['Stoch_Slow'] = 100 * (df['Close'] - df['Low'].rolling(slow_w).min()) / hl_s

            tp   = (df['High'] + df['Low'] + df['Close']) / 3
            mdev = tp.rolling(40).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
            df['CCI'] = (tp - tp.rolling(40).mean()) / (0.015 * mdev.replace(0, np.nan))

            def _s(v, d=3):
                try:
                    f = float(v); return round(f, d) if np.isfinite(f) else None
                except: return None

            sv = _s(df['StochRSI'].iloc[-1])
            sf = _s(df['Stoch_Fast'].iloc[-1], 1)
            ss = _s(df['Stoch_Slow'].iloc[-1], 1)
            cv = _s(df['CCI'].iloc[-1], 1)

            score = 0
            if sv and 0 < sv < 0.1:                        score += 1
            if sf and ss and sf < 10 and ss < 15:          score += 1
            if cv and cv > -100:                           score += 1

            sig = classify_signal(sv, sf, ss, cv)

            inf = {}
            try: inf = stock.info or {}
            except: pass
            cur = get_currency(ticker)
            div = inf.get('dividendYield')

            return {
                "Ticker":     ticker,
                "Name":       inf.get('shortName', ticker)[:20],
                "Signal":     f"{sig['emoji']} {sig['label']}",
                "Preis":      f"{round(float(df['Close'].iloc[-1]),2)} {cur}",
                "Währung":    cur,
                "StochRSI":   sv,
                "CCI":        cv,
                "Stoch_Fast": sf,
                "Stoch_Slow": ss,
                "Score":      score,
                "Div":        f"{round(div*100,2)}%" if isinstance(div,(int,float)) and div>0 else "0%",
                "KGV":        round(inf.get('trailingPE',0),1) if inf.get('trailingPE') else "N/A",
            }
        except Exception as e:
            if attempt < retries: time.sleep(1.0)
            else: print(f"[engine] {ticker}: {e}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# FUTURES
# ─────────────────────────────────────────────────────────────────────────────

FUTURES_TICKERS = {
    "CL=F":  {"name":"Crude Oil (WTI)",     "group":"Energie",    "unit":"$/bbl"},
    "BZ=F":  {"name":"Brent Crude Oil",     "group":"Energie",    "unit":"$/bbl"},
    "NG=F":  {"name":"Natural Gas",         "group":"Energie",    "unit":"$/MMBtu"},
    "RB=F":  {"name":"RBOB Gasoline",       "group":"Energie",    "unit":"$/gal"},
    "HO=F":  {"name":"Heating Oil",         "group":"Energie",    "unit":"$/gal"},
    "GC=F":  {"name":"Gold",                "group":"Edelmetalle","unit":"$/oz"},
    "SI=F":  {"name":"Silber",              "group":"Edelmetalle","unit":"$/oz"},
    "PL=F":  {"name":"Platin",              "group":"Edelmetalle","unit":"$/oz"},
    "PA=F":  {"name":"Palladium",           "group":"Edelmetalle","unit":"$/oz"},
    "HG=F":  {"name":"Kupfer",              "group":"Edelmetalle","unit":"$/lb"},
    "ZC=F":  {"name":"Mais (Corn)",         "group":"Agrar",      "unit":"¢/bu"},
    "ZW=F":  {"name":"Weizen (Wheat)",      "group":"Agrar",      "unit":"¢/bu"},
    "ZS=F":  {"name":"Soja (Soybeans)",     "group":"Agrar",      "unit":"¢/bu"},
    "KC=F":  {"name":"Kaffee (Coffee)",     "group":"Agrar",      "unit":"¢/lb"},
    "CT=F":  {"name":"Baumwolle (Cotton)",  "group":"Agrar",      "unit":"¢/lb"},
    "SB=F":  {"name":"Zucker (Sugar)",      "group":"Agrar",      "unit":"¢/lb"},
    "CC=F":  {"name":"Kakao (Cocoa)",       "group":"Agrar",      "unit":"$/t"},
    "ES=F":  {"name":"S&P 500 Future",      "group":"Index",      "unit":"Pkt"},
    "NQ=F":  {"name":"NASDAQ 100 Future",   "group":"Index",      "unit":"Pkt"},
    "YM=F":  {"name":"Dow Jones Future",    "group":"Index",      "unit":"Pkt"},
    "RTY=F": {"name":"Russell 2000 Future", "group":"Index",      "unit":"Pkt"},
    "6E=F":  {"name":"EUR/USD Future",      "group":"FX",         "unit":""},
    "6J=F":  {"name":"JPY/USD Future",      "group":"FX",         "unit":""},
    "6B=F":  {"name":"GBP/USD Future",      "group":"FX",         "unit":""},
    "BTC=F": {"name":"Bitcoin Future",      "group":"Krypto",     "unit":"$"},
    "ETH=F": {"name":"Ethereum Future",     "group":"Krypto",     "unit":"$"},
}


def get_futures_analysis(ticker: str) -> dict | None:
    meta = FUTURES_TICKERS.get(ticker, {"name": ticker, "group": "Sonstige", "unit": ""})
    try:
        stock = yf.Ticker(ticker)
        df    = stock.history(period="1y", auto_adjust=False)
        if df.empty or len(df) < 30:
            return None

        rsi_w = 14
        delta = df['Close'].diff()
        gain  = delta.where(delta > 0, 0.0).rolling(rsi_w).mean()
        loss  = (-delta.where(delta < 0, 0.0)).rolling(rsi_w).mean()
        df['RSI'] = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))
        rsi_r     = (df['RSI'].rolling(rsi_w).max() - df['RSI'].rolling(rsi_w).min()).replace(0, np.nan)
        df['StochRSI'] = (df['RSI'] - df['RSI'].rolling(rsi_w).min()) / rsi_r

        w14 = min(14, len(df)-1)
        hl  = (df['High'].rolling(w14).max() - df['Low'].rolling(w14).min()).replace(0, np.nan)
        df['Stoch_K'] = 100 * (df['Close'] - df['Low'].rolling(w14).min()) / hl
        df['Stoch_D'] = df['Stoch_K'].rolling(3).mean()

        tp   = (df['High'] + df['Low'] + df['Close']) / 3
        mdev = tp.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
        df['CCI'] = (tp - tp.rolling(20).mean()) / (0.015 * mdev.replace(0, np.nan))

        bb_w = min(50, len(df)-1)
        df['EMA50']    = df['Close'].ewm(span=bb_w, adjust=False).mean()
        std            = df['Close'].rolling(bb_w).std()
        df['BB_Upper'] = df['EMA50'] + 2 * std
        df['BB_Lower'] = df['EMA50'] - 2 * std

        w20 = min(20, len(df)-1)
        df['SMA20']   = df['Close'].rolling(w20).mean()
        df['Z_Score'] = (df['Close'] - df['SMA20']) / df['Close'].rolling(w20).std().replace(0, np.nan)
        df['RVOL']    = df['Volume'] / df['Volume'].rolling(w20).mean().replace(0, np.nan)

        def _s(v, d=2):
            try:
                f = float(v); return round(f, d) if np.isfinite(f) else None
            except: return None

        price  = _s(df['Close'].iloc[-1])
        sr     = _s(df['StochRSI'].iloc[-1], 3)
        sk     = _s(df['Stoch_K'].iloc[-1], 1)
        sd     = _s(df['Stoch_D'].iloc[-1], 1)
        cci    = _s(df['CCI'].iloc[-1], 1)
        rsi_v  = _s(df['RSI'].iloc[-1], 1)
        zscore = _s(df['Z_Score'].iloc[-1], 2)
        rvol   = _s(df['RVOL'].iloc[-1], 2)

        score = 0
        if sr  and 0 < sr  < 0.2:  score += 1
        if sk  and sk  < 25:        score += 1
        if cci and cci < -80:       score += 1
        if rsi_v and rsi_v < 35:    score += 1

        sig   = classify_signal(sr, sk, sd, cci)
        df_1y = df.tail(252)

        return {
            "Ticker":   ticker, "Name": meta["name"], "Gruppe": meta["group"],
            "Einheit":  meta["unit"], "Signal": f"{sig['emoji']} {sig['label']}",
            "Sig_Data": sig, "Preis": price,
            "52W_Hoch": _s(df_1y['High'].max()), "52W_Tief": _s(df_1y['Low'].min()),
            "Perf_1W":  _s(((df['Close'].iloc[-1]/df['Close'].iloc[-5])-1)*100 if len(df)>=5 else None, 2),
            "Perf_1M":  _s(((df['Close'].iloc[-1]/df['Close'].iloc[-22])-1)*100 if len(df)>=22 else None, 2),
            "RSI": rsi_v, "StochRSI": sr, "Stoch_K": sk, "Stoch_D": sd,
            "CCI": cci, "Z_Score": zscore, "RVOL": rvol, "Score": score, "df": df,
        }
    except Exception as e:
        print(f"[futures] {ticker}: {e}")
        return None


def get_all_futures_groups() -> list:
    seen, r = set(), []
    for v in FUTURES_TICKERS.values():
        if v["group"] not in seen:
            seen.add(v["group"]); r.append(v["group"])
    return r


def get_futures_by_group(group: str) -> list:
    return [k for k, v in FUTURES_TICKERS.items() if v["group"] == group]


# ─────────────────────────────────────────────────────────────────────────────
# EMAIL — mit klickbaren Ticker-Links und App-Header-Link
# ─────────────────────────────────────────────────────────────────────────────

def send_mail_report(df_results, password, total_scanned=0, success_count=0, failed_count=0) -> str:
    try:
        sender, receiver = "daily@in8invest.com", "j.jendraszek@yahoo.de"
        signals = pd.DataFrame()
        if not df_results.empty and 'Score' in df_results.columns:
            signals = df_results[df_results['Score'] > 1].sort_values("Score", ascending=False)

        def _badge(v, low, high, invert=False):
            if v is None: return "<td style='color:#aaa;text-align:center'>N/A</td>"
            try:
                fv = float(v)
                if fv <= low:
                    bg,fc,t = ("#e6f9ee","#1a9e3f","OS") if not invert else ("#fee2e2","#c0392b","OB")
                elif fv >= high:
                    bg,fc,t = ("#fee2e2","#c0392b","OB") if not invert else ("#e6f9ee","#1a9e3f","OS")
                else:
                    bg,fc,t = "#f8f8f8","#666","–"
                b   = f"<span style='background:{fc};color:#fff;padding:1px 6px;border-radius:4px;font-size:10px;font-weight:700'>{t}</span>"
                fmt = "{:.3f}" if abs(fv) < 10 else "{:.1f}"
                return f"<td style='background:{bg};text-align:center;padding:9px 6px'>{b}<br><span style='font-size:11px;color:#444'>{fmt.format(fv)}</span></td>"
            except: return f"<td style='text-align:center'>{v}</td>"

        def _sig_cell(row):
            sig = classify_signal(row.get('StochRSI'), row.get('Stoch_Fast'), row.get('Stoch_Slow'), row.get('CCI'))
            return (f"<td style='text-align:center'>"
                    f"<span style='background:{sig['color']};color:#fff;padding:4px 10px;"
                    f"border-radius:14px;font-size:11px;font-weight:700;white-space:nowrap'>"
                    f"{sig['emoji']} {sig['label']}</span></td>")

        def _ticker_link(ticker, name):
            # Deep-link: ?ticker=ALV.DE öffnet direkt Detail-Analyse
            url = f"{APP_URL}/?ticker={ticker}"
            return (f"<td style='padding:9px 8px'>"
                    f"<a href='{url}' style='color:#3b82f6;font-weight:700;text-decoration:none;font-size:13px'>{ticker}</a>"
                    f"<br><span style='color:#888;font-size:11px'>{name}</span></td>")

        sc_colors = {3:"#1a9e3f",2:"#f39c12",1:"#7f8c8d"}
        rows = ""
        for _, r in signals.iterrows():
            sc   = int(r.get('Score',0))
            sc_c = sc_colors.get(sc,"#999")
            rows += f"""<tr style='border-bottom:1px solid #f0f0f0'>
              {_ticker_link(r.get('Ticker',''), r.get('Name',''))}
              {_sig_cell(r)}
              <td style='text-align:right;padding:9px 8px;font-weight:700;font-size:13px'>{r.get('Preis','')}</td>
              {_badge(r.get('StochRSI'),0.15,0.85)}
              {_badge(r.get('Stoch_Fast'),20,80)}
              {_badge(r.get('Stoch_Slow'),25,75)}
              {_badge(r.get('CCI'),-100,100,invert=True)}
              <td style='text-align:center;padding:9px 8px'>
                <span style='background:{sc_c};color:#fff;padding:3px 10px;border-radius:12px;font-weight:700;font-size:12px'>{sc}/3</span>
              </td>
              <td style='text-align:center;color:#666;font-size:12px;padding:9px 8px'>{r.get('Div','')}</td>
              <td style='text-align:center;color:#666;font-size:12px;padding:9px 8px'>{r.get('KGV','')}</td>
            </tr>"""

        tbl = f"""<table width="100%" cellpadding="0" cellspacing="0"
            style="border-collapse:collapse;font-size:12px;font-family:'Segoe UI',Arial,sans-serif">
          <thead>
            <tr style="background:#1e293b">
              <th style="color:#94a3b8;padding:11px 8px;text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.8px;font-weight:600">Ticker / Name</th>
              <th style="color:#94a3b8;padding:11px 8px;text-align:center;font-size:10px;text-transform:uppercase;letter-spacing:.8px;font-weight:600">Signal</th>
              <th style="color:#94a3b8;padding:11px 8px;text-align:right;font-size:10px;text-transform:uppercase;letter-spacing:.8px;font-weight:600">Preis</th>
              <th style="color:#94a3b8;padding:11px 8px;text-align:center;font-size:10px;text-transform:uppercase;letter-spacing:.8px;font-weight:600">StochRSI</th>
              <th style="color:#94a3b8;padding:11px 8px;text-align:center;font-size:10px;text-transform:uppercase;letter-spacing:.8px;font-weight:600">Stoch F</th>
              <th style="color:#94a3b8;padding:11px 8px;text-align:center;font-size:10px;text-transform:uppercase;letter-spacing:.8px;font-weight:600">Stoch S</th>
              <th style="color:#94a3b8;padding:11px 8px;text-align:center;font-size:10px;text-transform:uppercase;letter-spacing:.8px;font-weight:600">CCI</th>
              <th style="color:#94a3b8;padding:11px 8px;text-align:center;font-size:10px;text-transform:uppercase;letter-spacing:.8px;font-weight:600">Score</th>
              <th style="color:#94a3b8;padding:11px 8px;text-align:center;font-size:10px;text-transform:uppercase;letter-spacing:.8px;font-weight:600">Div</th>
              <th style="color:#94a3b8;padding:11px 8px;text-align:center;font-size:10px;text-transform:uppercase;letter-spacing:.8px;font-weight:600">KGV</th>
            </tr>
          </thead>
          <tbody>{rows if rows else "<tr><td colspan='10' style='text-align:center;padding:24px;color:#aaa;font-style:italic'>Keine Signale mit Score &gt; 1 gefunden.</td></tr>"}</tbody>
        </table>""" 

        now = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")

        body = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:'Segoe UI',Arial,sans-serif">
<div style="max-width:880px;margin:0 auto;padding:20px 16px">

  <!-- HEADER mit App-Link -->
  <div style="background:linear-gradient(135deg,#0f172a 0%,#1e293b 60%,#0f2744 100%);
              border-radius:16px;padding:28px 32px;margin-bottom:16px;
              border:1px solid #334155">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td>
        <div style="font-size:24px;font-weight:900;color:#fff;letter-spacing:.5px">
          📊 <span style="color:#38bdf8">In8</span>Invest
        </div>
        <div style="color:#94a3b8;font-size:13px;margin-top:5px">
          Daily Strategy Report &nbsp;·&nbsp; {now}
        </div>
      </td>
      <td style="text-align:right;vertical-align:middle">
        <a href="{APP_URL}" style="background:#3b82f6;color:#fff;padding:10px 20px;
           border-radius:8px;text-decoration:none;font-weight:700;font-size:13px;
           display:inline-block">
          📱 App öffnen →
        </a>
      </td>
    </tr></table>
  </div>

  <!-- STATISTIK-KACHELN -->
  <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:16px">
    <tr>
      <td width="25%" style="padding:0 6px 0 0">
        <div style="background:#fff;border-radius:12px;padding:20px;text-align:center;
                    box-shadow:0 1px 6px rgba(0,0,0,.08);border-top:3px solid #3b82f6">
          <div style="font-size:34px;font-weight:900;color:#3b82f6">{total_scanned}</div>
          <div style="font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:1px;margin-top:4px">Geprüft</div>
        </div>
      </td>
      <td width="25%" style="padding:0 6px">
        <div style="background:#fff;border-radius:12px;padding:20px;text-align:center;
                    box-shadow:0 1px 6px rgba(0,0,0,.08);border-top:3px solid #1a9e3f">
          <div style="font-size:34px;font-weight:900;color:#1a9e3f">{success_count}</div>
          <div style="font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:1px;margin-top:4px">Erfolgreich</div>
        </div>
      </td>
      <td width="25%" style="padding:0 6px">
        <div style="background:#fff;border-radius:12px;padding:20px;text-align:center;
                    box-shadow:0 1px 6px rgba(0,0,0,.08);border-top:3px solid #e74c3c">
          <div style="font-size:34px;font-weight:900;color:#e74c3c">{failed_count}</div>
          <div style="font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:1px;margin-top:4px">Fehler</div>
        </div>
      </td>
      <td width="25%" style="padding:0 0 0 6px">
        <div style="background:#fff;border-radius:12px;padding:20px;text-align:center;
                    box-shadow:0 1px 6px rgba(0,0,0,.08);border-top:3px solid #f39c12">
          <div style="font-size:34px;font-weight:900;color:#f39c12">{len(signals)}</div>
          <div style="font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:1px;margin-top:4px">Signale</div>
        </div>
      </td>
    </tr>
  </table>

  <!-- KRITERIEN-BOX -->
  <div style="background:#fffbeb;border-left:4px solid #f59e0b;border-radius:0 10px 10px 0;
              padding:12px 16px;margin-bottom:16px;font-size:12px;color:#78350f">
    <b>Scan-Kriterien:</b>
    StochRSI(70) &lt; 0.1 &nbsp;|&nbsp; Stoch Fast(70) &lt; 10 &amp; Slow(200) &lt; 15 &nbsp;|&nbsp; CCI(40) &gt; −100
    <br>
    <b>Legende:</b> &nbsp;
    <span style="background:#1a9e3f;color:#fff;padding:1px 7px;border-radius:4px;font-size:10px;font-weight:700">OS</span> Oversold &nbsp;
    <span style="background:#c0392b;color:#fff;padding:1px 7px;border-radius:4px;font-size:10px;font-weight:700">OB</span> Overbought &nbsp;
    <span style="background:#7f8c8d;color:#fff;padding:1px 7px;border-radius:4px;font-size:10px;font-weight:700">–</span> Neutral &nbsp;·&nbsp;
    <i>Ticker anklicken → öffnet Detail-Analyse in der App</i>
  </div>

  <!-- SIGNALE-TABELLE -->
  <div style="background:#fff;border-radius:14px;overflow:hidden;
              box-shadow:0 2px 16px rgba(0,0,0,.09);margin-bottom:16px">
    <div style="padding:20px 24px 14px;border-bottom:1px solid #f1f5f9">
      <span style="font-size:17px;font-weight:800;color:#0f172a">🎯 Top Signale</span>
      <span style="background:#f1f5f9;color:#64748b;padding:3px 10px;border-radius:8px;
                   font-size:12px;font-weight:600;margin-left:10px">Score ≥ 2</span>
    </div>
    <div style="overflow-x:auto">
      {tbl}
    </div>
  </div>

  <!-- FOOTER -->
  <div style="text-align:center;color:#94a3b8;font-size:11px;padding:12px 0 20px">
    In8Invest Scanner &nbsp;·&nbsp; Automatisch generiert &nbsp;·&nbsp;
    <a href="{APP_URL}" style="color:#3b82f6;text-decoration:none">stockupdate.streamlit.app</a>
  </div>

</div></body></html>"""

        msg = MIMEMultipart()
        msg['Subject'] = f"📊 In8Invest | {len(signals)} Signale | {now}"
        msg['From']    = sender
        msg['To']      = receiver
        msg.attach(MIMEText(body, 'html'))

        with smtplib.SMTP_SSL("w01a1dc3.kasserver.com", 465) as s:
            s.login(sender, password)
            s.sendmail(sender, receiver, msg.as_string())
        return "✅ Mail erfolgreich versendet"
    except Exception as e:
        return f"❌ Fehler: {e}"
