# engine.py — v3: Signal-Klassifikation OVERSOLD/OVERBOUGHT/NEUTRAL + Futures + Email

import yfinance as yf
import pandas as pd
import numpy as np
import smtplib
import time
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from database import get_currency


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL KLASSIFIKATION
# ─────────────────────────────────────────────────────────────────────────────

def classify_signal(stoch_rsi=None, stoch_fast=None, stoch_slow=None, cci=None) -> dict:
    """OVERSOLD / OVERBOUGHT / NEUTRAL mit Farb-Metadaten."""
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
# SCANNER ENGINE (Aktien)
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

            rsi_r = (df['RSI'].rolling(rsi_w).max() - df['RSI'].rolling(rsi_w).min()).replace(0, np.nan)
            df['StochRSI'] = (df['RSI'] - df['RSI'].rolling(rsi_w).min()) / rsi_r

            slow_w  = 200 if has_200 else 70
            hl_f    = (df['High'].rolling(70).max() - df['Low'].rolling(70).min()).replace(0, np.nan)
            df['Stoch_Fast'] = 100 * (df['Close'] - df['Low'].rolling(70).min()) / hl_f
            hl_s    = (df['High'].rolling(slow_w).max() - df['Low'].rolling(slow_w).min()).replace(0, np.nan)
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
            if sv and 0 < sv < 0.1:                          score += 1
            if sf and ss and sf < 10 and ss < 15:            score += 1
            if cv and cv > -100:                             score += 1

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
# FUTURES (Rohstoffe, Energie, Index-Futures)
# ─────────────────────────────────────────────────────────────────────────────

FUTURES_TICKERS = {
    "CL=F":   {"name":"Crude Oil (WTI)",     "group":"Energie",   "unit":"$/bbl"},
    "BZ=F":   {"name":"Brent Crude Oil",     "group":"Energie",   "unit":"$/bbl"},
    "NG=F":   {"name":"Natural Gas",         "group":"Energie",   "unit":"$/MMBtu"},
    "RB=F":   {"name":"RBOB Gasoline",       "group":"Energie",   "unit":"$/gal"},
    "HO=F":   {"name":"Heating Oil",         "group":"Energie",   "unit":"$/gal"},
    "GC=F":   {"name":"Gold",                "group":"Edelmetalle","unit":"$/oz"},
    "SI=F":   {"name":"Silber",              "group":"Edelmetalle","unit":"$/oz"},
    "PL=F":   {"name":"Platin",              "group":"Edelmetalle","unit":"$/oz"},
    "PA=F":   {"name":"Palladium",           "group":"Edelmetalle","unit":"$/oz"},
    "HG=F":   {"name":"Kupfer",              "group":"Edelmetalle","unit":"$/lb"},
    "ZC=F":   {"name":"Mais (Corn)",         "group":"Agrar",     "unit":"¢/bu"},
    "ZW=F":   {"name":"Weizen (Wheat)",      "group":"Agrar",     "unit":"¢/bu"},
    "ZS=F":   {"name":"Soja (Soybeans)",     "group":"Agrar",     "unit":"¢/bu"},
    "KC=F":   {"name":"Kaffee (Coffee)",     "group":"Agrar",     "unit":"¢/lb"},
    "CT=F":   {"name":"Baumwolle (Cotton)",  "group":"Agrar",     "unit":"¢/lb"},
    "SB=F":   {"name":"Zucker (Sugar)",      "group":"Agrar",     "unit":"¢/lb"},
    "CC=F":   {"name":"Kakao (Cocoa)",       "group":"Agrar",     "unit":"$/t"},
    "ES=F":   {"name":"S&P 500 Future",      "group":"Index",     "unit":"Pkt"},
    "NQ=F":   {"name":"NASDAQ 100 Future",   "group":"Index",     "unit":"Pkt"},
    "YM=F":   {"name":"Dow Jones Future",    "group":"Index",     "unit":"Pkt"},
    "RTY=F":  {"name":"Russell 2000 Future", "group":"Index",     "unit":"Pkt"},
    "6E=F":   {"name":"EUR/USD Future",      "group":"FX",        "unit":""},
    "6J=F":   {"name":"JPY/USD Future",      "group":"FX",        "unit":""},
    "6B=F":   {"name":"GBP/USD Future",      "group":"FX",        "unit":""},
    "BTC=F":  {"name":"Bitcoin Future",      "group":"Krypto",    "unit":"$"},
    "ETH=F":  {"name":"Ethereum Future",     "group":"Krypto",    "unit":"$"},
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

        rsi_r = (df['RSI'].rolling(rsi_w).max() - df['RSI'].rolling(rsi_w).min()).replace(0, np.nan)
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
            "Ticker":   ticker,
            "Name":     meta["name"],
            "Gruppe":   meta["group"],
            "Einheit":  meta["unit"],
            "Signal":   f"{sig['emoji']} {sig['label']}",
            "Sig_Data": sig,
            "Preis":    price,
            "52W_Hoch": _s(df_1y['High'].max()),
            "52W_Tief": _s(df_1y['Low'].min()),
            "Perf_1W":  _s(((df['Close'].iloc[-1]/df['Close'].iloc[-5])-1)*100 if len(df)>=5 else None, 2),
            "Perf_1M":  _s(((df['Close'].iloc[-1]/df['Close'].iloc[-22])-1)*100 if len(df)>=22 else None, 2),
            "RSI":      rsi_v,
            "StochRSI": sr,
            "Stoch_K":  sk,
            "Stoch_D":  sd,
            "CCI":      cci,
            "Z_Score":  zscore,
            "RVOL":     rvol,
            "Score":    score,
            "df":       df,
        }
    except Exception as e:
        print(f"[futures] {ticker}: {e}")
        return None


