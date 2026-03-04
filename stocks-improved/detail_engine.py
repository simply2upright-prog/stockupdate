# detail_engine.py — Verbessert: NaN-Schutz, Währung, sauberere Indikatoren

import yfinance as yf
import pandas as pd
import numpy as np
from scipy.signal import argrelextrema
from database import get_currency


def get_detail_analysis(ticker: str) -> dict | None:
    """
    Vollständige technische Tiefen-Analyse für einen einzelnen Ticker.
    Gibt None zurück bei zu wenig Daten oder API-Fehler.
    """
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="2y", auto_adjust=True)

        if df.empty or len(df) < 200:
            return None

        # --- 1. RSI (70 Tage) ---
        delta = df['Close'].diff()
        gain  = delta.where(delta > 0, 0.0).rolling(window=70).mean()
        loss  = (-delta.where(delta < 0, 0.0)).rolling(window=70).mean()
        rs    = gain / loss.replace(0, np.nan)
        df['RSI_70'] = 100 - (100 / (1 + rs))

        # --- 2. StochRSI (70 Tage) ---
        rsi_min   = df['RSI_70'].rolling(70).min()
        rsi_max   = df['RSI_70'].rolling(70).max()
        rsi_range = (rsi_max - rsi_min).replace(0, np.nan)
        df['StochRSI_70'] = (df['RSI_70'] - rsi_min) / rsi_range

        # --- 3. Stochastik (Fast 14 / Slow 7-SMA) ---
        low_min  = df['Low'].rolling(14).min()
        high_max = df['High'].rolling(14).max()
        hl_range = (high_max - low_min).replace(0, np.nan)
        df['Stoch_Fast'] = 100 * (df['Close'] - low_min) / hl_range
        df['Stoch_Slow'] = df['Stoch_Fast'].rolling(7).mean()

        # --- 4. CCI (20 Tage) ---
        tp        = (df['High'] + df['Low'] + df['Close']) / 3
        mean_dev  = tp.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
        df['CCI_20'] = (tp - tp.rolling(20).mean()) / (0.015 * mean_dev.replace(0, np.nan))

        # --- 5. Bollinger Bänder (200 EMA, 2σ) ---
        df['SMA200']   = df['Close'].ewm(span=200, adjust=False).mean()
        std200         = df['Close'].rolling(200).std()
        df['BB_Upper'] = df['SMA200'] + 2 * std200
        df['BB_Lower'] = df['SMA200'] - 2 * std200

        # --- 6. Z-Score & Relatives Volumen (RVOL) ---
        df['SMA20']  = df['Close'].rolling(20).mean()
        df['Z_Score'] = (df['Close'] - df['SMA20']) / df['Close'].rolling(20).std().replace(0, np.nan)
        vol_avg      = df['Volume'].rolling(20).mean().replace(0, np.nan)
        df['RVOL']   = df['Volume'] / vol_avg

        # --- 7. Mustererkennung ---
        patterns = _detect_patterns(df)

        # --- Kennzahlen ---
        aktienkurs = df['Close'].iloc[-1]
        prev_close = df['Close'].iloc[-2]
        perf_abs   = aktienkurs - prev_close
        perf_pct   = (perf_abs / prev_close * 100) if prev_close != 0 else 0.0

        stoch_rsi_val = df['StochRSI_70'].iloc[-1]
        s_fast        = df['Stoch_Fast'].iloc[-1]
        s_slow        = df['Stoch_Slow'].iloc[-1]
        cci_val       = df['CCI_20'].iloc[-1]
        z_score       = df['Z_Score'].iloc[-1]
        rvol          = df['RVOL'].iloc[-1]

        # --- Scoring ---
        score = 0
        if pd.notna(stoch_rsi_val) and stoch_rsi_val < 0.1: score += 1
        if pd.notna(s_fast) and pd.notna(s_slow) and s_fast < 20 and s_slow < 25: score += 1
        if pd.notna(cci_val) and cci_val > -100: score += 1

        # --- Stammdaten ---
        inf       = stock.info
        currency  = get_currency(ticker)
        div_yield = inf.get('dividendYield')
        div_str   = f"{round(div_yield * 100, 2)}%" if isinstance(div_yield, (int, float)) else "0.00%"
        df_1y     = df.tail(252)

        return {
            "Ticker":    ticker,
            "Name":      inf.get('shortName', ticker)[:20],
            "Währung":   currency,
            "Preis":     round(float(aktienkurs), 2),
            "Perf_Abs":  round(float(perf_abs), 2),
            "Perf_Pct":  round(float(perf_pct), 2),
            "Hoch_365":  round(float(df_1y['High'].max()), 2),
            "Tief_365":  round(float(df_1y['Low'].min()), 2),
            "Score":     score,
            "StochRSI":  round(float(stoch_rsi_val), 3) if pd.notna(stoch_rsi_val) else 0.0,
            "CCI":       round(float(cci_val), 1)       if pd.notna(cci_val)        else 0.0,
            "Z_Score":   round(float(z_score), 2)       if pd.notna(z_score)        else 0.0,
            "RVOL":      round(float(rvol), 2)          if pd.notna(rvol)           else 0.0,
            "Div":       div_str,
            "KGV":       round(inf.get('trailingPE', 0), 1) if inf.get('trailingPE') else "N/A",
            "Patterns":  patterns,
            "df":        df,
        }

    except Exception as e:
        print(f"[detail_engine] Fehler bei {ticker}: {e}")
        return None


