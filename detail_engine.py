# detail_engine.py — BUGFIX: auto_adjust entfernt, Fallback-History, robuste NaN-Guards

import yfinance as yf
import pandas as pd
import numpy as np
from scipy.signal import argrelextrema
from database import get_currency


def _fetch_history(ticker: str):
    """
    Lädt Kursdaten mit Fallback-Strategie.
    auto_adjust=True wurde entfernt — verursachte leere DataFrames bei vielen Tickern.
    """
    stock = yf.Ticker(ticker)
    df = stock.history(period="2y", auto_adjust=False)
    if df.empty or len(df) < 50:
        df = stock.history(period="1y", auto_adjust=False)
    return df, stock


def get_detail_analysis(ticker: str) -> dict | None:
    """
    Vollständige technische Tiefen-Analyse für einen einzelnen Ticker.
    Gibt None zurück bei zu wenig Daten oder API-Fehler.
    """
    try:
        df, stock = _fetch_history(ticker)

        if df.empty:
            print(f"[detail_engine] Leerer DataFrame für {ticker}")
            return None
        if len(df) < 50:
            print(f"[detail_engine] Zu wenig Daten für {ticker}: {len(df)} Zeilen")
            return None

        has_200 = len(df) >= 200
        has_70  = len(df) >= 70

        # --- 1. RSI (70 Tage, sonst 14) ---
        rsi_window = 70 if has_70 else 14
        delta = df['Close'].diff()
        gain  = delta.where(delta > 0, 0.0).rolling(window=rsi_window).mean()
        loss  = (-delta.where(delta < 0, 0.0)).rolling(window=rsi_window).mean()
        rs    = gain / loss.replace(0, np.nan)
        df['RSI_70'] = 100 - (100 / (1 + rs))

        # --- 2. StochRSI ---
        rsi_min   = df['RSI_70'].rolling(rsi_window).min()
        rsi_max   = df['RSI_70'].rolling(rsi_window).max()
        rsi_range = (rsi_max - rsi_min).replace(0, np.nan)
        df['StochRSI_70'] = (df['RSI_70'] - rsi_min) / rsi_range

        # --- 3. Stochastik (Fast 14 / Slow 7-SMA) ---
        low_min  = df['Low'].rolling(14).min()
        high_max = df['High'].rolling(14).max()
        hl_range = (high_max - low_min).replace(0, np.nan)
        df['Stoch_Fast'] = 100 * (df['Close'] - low_min) / hl_range
        df['Stoch_Slow'] = df['Stoch_Fast'].rolling(7).mean()

        # --- 4. CCI (20 Tage) ---
        tp       = (df['High'] + df['Low'] + df['Close']) / 3
        mean_dev = tp.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
        df['CCI_20'] = (tp - tp.rolling(20).mean()) / (0.015 * mean_dev.replace(0, np.nan))

        # --- 5. Bollinger Bänder (200 EMA wenn möglich, sonst 50) ---
        bb_window = 200 if has_200 else 50
        df['SMA200']   = df['Close'].ewm(span=bb_window, adjust=False).mean()
        std_bb         = df['Close'].rolling(bb_window).std()
        df['BB_Upper'] = df['SMA200'] + 2 * std_bb
        df['BB_Lower'] = df['SMA200'] - 2 * std_bb

        # --- 6. Z-Score & RVOL ---
        w20           = min(20, len(df) - 1)
        df['SMA20']   = df['Close'].rolling(w20).mean()
        df['Z_Score'] = (df['Close'] - df['SMA20']) / df['Close'].rolling(w20).std().replace(0, np.nan)
        vol_avg       = df['Volume'].rolling(w20).mean().replace(0, np.nan)
        df['RVOL']    = df['Volume'] / vol_avg

        # --- 7. Mustererkennung ---
        patterns = _detect_patterns(df)

        # --- Kennzahlen ---
        aktienkurs = float(df['Close'].iloc[-1])
        prev_close = float(df['Close'].iloc[-2]) if len(df) >= 2 else aktienkurs
        perf_abs   = aktienkurs - prev_close
        perf_pct   = (perf_abs / prev_close * 100) if prev_close != 0 else 0.0

        def _safe(val, decimals=3):
            try:
                v = float(val)
                return round(v, decimals) if np.isfinite(v) else 0.0
            except Exception:
                return 0.0

        stoch_rsi_val = _safe(df['StochRSI_70'].iloc[-1])
        s_fast        = _safe(df['Stoch_Fast'].iloc[-1], 1)
        s_slow        = _safe(df['Stoch_Slow'].iloc[-1], 1)
        cci_val       = _safe(df['CCI_20'].iloc[-1], 1)
        z_score       = _safe(df['Z_Score'].iloc[-1], 2)
        rvol          = _safe(df['RVOL'].iloc[-1], 2)

        # --- Scoring ---
        score = 0
        if 0 < stoch_rsi_val < 0.1: score += 1
        if s_fast > 0 and s_fast < 20 and s_slow < 25: score += 1
        if cci_val != 0 and cci_val > -100: score += 1

        # --- Stammdaten ---
        inf = {}
        try:
            inf = stock.info or {}
        except Exception:
            pass

        currency  = get_currency(ticker)
        div_yield = inf.get('dividendYield')
        div_str   = f"{round(div_yield * 100, 2)}%" if isinstance(div_yield, (int, float)) and div_yield > 0 else "0.00%"
        df_1y     = df.tail(252)

        return {
            "Ticker":    ticker,
            "Name":      inf.get('shortName', ticker)[:25],
            "Währung":   currency,
            "Preis":     round(aktienkurs, 2),
            "Perf_Abs":  round(perf_abs, 2),
            "Perf_Pct":  round(perf_pct, 2),
            "Hoch_365":  round(float(df_1y['High'].max()), 2),
            "Tief_365":  round(float(df_1y['Low'].min()), 2),
            "Score":     score,
            "StochRSI":  stoch_rsi_val,
            "CCI":       cci_val,
            "Z_Score":   z_score,
            "RVOL":      rvol,
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
    if len(df) < 30:
        return patterns

    order = min(7, max(2, len(df) // 10))

    try:
        idx_max = argrelextrema(df['High'].values, np.greater_equal, order=order)[0]
        idx_min = argrelextrema(df['Low'].values,  np.less_equal,    order=order)[0]

        p_max = df['High'].iloc[idx_max].tail(5).tolist()
        p_min = df['Low'].iloc[idx_min].tail(5).tolist()

        # SKS
        if len(p_max) >= 3:
            s1, k, s2 = p_max[-3], p_max[-2], p_max[-1]
            if k > s1 and k > s2 and s1 > 0 and abs(s1 - s2) / s1 < 0.04:
                patterns.append("SKS-Formation")

        # Doppelboden
        if len(p_min) >= 2:
            b1, b2 = p_min[-2], p_min[-1]
            if b1 > 0 and abs(b1 - b2) / b1 < 0.02:
                patterns.append("Doppelboden")

        # Doppeltop
        if len(p_max) >= 2:
            t1, t2 = p_max[-2], p_max[-1]
            if t1 > 0 and abs(t1 - t2) / t1 < 0.02:
                patterns.append("Doppeltop")

        # Selling Climax
        rvol_val = df['RVOL'].iloc[-1] if 'RVOL' in df.columns else 0
        if pd.notna(rvol_val) and df['Close'].iloc[-1] < df['Open'].iloc[-1] and float(rvol_val) > 2.0:
            patterns.append("Selling Climax (Potenzielle Wende)")

        # Gap Up / Down
        if len(df) >= 2:
            prev      = float(df['Close'].iloc[-2])
            curr_open = float(df['Open'].iloc[-1])
            if prev > 0:
                gap     = (curr_open - prev) / prev
                vol_avg = df['Volume'].rolling(20).mean().iloc[-2] if len(df) >= 20 else df['Volume'].mean()
                vol_now = float(df['Volume'].iloc[-1])
                if gap > 0.015:
                    label = "Power Gap Up" if vol_now > vol_avg * 1.5 else "Gap Up"
                    patterns.append(f"{label} (+{round(gap * 100, 1)}%)")
                elif gap < -0.015:
                    label = "Power Gap Down" if vol_now > vol_avg * 1.5 else "Gap Down"
                    patterns.append(f"{label} ({round(gap * 100, 1)}%)")

        # Bollinger Squeeze
        if all(c in df.columns for c in ['BB_Upper', 'BB_Lower', 'SMA200']):
            sma = df['SMA200'].replace(0, np.nan)
            bw  = (df['BB_Upper'] - df['BB_Lower']) / sma
            if len(bw.dropna()) >= 100:
                bw_min = bw.rolling(100).min().iloc[-1]
                if pd.notna(bw.iloc[-1]) and pd.notna(bw_min) and bw.iloc[-1] < bw_min * 1.1:
                    patterns.append("Bollinger Squeeze")

    except Exception as e:
        print(f"[pattern_detect] Fehler: {e}")

    return patterns