def get_all_futures_groups() -> list:
    seen, result = set(), []
    for v in FUTURES_TICKERS.values():
        if v["group"] not in seen:
            seen.add(v["group"]); result.append(v["group"])
    return result


def get_futures_by_group(group: str) -> list:
    return [k for k, v in FUTURES_TICKERS.items() if v["group"] == group]


# ─────────────────────────────────────────────────────────────────────────────
# EMAIL
# ─────────────────────────────────────────────────────────────────────────────

def send_mail_report(df_results, password, total_scanned=0, success_count=0, failed_count=0) -> str:
    try:
        sender, receiver = "daily@in8invest.com", "j.jendraszek@yahoo.de"
        signals = pd.DataFrame()
        if not df_results.empty and 'Score' in df_results.columns:
            signals = df_results[df_results['Score'] > 1].sort_values("Score", ascending=False)

        def _badge(v, low, high, invert=False):
            if v is None: return "<td style='color:#555'>N/A</td>"
            try:
                fv = float(v)
                if fv <= low:
                    bg,fc,t = ("#e6f9ee","#1a9e3f","OS") if not invert else ("#fee","#c0392b","OB")
                elif fv >= high:
                    bg,fc,t = ("#fee","#c0392b","OB") if not invert else ("#e6f9ee","#1a9e3f","OS")
                else:
                    bg,fc,t = "#f8f8f8","#888","–"
                b = f"<span style='background:{fc};color:#fff;padding:1px 5px;border-radius:3px;font-size:10px;font-weight:bold'>{t}</span>"
                fmt = "{:.3f}" if abs(fv) < 10 else "{:.1f}"
                return f"<td style='background:{bg};text-align:center;padding:8px 6px'>{b} {fmt.format(fv)}</td>"
            except: return f"<td>{v}</td>"

        def _sig_html(row):
            sig = classify_signal(row.get('StochRSI'), row.get('Stoch_Fast'), row.get('Stoch_Slow'), row.get('CCI'))
            return f"<span style='background:{sig['color']};color:#fff;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:bold'>{sig['emoji']} {sig['label']}</span>"

        sc_colors = {3:"#1a9e3f",2:"#f39c12",1:"#7f8c8d"}
        rows = ""
        for _, r in signals.iterrows():
            sc = int(r.get('Score',0))
            rows += f"""<tr>
              <td style='font-weight:700;color:#1a1a2e;white-space:nowrap'>{r.get('Ticker','')}</td>
              <td style='color:#444'>{r.get('Name','')}</td>
              <td style='text-align:center'>{_sig_html(r)}</td>
              <td style='text-align:right;font-weight:700'>{r.get('Preis','')}</td>
              {_badge(r.get('StochRSI'),0.15,0.85)}
              {_badge(r.get('Stoch_Fast'),20,80)}
              {_badge(r.get('Stoch_Slow'),25,75)}
              {_badge(r.get('CCI'),-100,100,invert=True)}
              <td style='text-align:center'><span style='background:{sc_colors.get(sc,"#999")};color:#fff;padding:2px 10px;border-radius:10px;font-weight:700'>{sc}/3</span></td>
              <td style='text-align:center;color:#666'>{r.get('Div','')}</td>
              <td style='text-align:center;color:#666'>{r.get('KGV','')}</td>
            </tr>"""

        tbl = f"""<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:12px">
          <tr style="background:#2c3e50">
            <th style="color:#fff;padding:10px 8px;text-align:left">Ticker</th>
            <th style="color:#fff;padding:10px 8px;text-align:left">Name</th>
            <th style="color:#fff;padding:10px 8px;text-align:center">Signal</th>
            <th style="color:#fff;padding:10px 8px;text-align:right">Preis</th>
            <th style="color:#fff;padding:10px 8px;text-align:center">StochRSI</th>
            <th style="color:#fff;padding:10px 8px;text-align:center">Stoch F</th>
            <th style="color:#fff;padding:10px 8px;text-align:center">Stoch S</th>
            <th style="color:#fff;padding:10px 8px;text-align:center">CCI</th>
            <th style="color:#fff;padding:10px 8px;text-align:center">Score</th>
            <th style="color:#fff;padding:10px 8px;text-align:center">Div</th>
            <th style="color:#fff;padding:10px 8px;text-align:center">KGV</th>
          </tr>{rows}</table>""" if not signals.empty else "<p style='color:#888;font-style:italic'>Keine Signale mit Score &gt; 1 gefunden.</p>"

        now = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")

        body = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:'Segoe UI',Arial,sans-serif">
