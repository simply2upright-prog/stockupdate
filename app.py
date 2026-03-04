# app.py — v3: Signal-Badges, Zielkurse, Futures-Tab, Top-Erkennung

import streamlit as st
import pandas as pd
import numpy as np
import base64
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from database import get_all_tickers, get_tickers_by_group, get_all_groups, get_currency, get_ticker_count
from engine import (get_analysis, send_mail_report, classify_signal,
                    get_futures_analysis, FUTURES_TICKERS,
                    get_all_futures_groups, get_futures_by_group)
from detail_engine import get_detail_analysis

# ─── PAGE CONFIG ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="In8Invest Scanner", page_icon="📊", layout="wide")

try:
    def _b64(p):
        with open(p,"rb") as f: return base64.b64encode(f.read()).decode()
    st.markdown(f'<div style="margin-bottom:8px"><img src="data:image/png;base64,{_b64("Icon in8invest.png")}" width="160"></div>', unsafe_allow_html=True)
except: pass

st.title("📊 Strategie Scanner")
st.caption(f"🌍 Datenbank: {get_ticker_count()} Ticker · {len(get_all_groups())} Märkte & Sektoren")

if "results" not in st.session_state: st.session_state.results = pd.DataFrame()

# Ampel-HTML-Helper
def _sig_badge(sig: dict) -> str:
    return (f"<span style='background:{sig['color']};color:#fff;padding:3px 10px;"
            f"border-radius:12px;font-size:12px;font-weight:700'>{sig['emoji']} {sig['label']}</span>")

def _ind_badge(v, low, high, fmt="{:.3f}", invert=False) -> str:
    if v is None: return "N/A"
    try:
        fv = float(v)
        if fv <= low:   c,t = ("#1a9e3f","OS") if not invert else ("#c0392b","OB")
        elif fv >= high:c,t = ("#c0392b","OB") if not invert else ("#1a9e3f","OS")
        else:            c,t = "#7f8c8d","—"
        badge = f"<span style='background:{c};color:#fff;padding:1px 6px;border-radius:3px;font-size:11px;font-weight:700'>{t}</span>"
        return f"{badge} {fmt.format(fv)}"
    except: return str(v)

