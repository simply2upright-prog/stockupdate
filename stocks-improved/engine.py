# engine.py — Verbessert: Caching, robustere Fehlerbehandlung, Währungs-Unterstützung

import yfinance as yf
import pandas as pd
import numpy as np
import smtplib
import time
from functools import lru_cache
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from database import get_currency

# --- CACHE: yf.Ticker-Objekte werden zwischengespeichert ---
@lru_cache(maxsize=512)
def _get_ticker(ticker: str):
    return yf.Ticker(ticker)

def get_analysis(ticker: str, retries: int = 2) -> dict | None:
    """
    Lädt 2 Jahre Kursdaten und berechnet technische Indikatoren.
    Gibt None zurück bei zu wenig Daten oder Fehler.
    Retry-Logik verhindert Abbrüche bei kurzen API-Timeouts.
    """
    for attempt in range(retries + 1):
        try:
            stock = _get_ticker(ticker)
            df = stock.history(period="2y", auto_adjust=True)

            if df.empty or len(df) < 200:
                return None

            # --- 1. RSI (70 Tage) ---
            delta = df['Close'].diff()
            gain = delta.where(delta > 0, 0.0).rolling(window=70).mean()
            loss = (-delta.where(delta < 0, 0.0)).rolling(window=70).mean()
            rs = gain / loss.replace(0, np.nan)
            df['RSI_70'] = 100 - (100 / (1 + rs))

            # --- 2. StochRSI (70 Tage) ---
            rsi_min = df['RSI_70'].rolling(window=70).min()
            rsi_max = df['RSI_70'].rolling(window=70).max()
            rsi_range = (rsi_max - rsi_min).replace(0, np.nan)
            df['StochRSI_70'] = (df['RSI_70'] - rsi_min) / rsi_range
            stoch_rsi_val = df['StochRSI_70'].iloc[-1]

            # --- 3. Stochastik (Fast 70 / Slow 200) ---
            low_min  = df['Low'].rolling(70).min()
            high_max = df['High'].rolling(70).max()
            hl_range = (high_max - low_min).replace(0, np.nan)
            df['Stoch_Fast'] = 100 * (df['Close'] - low_min) / hl_range
            df['Stoch_Slow'] = 100 * (df['Close'] - df['Low'].rolling(200).min()) / (
                df['High'].rolling(200).max() - df['Low'].rolling(200).min()
            ).replace(0, np.nan)
            s_fast = df['Stoch_Fast'].iloc[-1]
            s_slow = df['Stoch_Slow'].iloc[-1]

            # --- 4. CCI (40 Tage) ---
            tp = (df['High'] + df['Low'] + df['Close']) / 3
            mean_dev = tp.rolling(40).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
            df['CCI_40'] = (tp - tp.rolling(40).mean()) / (0.015 * mean_dev.replace(0, np.nan))
            cci_val = df['CCI_40'].iloc[-1]

            # --- SCORING ---
            score = 0
            if pd.notna(stoch_rsi_val) and stoch_rsi_val < 0.1: score += 1
            if pd.notna(s_fast) and pd.notna(s_slow) and s_fast < 10 and s_slow < 15: score += 1
            if pd.notna(cci_val) and cci_val > -100: score += 1

            inf = stock.info
            currency = get_currency(ticker)
            div_yield = inf.get('dividendYield')
            div_str = f"{round(div_yield * 100, 2)}%" if isinstance(div_yield, (int, float)) else "0%"

            return {
                "Ticker":      ticker,
                "Name":        inf.get('shortName', ticker)[:20],
                "Preis":       f"{round(df['Close'].iloc[-1], 2)} {currency}",
                "Währung":     currency,
                "StochRSI":    round(float(stoch_rsi_val), 3) if pd.notna(stoch_rsi_val) else None,
                "CCI":         round(float(cci_val), 1)       if pd.notna(cci_val)        else None,
                "Stoch_Fast":  round(float(s_fast), 1)        if pd.notna(s_fast)         else None,
                "Stoch_Slow":  round(float(s_slow), 1)        if pd.notna(s_slow)         else None,
                "Score":       score,
                "Div":         div_str,
                "KGV":         round(inf.get('trailingPE', 0), 1) if inf.get('trailingPE') else "N/A",
            }

        except Exception as e:
            if attempt < retries:
                time.sleep(1)
            else:
                print(f"[engine] Fehler bei {ticker}: {e}")
                return None