def _detect_patterns(df: pd.DataFrame) -> list[str]:
    """Erkennt charttechnische Muster im DataFrame."""
    patterns = []
    order = 7

    try:
        df['Pivot_Max'] = np.nan
        df['Pivot_Min'] = np.nan
        idx_max = argrelextrema(df['High'].values, np.greater_equal, order=order)[0]
        idx_min = argrelextrema(df['Low'].values,  np.less_equal,    order=order)[0]
        df.iloc[idx_max, df.columns.get_loc('Pivot_Max')] = df['High'].iloc[idx_max]
        df.iloc[idx_min, df.columns.get_loc('Pivot_Min')] = df['Low'].iloc[idx_min]

        p_max = df['Pivot_Max'].dropna().tail(5).tolist()
        p_min = df['Pivot_Min'].dropna().tail(5).tolist()

        # Schulter-Kopf-Schulter
        if len(p_max) >= 3:
            s1, k, s2 = p_max[-3], p_max[-2], p_max[-1]
            if k > s1 and k > s2 and abs(s1 - s2) / max(s1, 0.0001) < 0.04:
                patterns.append("SKS-Formation")

        # Doppelboden
        if len(p_min) >= 2:
            if abs(p_min[-2] - p_min[-1]) / max(p_min[-2], 0.0001) < 0.02:
                patterns.append("Doppelboden")

        # Doppeltop
        if len(p_max) >= 2:
            if abs(p_max[-2] - p_max[-1]) / max(p_max[-2], 0.0001) < 0.02:
                patterns.append("Doppeltop")

        # Selling Climax
        rvol_last = df['RVOL'].iloc[-1] if 'RVOL' in df.columns else 0
        if df['Close'].iloc[-1] < df['Open'].iloc[-1] and rvol_last > 2.0:
            patterns.append("Selling Climax (Potenzielle Wende)")

        # Gap Up / Power Gap
        gap = (df['Open'].iloc[-1] - df['Close'].iloc[-2]) / max(df['Close'].iloc[-2], 0.0001)
        vol_avg = df['Volume'].rolling(20).mean().iloc[-2]
        if gap > 0.015:
            label = "Power Gap" if df['Volume'].iloc[-1] > vol_avg * 1.5 else "Gap Up"
            patterns.append(f"{label} (+{round(gap * 100, 1)}%)")
        elif gap < -0.015:
            label = "Power Gap Down" if df['Volume'].iloc[-1] > vol_avg * 1.5 else "Gap Down"
            patterns.append(f"{label} ({round(gap * 100, 1)}%)")

        # Bollinger Squeeze
        if 'BB_Upper' in df.columns and 'BB_Lower' in df.columns and 'SMA200' in df.columns:
            bw = (df['BB_Upper'] - df['BB_Lower']) / df['SMA200'].replace(0, np.nan)
            bw_min = bw.rolling(100).min().iloc[-1]
            if pd.notna(bw.iloc[-1]) and pd.notna(bw_min) and bw.iloc[-1] < bw_min * 1.1:
                patterns.append("Bollinger Squeeze")

    except Exception as e:
        print(f"[pattern_detect] Fehler: {e}")

    return patterns