# ─── TABS ─────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🚀 Scanner", "📊 Detail-Analyse", "📐 Formations-Check", "🛢️ Rohstoffe & Futures", "📅 Automation"
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — SCANNER
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.header("Globaler Markt-Scanner")
    c1, c2 = st.columns([4, 1])
    sel_grp   = c1.selectbox("📂 Markt / Index / Sektor:", ["🌍 Alle Gruppen"] + get_all_groups(), key="scan_grp")
    min_score = c2.selectbox("Min. Score:", [1, 2, 3])

    if st.button("🔥 SCAN STARTEN", use_container_width=False):
        tickers  = get_all_tickers() if sel_grp == "🌍 Alle Gruppen" else get_tickers_by_group(sel_grp)
        raw, prog, stat = [], st.progress(0), st.empty()
        for i, t in enumerate(tickers):
            stat.text(f"Scanne {i+1}/{len(tickers)}: {t}")
            res = get_analysis(t)
            if res: raw.append(res)
            prog.progress((i+1)/len(tickers))
        df = pd.DataFrame(raw)
        if not df.empty:
            df = df[df["Score"] >= min_score].sort_values("Score", ascending=False).reset_index(drop=True)
            st.session_state.results = df
            stat.success(f"✅ {len(df)} Signale in {len(tickers)} Titeln.")
        else:
            stat.warning("Keine Signale.")

    if not st.session_state.results.empty:
        df_show = st.session_state.results.copy()
        # Signal-Spalte ist bereits als Text; restliche Indikatoren mit Farbe
        st.markdown("##### Ergebnisse — Signal-Legende: 🟢 OVERSOLD · 🔴 OVERBOUGHT · ⚪ NEUTRAL")

        # Farbige HTML-Tabelle
        def _row_html(r):
            sv, sf, ss, cv = r.get('StochRSI'), r.get('Stoch_Fast'), r.get('Stoch_Slow'), r.get('CCI')
            sig = classify_signal(sv, sf, ss, cv)
            sc  = int(r.get('Score', 0))
            sc_c = {3:"#1a9e3f",2:"#f39c12",1:"#7f8c8d"}.get(sc,"#999")
            return (
                f"<tr>"
                f"<td><b>{r['Ticker']}</b></td>"
                f"<td>{r.get('Name','')}</td>"
                f"<td>{_sig_badge(sig)}</td>"
                f"<td style='text-align:right'><b>{r.get('Preis','')}</b></td>"
                f"<td style='text-align:center'>{_ind_badge(sv,0.15,0.85)}</td>"
                f"<td style='text-align:center'>{_ind_badge(sf,20,80,'{:.1f}')}</td>"
                f"<td style='text-align:center'>{_ind_badge(ss,25,75,'{:.1f}')}</td>"
                f"<td style='text-align:center'>{_ind_badge(cv,-100,100,'{:.1f}',invert=True)}</td>"
                f"<td style='text-align:center'><span style='background:{sc_c};color:#fff;padding:2px 8px;border-radius:10px;font-weight:700'>{sc}/3</span></td>"
                f"<td>{r.get('Div','')}</td><td>{r.get('KGV','')}</td>"
                f"</tr>"
            )

        thead = """<thead style='background:#1e2235;color:#8892a4;font-size:11px;text-transform:uppercase;letter-spacing:.5px'>
            <tr><th style='padding:10px 8px'>Ticker</th><th>Name</th><th>Signal</th><th>Preis</th>
            <th>StochRSI</th><th>Stoch F</th><th>Stoch S</th><th>CCI</th>
            <th>Score</th><th>Div</th><th>KGV</th></tr></thead>"""
        tbody = "".join(_row_html(r) for _, r in df_show.iterrows())
        html  = f"""<div style='overflow-x:auto'>
            <table style='border-collapse:collapse;width:100%;font-size:13px;font-family:sans-serif'>
            {thead}<tbody>{tbody}</tbody></table></div>"""
        st.markdown(html, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — DETAIL-ANALYSE
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.header("Analyse & Chart-Center")
    sel_t = st.selectbox("Aktie:", get_all_tickers(), key="det_t")

    if sel_t:
        with st.spinner(f"Lade {sel_t} …"):
            data = get_detail_analysis(sel_t)

        if data and "df" in data:
            cur = data["Währung"]
            sig = data["Sig_Data"]
            sc_col = "green" if data["Score"]>=2 else ("orange" if data["Score"]==1 else "red")

            # Header
            col_h1, col_h2 = st.columns([3,1])
            col_h1.markdown(f"### {data['Name']} ({sel_t})")
            col_h2.markdown(_sig_badge(sig), unsafe_allow_html=True)
            col_h2.markdown(f":{sc_col}[Score {data['Score']}/3]")

            # Metriken
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Kurs", f"{data['Preis']:.2f} {cur}",
                      delta=f"{data['Perf_Abs']:+.2f} {cur} ({data['Perf_Pct']:+.2f}%)")
            c2.metric("52W Hoch", f"{data['Hoch_365']:.2f} {cur}")
            c3.metric("52W Tief", f"{data['Tief_365']:.2f} {cur}")
            c4.metric("Dividende", data["Div"])

            # Indikator-Badges
            st.divider()
            st.markdown("#### Indikator-Status")
            ib1, ib2, ib3, ib4 = st.columns(4)
            ib1.markdown(f"**StochRSI** &nbsp; {_ind_badge(data['StochRSI'],0.15,0.85)}", unsafe_allow_html=True)
            ib2.markdown(f"**CCI** &nbsp; {_ind_badge(data['CCI'],-100,100,'{:.1f}',invert=True)}", unsafe_allow_html=True)
            ib3.markdown(f"**Z-Score** &nbsp; {_ind_badge(data['Z_Score'],-1.5,1.5,'{:.2f}')}", unsafe_allow_html=True)
            ib4.markdown(f"**RVOL** &nbsp; <span style='font-size:14px'>{data['RVOL']:.2f}x</span>", unsafe_allow_html=True)

            # Chart
            df_p = data["df"].tail(252)
            fig  = make_subplots(rows=5, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                                 row_heights=[0.40,0.10,0.15,0.15,0.15],
                                 subplot_titles=("Kurs & Bollinger","Volumen","Stochastik","StochRSI","CCI"))
            fig.add_trace(go.Scatter(x=df_p.index, y=df_p["BB_Lower"], name="BB-", line=dict(color="#00eeee",width=.8,dash="dot"), showlegend=False), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_p.index, y=df_p["BB_Upper"], name="Bollinger", fill="tonexty", fillcolor="rgba(0,238,238,0.05)", line=dict(color="#00eeee",width=.8,dash="dot")), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_p.index, y=df_p["SMA200"],  name="EMA200", line=dict(color="#888",width=1.5,dash="dash")), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_p.index, y=df_p["Close"],   name="Kurs",   line=dict(color="#ffff00",width=2.5)), row=1, col=1)
            v_c = ["#ff4444" if r["Open"]>r["Close"] else "#00cc66" for _,r in df_p.iterrows()]
            fig.add_trace(go.Bar(x=df_p.index, y=df_p["Volume"], name="Vol", marker_color=v_c, opacity=.7), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_p.index, y=df_p["Stoch_Fast"], name="Fast", line=dict(color="#00ffff",width=1)), row=3, col=1)
            fig.add_trace(go.Scatter(x=df_p.index, y=df_p["Stoch_Slow"], name="Slow", line=dict(color="#ff00ff",width=2)), row=3, col=1)
            for y,c in [(10,"#00ff00"),(90,"#ff0000")]: fig.add_hline(y=y, line_color=c, line_width=1, row=3, col=1)
            fig.add_trace(go.Scatter(x=df_p.index, y=df_p["StochRSI_70"], name="StochRSI", line=dict(color="#fff",width=1.5)), row=4, col=1)
            for y,c in [(0.1,"#00ff00"),(0.9,"#ff0000")]: fig.add_hline(y=y, line_color=c, row=4, col=1)
            fig.add_trace(go.Scatter(x=df_p.index, y=df_p["CCI_20"], name="CCI", line=dict(color="#be94ff",width=2)), row=5, col=1)
            for y,c in [(-100,"#00ff00"),(100,"#ff0000")]: fig.add_hline(y=y, line_color=c, row=5, col=1)
            fig.update_layout(height=1000, template="plotly_dark", paper_bgcolor="black", plot_bgcolor="black",
                              margin=dict(l=10,r=10,t=40,b=10), hovermode="x unified")
            fig.update_xaxes(showgrid=True, gridcolor="#222")
            fig.update_yaxes(showgrid=True, gridcolor="#222")
            st.plotly_chart(fig, use_container_width=True)

            # Fundamentals
            st.markdown("#### Fundamentale Kennzahlen")
            m1,m2,m3,m4 = st.columns(4)
            m1.metric("KGV",str(data["KGV"])); m2.metric("CCI",f"{data['CCI']:.1f}")
            m3.metric("StochRSI",f"{data['StochRSI']:.3f}"); m4.metric("Z-Score",f"{data['Z_Score']:.2f}")

            # Muster
            if data.get("Patterns"):
                st.markdown("#### 📐 Erkannte Muster")
                for p in data["Patterns"]: st.info(f"📌 {p}")

            # Zielkurse
            if data.get("Targets"):
                st.markdown("#### 🎯 Zielkurse & Fibonacci")
                t_items = data["Targets"].items()
                col_n = 3
                rows_t = [list(t_items)[i:i+col_n] for i in range(0, len(data["Targets"]), col_n)]
                for row_t in rows_t:
                    cols_t = st.columns(col_n)
                    for j,(k,v) in enumerate(row_t):
                        price_now = data["Preis"]
                        pct  = round((v - price_now) / price_now * 100, 1) if price_now else 0
                        delta_str = f"{pct:+.1f}% vom Kurs"
                        label = k.replace("_"," ")
                        cols_t[j].metric(label, f"{v:.2f} {cur}", delta=delta_str)

        else:
            st.error(f"❌ Keine Daten für **{sel_t}**. Bitte Symbol prüfen.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — FORMATIONS-CHECK (Boden & Top)
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.header("📐 Formations-Check: Boden & Topbildung")

    mode = st.radio("Modus:", ["🔍 Markt scannen", "🎯 Einzelne Aktie"], horizontal=True)

    if mode == "🔍 Markt scannen":
        grp_opts = ["🌍 Alle Gruppen"] + get_all_groups()
        grp_t3   = st.selectbox("Gruppe:", grp_opts, key="form_grp")
        scan_mode = st.radio("Suche nach:", ["🟢 Bodenbildung (Kaufchancen)", "🔴 Topbildung (Verkaufchancen)", "🔍 Alle Signale"], horizontal=True)

        if st.button("🚀 Formations-Scan starten"):
            tickers_t3 = get_all_tickers() if grp_t3=="🌍 Alle Gruppen" else get_tickers_by_group(grp_t3)
            result_list, prog, txt = [], st.progress(0), st.empty()

            for i,t in enumerate(tickers_t3):
                txt.text(f"Scanne: {t}")
                res = get_detail_analysis(t)
                if res:
                    patterns = res.get("Patterns", [])
                    targets  = res.get("Targets",  {})

                    # Boden-Score
                    b_score = 0
                    if res["Z_Score"] < -1.5: b_score += 15
                    if res["Z_Score"] < -2.0: b_score += 15
                    if res["RVOL"]    > 1.3:  b_score += 10
                    if res["RVOL"]    > 2.0:  b_score += 15
                    for p in patterns:
                        if "Selling Climax"   in p: b_score += 30
                        if "Doppelboden"      in p: b_score += 20
                        if "Dreifachboden"    in p: b_score += 25
                        if "Umgekehrte SKS"   in p: b_score += 25
                        if "V-Boden"          in p: b_score += 15
                    b_score = min(b_score, 100)

                    # Top-Score
                    t_score = 0
                    if res["Z_Score"] > 1.5: t_score += 15
                    if res["Z_Score"] > 2.0: t_score += 15
                    if res["RVOL"]    > 1.3: t_score += 10
                    if res["RVOL"]    > 2.0: t_score += 15
                    for p in patterns:
                        if "Buying Climax"    in p: t_score += 30
                        if "Doppeltop"        in p: t_score += 20
                        if "SKS-Formation"    in p: t_score += 25
                        if "Gap Up"           in p: t_score += 10
                    t_score = min(t_score, 100)

                    show = False
                    if "Bodenbildung" in scan_mode and b_score >= 30: show = True
                    if "Topbildung"   in scan_mode and t_score >= 30: show = True
                    if "Alle"         in scan_mode and (b_score >= 30 or t_score >= 30): show = True

                    if show:
                        # Bestes Ziel ermitteln
                        entry_target = ""
                        if b_score >= t_score:
                            if "Doppelboden_Nackenlinie" in targets:
                                entry_target = f"Neckline: {targets['Doppelboden_Nackenlinie']} → Ziel: {targets.get('Doppelboden_Ziel_100pct','?')}"
                            elif targets:
                                k,v = next(iter(targets.items()))
                                entry_target = f"{k.replace('_',' ')}: {v}"
                        else:
                            if "Doppeltop_Nackenlinie" in targets:
                                entry_target = f"Neckline: {targets['Doppeltop_Nackenlinie']} → Ziel: {targets.get('Doppeltop_Ziel_100pct','?')}"

                        result_list.append({
                            "Ticker":       t,
                            "Name":         res["Name"],
                            "Signal":       res["Signal"],
                            "Boden %":      b_score,
                            "Top %":        t_score,
                            "Muster":       " | ".join(patterns[:3]) if patterns else "–",
                            "Einstieg/Ziel":entry_target or "–",
                            "Preis":        f"{res['Preis']} {res['Währung']}",
                            "Z-Score":      res["Z_Score"],
                            "RVOL":         res["RVOL"],
                        })
                prog.progress((i+1)/len(tickers_t3))

            txt.empty()
            if result_list:
                sort_col = "Boden %" if "Bodenbildung" in scan_mode or "Alle" in scan_mode else "Top %"
                df_f = pd.DataFrame(result_list).sort_values(sort_col, ascending=False)
                st.subheader(f"🔥 {len(df_f)} Formationen erkannt")
                st.dataframe(df_f, hide_index=True, use_container_width=True)
            else:
                st.warning("Keine Formationen gefunden.")

    else:
        # Einzelanalyse
        sel_t3 = st.selectbox("Aktie:", get_all_tickers(), key="form_single")
        if sel_t3:
            with st.spinner(f"Analysiere {sel_t3} …"):
                data = get_detail_analysis(sel_t3)

            if data and "df" in data:
                df   = data["df"]
                cur  = data["Währung"]

                # Boden & Top Wahrscheinlichkeit
                patterns = data.get("Patterns", [])
                targets  = data.get("Targets", {})

                b_score = t_score = 0
                b_reasons = []
                t_reasons = []

                if data["Z_Score"] < -1.5: b_score += 15
                if data["Z_Score"] < -2.0: b_score += 15; b_reasons.append(f"📏 Extrem überverkauft (Z={data['Z_Score']})")
                if data["RVOL"]    > 1.3:  b_score += 10
                if data["RVOL"]    > 2.0:  b_score += 15; b_reasons.append(f"📊 Hohes Volumen (RVOL {data['RVOL']})")
                for p in patterns:
                    if "Selling Climax"  in p: b_score += 30; b_reasons.append("🚨 Selling Climax")
                    if "Doppelboden"     in p: b_score += 20; b_reasons.append("📐 Doppelboden")
                    if "Dreifachboden"   in p: b_score += 25; b_reasons.append("📐 Dreifachboden")
                    if "Umgekehrte SKS"  in p: b_score += 25; b_reasons.append("📐 Inverse SKS")
                    if "V-Boden"         in p: b_score += 15; b_reasons.append("📐 V-Boden")
                if data["Z_Score"] > 1.5: t_score += 15
                if data["Z_Score"] > 2.0: t_score += 15; t_reasons.append(f"📏 Extrem überkauft (Z={data['Z_Score']})")
                if data["RVOL"]    > 2.0: t_score += 15; t_reasons.append(f"📊 Hohes Volumen (RVOL {data['RVOL']})")
                for p in patterns:
                    if "Buying Climax"   in p: t_score += 30; t_reasons.append("🚨 Buying Climax")
                    if "Doppeltop"       in p: t_score += 20; t_reasons.append("📐 Doppeltop")
                    if "SKS-Formation"   in p: t_score += 25; t_reasons.append("📐 SKS")

                b_score = min(b_score, 100)
                t_score = min(t_score, 100)

                col_b, col_t = st.columns(2)

                # BODEN GAUGE
                with col_b:
                    fig_b = go.Figure(go.Indicator(
                        mode="gauge+number", value=b_score,
                        number={"suffix":"%","font":{"size":60,"color":"#00d4ff","family":"Arial Black"}},
                        title={"text":"🟢 Bodenbildung","font":{"size":18,"color":"white"}},
                        gauge={"axis":{"range":[0,100]},"bar":{"color":"#1a9e3f"},
                               "bgcolor":"#161b22",
                               "steps":[{"range":[0,40],"color":"#333"},{"range":[40,70],"color":"#555"}],
                               "threshold":{"line":{"color":"#00ff88","width":4},"value":70}}))
                    fig_b.update_layout(paper_bgcolor="rgba(0,0,0,0)",font={"color":"white"},height=350)
                    st.plotly_chart(fig_b, use_container_width=True)
                    for r in b_reasons: st.write(f"✅ {r}")
                    if   b_score >= 70: st.success("🔥 STARKES BODEN-SIGNAL!")
                    elif b_score >= 40: st.warning("⚠️ Bodenbildung möglich")
                    else:               st.info("📉 Noch kein Boden erkennbar")

                # TOP GAUGE
                with col_t:
                    fig_t = go.Figure(go.Indicator(
                        mode="gauge+number", value=t_score,
                        number={"suffix":"%","font":{"size":60,"color":"#ff6b6b","family":"Arial Black"}},
                        title={"text":"🔴 Topbildung","font":{"size":18,"color":"white"}},
                        gauge={"axis":{"range":[0,100]},"bar":{"color":"#c0392b"},
                               "bgcolor":"#161b22",
                               "steps":[{"range":[0,40],"color":"#333"},{"range":[40,70],"color":"#555"}],
                               "threshold":{"line":{"color":"#ff0000","width":4},"value":70}}))
                    fig_t.update_layout(paper_bgcolor="rgba(0,0,0,0)",font={"color":"white"},height=350)
                    st.plotly_chart(fig_t, use_container_width=True)
                    for r in t_reasons: st.write(f"⚠️ {r}")
                    if   t_score >= 70: st.error("🔴 STARKES TOP-SIGNAL!")
                    elif t_score >= 40: st.warning("⚠️ Topbildung möglich")
                    else:               st.info("📈 Kein Top erkennbar")

                # Zielkurse
                st.divider()
                if targets:
                    st.subheader("🎯 Zielkurse, Fibonacci & Einstiegszonen")
                    price_now = data["Preis"]

                    # Fibonacci Chart
                    fib_keys = [k for k in targets if k.startswith("Fib_")]
                    other_keys = [k for k in targets if not k.startswith("Fib_")]

                    if fib_keys:
                        st.markdown("**Fibonacci Retracement (52W Swing)**")
                        fc1,fc2,fc3,fc4,fc5 = st.columns(5)
                        cols_fib = [fc1,fc2,fc3,fc4,fc5]
                        for j,k in enumerate(fib_keys):
                            v   = targets[k]
                            pct = round((v - price_now)/price_now*100,1) if price_now else 0
                            cols_fib[j%5].metric(k.replace("_"," "), f"{v:.2f} {cur}", f"{pct:+.1f}%")

                    if other_keys:
                        st.markdown("**Formation-Ziele**")
                        n = 3
                        rows_k = [other_keys[i:i+n] for i in range(0,len(other_keys),n)]
                        for rk in rows_k:
                            cols_k = st.columns(n)
                            for j,k in enumerate(rk):
                                v   = targets[k]
                                pct = round((v - price_now)/price_now*100,1) if price_now else 0
                                arrow = "🎯" if pct > 0 else "⚠️"
                                cols_k[j].metric(f"{arrow} {k.replace('_',' ')}", f"{v:.2f} {cur}", f"{pct:+.1f}%")
                else:
                    st.info("Keine Formations-Zielkurse ermittelbar.")

                # POC Chart
                st.divider()
                st.subheader("📊 Price-Volume Distribution (POC)")
                counts, edges = np.histogram(df["Close"].tail(200), bins=40)
                centers   = (edges[:-1]+edges[1:])/2
                poc_price = centers[np.argmax(counts)]
                fig_vp = go.Figure()
                fig_vp.add_trace(go.Bar(y=centers,x=counts,orientation="h",
                    marker=dict(color=counts,colorscale="Blues",showscale=False)))
                fig_vp.add_hline(y=poc_price, line_dash="solid", line_color="#ff4b4b", line_width=4,
                    annotation_text=f" 🎯 POC: {poc_price:.2f} {cur} ",
                    annotation_font=dict(color="white",size=18,family="Arial Black"),
                    annotation_bgcolor="#ff4b4b", annotation_position="bottom left")
                fig_vp.add_hline(y=data["Preis"], line_dash="dash", line_color="#f9d423", line_width=4,
                    annotation_text=f" 💵 {data['Preis']} {cur} ",
                    annotation_font=dict(color="black",size=18,family="Arial Black"),
                    annotation_bgcolor="#f9d423", annotation_position="top right")
                fig_vp.update_layout(template="plotly_dark",height=600,
                    paper_bgcolor="#0e1117",plot_bgcolor="#161b22",
                    xaxis=dict(title="Volumen",showgrid=False),
                    yaxis=dict(title=f"Preis ({cur})",showgrid=True,gridcolor="#2d333b"))
                st.plotly_chart(fig_vp, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — ROHSTOFFE & FUTURES
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.header("🛢️ Rohstoffe, Energie & Futures")
    st.caption("Futures-Daten via Yahoo Finance (Continuous Contracts). Preise in USD sofern nicht anders angegeben.")

    all_fg  = ["🌍 Alle Gruppen"] + get_all_futures_groups()
    sel_fg  = st.selectbox("Gruppe:", all_fg, key="fut_grp")
    fut_mode = st.radio("Ansicht:", ["📊 Übersicht / Scanner", "📈 Detail-Chart"], horizontal=True)

    if fut_mode == "📊 Übersicht / Scanner":
        if st.button("🔥 Futures Scan starten"):
            tickers_f = list(FUTURES_TICKERS.keys()) if sel_fg=="🌍 Alle Gruppen" else get_futures_by_group(sel_fg)
            fut_data, prog_f, stat_f = [], st.progress(0), st.empty()
            for i,t in enumerate(tickers_f):
                stat_f.text(f"Lade: {t}")
                res = get_futures_analysis(t)
                if res:
                    fut_data.append({
                        "Ticker":   t,
                        "Name":     res["Name"],
                        "Gruppe":   res["Gruppe"],
                        "Signal":   res["Signal"],
                        "Preis":    f"{res['Preis']} {res['Einheit']}",
                        "52W Hoch": res["52W_Hoch"],
                        "52W Tief": res["52W_Tief"],
                        "1W %":     f"{res['Perf_1W']:+.1f}%" if res['Perf_1W'] else "–",
                        "1M %":     f"{res['Perf_1M']:+.1f}%" if res['Perf_1M'] else "–",
                        "RSI":      res["RSI"],
                        "StochRSI": res["StochRSI"],
                        "CCI":      res["CCI"],
                        "Score":    res["Score"],
                    })
                prog_f.progress((i+1)/len(tickers_f))
            stat_f.empty()

            if fut_data:
                df_f = pd.DataFrame(fut_data).sort_values("Score", ascending=False)
                # Farbige HTML-Tabelle
                def _frow(r):
                    sv,sk,cv = r.get('StochRSI'),None,r.get('CCI')
                    sig = classify_signal(sv, sk, None, cv)
                    sc  = int(r.get('Score',0))
                    sc_c = {4:"#1a9e3f",3:"#27ae60",2:"#f39c12",1:"#7f8c8d"}.get(sc,"#999")
                    perf1w = r.get('1W %','–')
                    perf1m = r.get('1M %','–')
                    pw_c = "#1a9e3f" if perf1w and perf1w.startswith('+') else "#c0392b" if perf1w and perf1w.startswith('-') else "#888"
                    pm_c = "#1a9e3f" if perf1m and perf1m.startswith('+') else "#c0392b" if perf1m and perf1m.startswith('-') else "#888"
                    return (f"<tr>"
                            f"<td><b>{r['Ticker']}</b></td><td>{r['Name']}</td>"
                            f"<td><span style='background:#2d3250;color:#a0aec0;padding:2px 8px;border-radius:6px;font-size:11px'>{r['Gruppe']}</span></td>"
                            f"<td>{_sig_badge(sig)}</td>"
                            f"<td style='text-align:right;font-weight:700'>{r['Preis']}</td>"
                            f"<td style='color:{pw_c};text-align:center;font-weight:700'>{perf1w}</td>"
                            f"<td style='color:{pm_c};text-align:center;font-weight:700'>{perf1m}</td>"
                            f"<td style='text-align:center'>{_ind_badge(r.get('RSI'),35,65,'{:.1f}')}</td>"
                            f"<td style='text-align:center'>{_ind_badge(sv,0.2,0.8)}</td>"
                            f"<td style='text-align:center'>{_ind_badge(cv,-80,80,'{:.1f}',invert=True)}</td>"
                            f"<td style='text-align:center'><span style='background:{sc_c};color:#fff;padding:2px 8px;border-radius:10px;font-weight:700'>{sc}/4</span></td>"
                            f"</tr>")

                thead_f = """<thead style='background:#1e2235;color:#8892a4;font-size:11px;text-transform:uppercase'>
                  <tr><th style='padding:10px 8px'>Ticker</th><th>Name</th><th>Gruppe</th><th>Signal</th>
                  <th>Preis</th><th>1W</th><th>1M</th><th>RSI</th><th>StochRSI</th><th>CCI</th><th>Score</th></tr>
                </thead>"""
                tbody_f = "".join(_frow(r) for _,r in df_f.iterrows())
                st.markdown(f"<div style='overflow-x:auto'><table style='border-collapse:collapse;width:100%;font-size:13px;font-family:sans-serif'>{thead_f}<tbody>{tbody_f}</tbody></table></div>", unsafe_allow_html=True)
            else:
                st.warning("Keine Daten geladen.")

    else:
        # Detail-Chart eines Futures
        fut_options = {f"{v['name']} ({k})": k for k,v in FUTURES_TICKERS.items()}
        sel_fut_label = st.selectbox("Futures-Kontrakt:", list(fut_options.keys()), key="fut_det")
        sel_fut = fut_options[sel_fut_label]

        with st.spinner(f"Lade {sel_fut} …"):
            fdata = get_futures_analysis(sel_fut)

        if fdata and "df" in fdata:
            sig_f = fdata["Sig_Data"]
            unit  = fdata["Einheit"]

            fc1,fc2,fc3,fc4,fc5 = st.columns(5)
            fc1.markdown(_sig_badge(sig_f), unsafe_allow_html=True)
            fc2.metric("Preis", f"{fdata['Preis']} {unit}")
            fc3.metric("52W Hoch", f"{fdata['52W_Hoch']} {unit}")
            fc4.metric("52W Tief", f"{fdata['52W_Tief']} {unit}")
            fc5.metric("Score", f"{fdata['Score']}/4")

            fi1,fi2,fi3,fi4 = st.columns(4)
            fi1.markdown(f"**RSI** {_ind_badge(fdata['RSI'],35,65,'{:.1f}')}", unsafe_allow_html=True)
            fi2.markdown(f"**StochRSI** {_ind_badge(fdata['StochRSI'],0.2,0.8)}", unsafe_allow_html=True)
            fi3.markdown(f"**CCI** {_ind_badge(fdata['CCI'],-80,80,'{:.1f}',invert=True)}", unsafe_allow_html=True)
            fi4.markdown(f"**RVOL** <span style='font-size:14px'>{fdata['RVOL']}x</span>", unsafe_allow_html=True)

            dfp = fdata["df"]
            fig_fut = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                                    row_heights=[0.45,0.18,0.18,0.18],
                                    subplot_titles=("Kurs & Bollinger","Volumen","RSI","CCI"))
            fig_fut.add_trace(go.Scatter(x=dfp.index,y=dfp["BB_Lower"],name="BB-",line=dict(color="#00eeee",width=.8,dash="dot"),showlegend=False),row=1,col=1)
            fig_fut.add_trace(go.Scatter(x=dfp.index,y=dfp["BB_Upper"],name="Bollinger",fill="tonexty",fillcolor="rgba(0,238,238,0.05)",line=dict(color="#00eeee",width=.8,dash="dot")),row=1,col=1)
            fig_fut.add_trace(go.Scatter(x=dfp.index,y=dfp["EMA50"],name="EMA50",line=dict(color="#888",width=1.5,dash="dash")),row=1,col=1)
            fig_fut.add_trace(go.Scatter(x=dfp.index,y=dfp["Close"],name="Preis",line=dict(color="#ffff00",width=2.5)),row=1,col=1)
            vc = ["#ff4444" if r["Open"]>r["Close"] else "#00cc66" for _,r in dfp.iterrows()]
            fig_fut.add_trace(go.Bar(x=dfp.index,y=dfp["Volume"],name="Vol",marker_color=vc,opacity=.7),row=2,col=1)
            fig_fut.add_trace(go.Scatter(x=dfp.index,y=dfp["RSI"],name="RSI",line=dict(color="#00ffff",width=1.5)),row=3,col=1)
            for y,c in [(30,"#00ff00"),(70,"#ff0000")]: fig_fut.add_hline(y=y,line_color=c,line_width=1,row=3,col=1)
            fig_fut.add_trace(go.Scatter(x=dfp.index,y=dfp["CCI"],name="CCI",line=dict(color="#be94ff",width=2)),row=4,col=1)
            for y,c in [(-100,"#00ff00"),(100,"#ff0000")]: fig_fut.add_hline(y=y,line_color=c,row=4,col=1)
            fig_fut.update_layout(height=900,template="plotly_dark",paper_bgcolor="black",plot_bgcolor="black",
                                  margin=dict(l=10,r=10,t=40,b=10),hovermode="x unified")
            fig_fut.update_xaxes(showgrid=True,gridcolor="#222")
            fig_fut.update_yaxes(showgrid=True,gridcolor="#222")
            st.plotly_chart(fig_fut, use_container_width=True)
        else:
            st.error(f"Keine Daten für {sel_fut}.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — AUTOMATION
# ══════════════════════════════════════════════════════════════════════════════
with tab5:
    st.header("📅 Bericht-Versand & Automation")
    st.info("Der tägliche Report wird automatisch via **GitHub Actions** gesendet (täglich 06:24 UTC). Hier manueller Trigger.")
    if st.button("📧 Report jetzt senden"):
        if not st.session_state.results.empty:
            try:
                pw = st.secrets["DAILY_EMAIL_PASS"]
                st.success(send_mail_report(st.session_state.results, pw))
            except Exception as e:
                st.error(f"Fehler: {e}")
        else:
            st.warning("⚠️ Erst Tab 1 Scanner ausführen.")