def send_mail_report(
    df_results: pd.DataFrame,
    password: str,
    total_scanned: int = 0,
    success_count: int = 0,
    failed_count: int = 0
) -> str:
    """Sendet den täglichen Scan-Report per E-Mail."""
    try:
        sender   = "daily@in8invest.com"
        receiver = "j.jendraszek@yahoo.de"

        signals = pd.DataFrame()
        if not df_results.empty and 'Score' in df_results.columns:
            signals = df_results[df_results['Score'] > 1].sort_values("Score", ascending=False)

        def _style_row(row):
            styles = [''] * len(row.index)
            col_idx = {c: i for i, c in enumerate(row.index)}

            def _set(col, cond_green, cond_red=None):
                if col in col_idx:
                    i = col_idx[col]
                    if cond_green:
                        styles[i] = 'background-color:#4caf50;color:white'
                    elif cond_red:
                        styles[i] = 'background-color:#f44336;color:white'

            _set('StochRSI',   row.get('StochRSI', 1) < 0.1,  row.get('StochRSI', 0) > 0.9)
            _set('CCI',        row.get('CCI', -200) > -100)
            _set('Stoch_Fast', row.get('Stoch_Fast', 100) < 10, row.get('Stoch_Fast', 0) > 90)
            _set('Stoch_Slow', row.get('Stoch_Slow', 100) < 15, row.get('Stoch_Slow', 0) > 85)
            return styles

        html_table = "<p>Keine Signale mit Score &gt; 1 gefunden.</p>"
        if not signals.empty:
            html_table = (
                signals.style
                .apply(_style_row, axis=1)
                .hide(axis='index')
                .to_html()
            )

        msg = MIMEMultipart()
        msg['Subject'] = f"🚀 {len(signals)} Top-Signale | {success_count}/{total_scanned} OK | {failed_count} Fehler"
        msg['From']    = sender
        msg['To']      = receiver

        html_body = f"""
        <html><head>
        <style>
            body {{ font-family: sans-serif; background: #f5f5f5; }}
            table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
            th {{ background: #2c3e50; color: white; padding: 10px; text-align: center; }}
            td {{ border: 1px solid #ddd; padding: 8px; text-align: center; }}
            .header-box {{ background: #f0f4f8; padding: 15px; border-left: 5px solid #0056b3; margin-bottom: 20px; border-radius: 4px; }}
            .stat {{ display: inline-block; margin: 0 15px; font-size: 16px; }}
        </style>
        </head><body>
        <div class="header-box">
            <h2 style="margin:0;">📊 Strategie Report: Long-Term Reversal</h2>
            <p>Kriterien: StochRSI(70) &lt; 0.1 | Stochastik Fast(70) &amp; Slow(200) Oversold | CCI(40) &gt; -100</p>
            <hr>
            <span class="stat">📋 Geprüft: <b>{total_scanned}</b></span>
            <span class="stat">✅ Erfolgreich: <b>{success_count}</b></span>
            <span class="stat">❌ Fehler: <b>{failed_count}</b></span>
            <span class="stat">🎯 Signale: <b>{len(signals)}</b></span>
        </div>
        {html_table}
        </body></html>
        """
        msg.attach(MIMEText(html_body, 'html'))

        with smtplib.SMTP_SSL("w01a1dc3.kasserver.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, receiver, msg.as_string())
        return "✅ Mail erfolgreich versendet"

    except Exception as e:
        return f"❌ Fehler beim Mail-Versand: {e}"