<div style="max-width:860px;margin:24px auto;padding:0 16px">

  <!-- HEADER -->
  <div style="background:linear-gradient(135deg,#1a1d2e 0%,#252840 100%);border-radius:16px;padding:28px 32px;margin-bottom:16px">
    <div style="font-size:26px;font-weight:900;color:#00d4ff;letter-spacing:1px">📊 In8Invest</div>
    <div style="color:#8892a4;font-size:14px;margin-top:6px">Daily Strategy Report &nbsp;·&nbsp; {now}</div>
  </div>

  <!-- STATS -->
  <div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap">
    <div style="flex:1;min-width:120px;background:#fff;border-radius:12px;padding:20px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,0.06)">
      <div style="font-size:32px;font-weight:900;color:#3498db">{total_scanned}</div>
      <div style="font-size:11px;color:#999;text-transform:uppercase;letter-spacing:1px;margin-top:4px">Geprüft</div>
    </div>
    <div style="flex:1;min-width:120px;background:#fff;border-radius:12px;padding:20px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,0.06)">
      <div style="font-size:32px;font-weight:900;color:#1a9e3f">{success_count}</div>
      <div style="font-size:11px;color:#999;text-transform:uppercase;letter-spacing:1px;margin-top:4px">Erfolgreich</div>
    </div>
    <div style="flex:1;min-width:120px;background:#fff;border-radius:12px;padding:20px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,0.06)">
      <div style="font-size:32px;font-weight:900;color:#e74c3c">{failed_count}</div>
      <div style="font-size:11px;color:#999;text-transform:uppercase;letter-spacing:1px;margin-top:4px">Fehler</div>
    </div>
    <div style="flex:1;min-width:120px;background:#fff;border-radius:12px;padding:20px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,0.06)">
      <div style="font-size:32px;font-weight:900;color:#f39c12">{len(signals)}</div>
      <div style="font-size:11px;color:#999;text-transform:uppercase;letter-spacing:1px;margin-top:4px">Signale</div>
    </div>
  </div>

  <!-- KRITERIEN -->
  <div style="background:#fff8e6;border-left:4px solid #f39c12;border-radius:0 8px 8px 0;padding:12px 16px;margin-bottom:16px;font-size:12px;color:#7d6608">
    <b>Scan-Kriterien:</b> StochRSI(70) &lt; 0.1 &nbsp;|&nbsp; Stoch Fast(70) &lt; 10 &amp; Slow(200) &lt; 15 &nbsp;|&nbsp; CCI(40) &gt; −100
    <br><b>Legende:</b>
    <span style="background:#1a9e3f;color:#fff;padding:1px 6px;border-radius:3px;font-size:11px">OS</span> Oversold &nbsp;
    <span style="background:#c0392b;color:#fff;padding:1px 6px;border-radius:3px;font-size:11px">OB</span> Overbought &nbsp;
    <span style="background:#7f8c8d;color:#fff;padding:1px 6px;border-radius:3px;font-size:11px">–</span> Neutral
  </div>

  <!-- TABELLE -->
  <div style="background:#fff;border-radius:12px;padding:24px;box-shadow:0 2px 12px rgba(0,0,0,0.07);margin-bottom:16px">
    <h2 style="margin:0 0 16px;font-size:18px;color:#1a1a2e">🎯 Top Signale (Score ≥ 2)</h2>
    {tbl}
  </div>

  <!-- FOOTER -->
  <div style="text-align:center;color:#aaa;font-size:11px;padding:16px 0">
    In8Invest Scanner &nbsp;·&nbsp; Automatisch generiert &nbsp;·&nbsp;
    <a href="https://stockupdate-65qjxum6gq2gpjpr5exqfd.streamlit.app/" style="color:#3498db">App öffnen →</a>
  </div>

</div></body></html>"""

        msg = MIMEMultipart()
        msg['Subject'] = f"📊 In8Invest Daily | {len(signals)} Signale | {now}"
        msg['From']    = sender
        msg['To']      = receiver
        msg.attach(MIMEText(body, 'html'))
        with smtplib.SMTP_SSL("w01a1dc3.kasserver.com", 465) as s:
            s.login(sender, password)
            s.sendmail(sender, receiver, msg.as_string())
        return "✅ Mail erfolgreich versendet"
    except Exception as e:
        return f"❌ Fehler: {e}"
