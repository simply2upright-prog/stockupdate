# app.py — Verbessert: Gruppen-Filter, Währungs-Labels, Streamlit-Deprecations behoben

import streamlit as st
import pandas as pd
import numpy as np
import base64
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from database import get_all_tickers, get_tickers_by_group, get_all_groups, get_currency
from engine import get_analysis, send_mail_report
from detail_engine import get_detail_analysis

# ─── PAGE CONFIG ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="In8Invest Scanner",
    page_icon="Icon in8invest web.png",
    layout="wide",
)

# ─── LOGO ──────────────────────────────────────────────────────────────────────
def _img_to_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

try:
    logo_b64 = _img_to_b64("Icon in8invest.png")
    st.markdown(
        f'<div style="text-align:left;margin-bottom:8px;">'
        f'<img src="data:image/png;base64,{logo_b64}" width="180">'
        f'</div>',
        unsafe_allow_html=True,
    )
except FileNotFoundError:
    pass

st.title("📊 Strategie Scanner")

# ─── SESSION STATE ─────────────────────────────────────────────────────────────
if "results" not in st.session_state:
    st.session_state.results = pd.DataFrame()

# ─── TABS ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "🚀 Scanner",
    "📊 Detail-Analyse",
    "📐 Formations-Check",
    "📅 Automation",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — SCANNER
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.header("Globaler Markt-Scanner")

    # Gruppen-Filter (NEU)
    all_groups = ["Alle Gruppen"] + get_all_groups()
    selected_group = st.selectbox("📂 Gruppe / Index:", all_groups, key="scan_group")

    col_btn, col_info = st.columns([1, 5])
    run_scan = col_btn.button("🔥 SCAN STARTEN", use_container_width=True)

    if run_scan:
        tickers = get_all_tickers() if selected_group == "Alle Gruppen" else get_tickers_by_group(selected_group)
        raw_data = []
        progress = st.progress(0)
        status   = st.empty()

        for i, ticker in enumerate(tickers):
            status.text(f"Scanne {i + 1}/{len(tickers)}: {ticker}")
            res = get_analysis(ticker)
            if res:
                raw_data.append(res)
            progress.progress((i + 1) / len(tickers))

        df = pd.DataFrame(raw_data)
        if not df.empty:
            df = df[df["Score"] >= 1].sort_values("Score", ascending=False).reset_index(drop=True)
            st.session_state.results = df
            status.success(f"✅ Scan fertig! {len(df)} Signale in {len(tickers)} geprüften Titeln.")
        else:
            status.warning("Keine Signale gefunden.")

    if not st.session_state.results.empty:
        st.dataframe(st.session_state.results, hide_index=True, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — DETAIL-ANALYSE
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.header("Analyse & Chart-Center")

    all_tickers = get_all_tickers()
    selected_ticker = st.selectbox(
        "Aktie zur Analyse auswählen:",
        options=all_tickers,
        help="Ticker-Symbol aus der Datenbank wählen oder suchen.",
        key="detail_ticker",
    )

    if selected_ticker:
        with st.spinner(f"Lade Analyse für {selected_ticker} …"):
            data = get_detail_analysis(selected_ticker)

        if data and "df" in data:
            currency = data["Währung"]
            score_color = "green" if data["Score"] >= 2 else ("orange" if data["Score"] == 1 else "red")

            st.markdown(f"### {data['Name']} ({selected_ticker}) | :{score_color}[Score {data['Score']}/3]")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric(
                "Aktueller Kurs",
                f"{data['Preis']:.2f} {currency}",
                delta=f"{data['Perf_Abs']:+.2f} {currency} ({data['Perf_Pct']:+.2f}%)",
            )
            c2.metric("52W Hoch",  f"{data['Hoch_365']:.2f} {currency}")
            c3.metric("52W Tief",  f"{data['Tief_365']:.2f} {currency}")
            c4.metric("Dividende", data["Div"])

            st.divider()

            df_plot = data["df"].tail(252)

            fig = make_subplots(
                rows=5, cols=1, shared_xaxes=True,
                vertical_spacing=0.03,
                row_heights=[0.40, 0.10, 0.15, 0.15, 0.15],
                subplot_titles=(
                    f"Kurs & Bollinger 200 (EMA)",
                    "Volumen",
                    "Stochastik (Fast 14 / Slow 7-SMA)",
                    "StochRSI (70)",
                    "CCI (20)",
                ),
            )

            # Bollinger
            fig.add_trace(go.Scatter(
                x=df_plot.index, y=df_plot["BB_Lower"],
                name="BB Unten", line=dict(color="#00eeee", width=0.8, dash="dot"), showlegend=False,
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=df_plot.index, y=df_plot["BB_Upper"],
                name="Bollinger Band", fill="tonexty", fillcolor="rgba(0,238,238,0.05)",
                line=dict(color="#00eeee", width=0.8, dash="dot"),
            ), row=1, col=1)

            # EMA 200
            fig.add_trace(go.Scatter(
                x=df_plot.index, y=df_plot["SMA200"],
                name="EMA 200", line=dict(color="#888888", width=1.5, dash="dash"),
            ), row=1, col=1)

            # Kurs
            fig.add_trace(go.Scatter(
                x=df_plot.index, y=df_plot["Close"],
                name="Kurs", line=dict(color="#ffff00", width=2.5),
            ), row=1, col=1)

            # Volumen
            v_colors = ["#ff4444" if r["Open"] > r["Close"] else "#00cc66" for _, r in df_plot.iterrows()]
            fig.add_trace(go.Bar(
                x=df_plot.index, y=df_plot["Volume"],
                name="Volumen", marker_color=v_colors, opacity=0.7,
            ), row=2, col=1)

            # Stochastik
            fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot["Stoch_Fast"], name="Fast", line=dict(color="#00ffff", width=1)), row=3, col=1)
            fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot["Stoch_Slow"], name="Slow", line=dict(color="#ff00ff", width=2)), row=3, col=1)
            fig.add_hline(y=10, line_color="#00ff00", line_width=1, row=3, col=1)
            fig.add_hline(y=90, line_color="#ff0000", line_width=1, row=3, col=1)

            # StochRSI
            fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot["StochRSI_70"], name="StochRSI", line=dict(color="#ffffff", width=1.5)), row=4, col=1)
            fig.add_hline(y=0.1, line_color="#00ff00", row=4, col=1)
            fig.add_hline(y=0.9, line_color="#ff0000", row=4, col=1)

            # CCI
            fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot["CCI_20"], name="CCI", line=dict(color="#be94ff", width=2)), row=5, col=1)
            fig.add_hline(y=-100, line_color="#00ff00", line_width=2, row=5, col=1)
            fig.add_hline(y=100,  line_color="#ff0000", line_width=1, row=5, col=1)

            fig.update_layout(
                height=1000, template="plotly_dark",
                paper_bgcolor="black", plot_bgcolor="black",
                margin=dict(l=10, r=10, t=50, b=10),
                showlegend=True, hovermode="x unified",
            )
            fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="#222222")
            fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="#222222")

            st.plotly_chart(fig, use_container_width=True)

            st.markdown("#### Fundamentale Kennzahlen")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("KGV (trailing)", data["KGV"])
            m2.metric("CCI Aktuell",    f"{data['CCI']:.1f}")
            m3.metric("StochRSI",       f"{data['StochRSI']:.3f}")
            m4.metric("Z-Score",        f"{data['Z_Score']:.2f}")

            if data["Patterns"]:
                st.markdown("#### 📐 Erkannte Muster")
                for p in data["Patterns"]:
                    st.info(f"📌 {p}")

        else:
            st.error(f"Keine Daten für **{selected_ticker}** gefunden. Bitte prüfe das Symbol.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — REVERSAL SCANNER / BODENBILDUNG
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.header("🛡️ Reversal-Scanner & Bodenbildung")

    mode = st.radio(
        "Modus:",
        ["🔍 Markt scannen", "🎯 Einzelne Aktie prüfen"],
        horizontal=True,
    )

    if mode == "🔍 Markt scannen":
        all_groups_t3 = ["Alle Gruppen"] + get_all_groups()
        scan_group_t3 = st.selectbox("Gruppe:", all_groups_t3, key="reversal_group")

        if st.button("🚀 Reversal-Scan starten"):
            tickers_t3 = (
                get_all_tickers()
                if scan_group_t3 == "Alle Gruppen"
                else get_tickers_by_group(scan_group_t3)
            )
            reversal_list = []
            prog = st.progress(0)
            txt  = st.empty()

            for i, t in enumerate(tickers_t3):
                txt.text(f"Scanne: {t}")
                res = get_detail_analysis(t)
                if res:
                    prob = 0
                    if res["Z_Score"] < -1.5: prob += 15
                    if res["Z_Score"] < -2.0: prob += 15
                    if res["RVOL"] > 1.3:     prob += 15
                    if res["RVOL"] > 2.0:     prob += 15
                    if "Selling Climax (Potenzielle Wende)" in res["Patterns"]: prob += 30
                    if "Doppelboden" in res["Patterns"]:  prob += 10

                    if prob >= 40:
                        reversal_list.append({
                            "Ticker":  t,
                            "Name":    res["Name"],
                            "Chance":  f"{min(prob, 100)}%",
                            "Z-Score": res["Z_Score"],
                            "RVOL":    res["RVOL"],
                            "Muster":  ", ".join(res["Patterns"]) if res["Patterns"] else "Akkumulation",
                            "Preis":   f"{res['Preis']} {res['Währung']}",
                        })
                prog.progress((i + 1) / len(tickers_t3))

            txt.empty()
            if reversal_list:
                df_rev = pd.DataFrame(reversal_list).sort_values("Chance", ascending=False)
                st.subheader(f"🔥 {len(df_rev)} Umkehr-Kandidaten")
                st.dataframe(df_rev, hide_index=True, use_container_width=True)
            else:
                st.warning("Keine Treffer gefunden.")

    else:
        # Einzelanalyse
        selected_t3 = st.selectbox("Aktie:", get_all_tickers(), key="reversal_single")

        if selected_t3:
            with st.spinner(f"Analysiere {selected_t3} …"):
                data = get_detail_analysis(selected_t3)

            if data and "df" in data:
                df = data["df"]
                currency = data["Währung"]

                prob_score = 0
                reasons    = []

                if "Selling Climax (Potenzielle Wende)" in data["Patterns"]:
                    prob_score += 40; reasons.append("🚨 SELLING CLIMAX erkannt")
                if data["Z_Score"] < -1.5: prob_score += 15
                if data["Z_Score"] < -2.0:
                    prob_score += 15; reasons.append(f"📏 Extrem überverkauft (Z-Score {data['Z_Score']})")
                if data["RVOL"] > 1.3: prob_score += 10
                if data["RVOL"] > 2.0:
                    prob_score += 20; reasons.append(f"📊 Hohes Volumen (RVOL {data['RVOL']})")
                if "Doppelboden" in data["Patterns"]:
                    prob_score += 15; reasons.append("📐 DOPPELBODEN erkannt")

                prob_score = min(prob_score, 100)

                col_left, col_right = st.columns(2)
                with col_left:
                    fig_gauge = go.Figure(go.Indicator(
                        mode="gauge+number",
                        value=prob_score,
                        number={"suffix": "%", "font": {"size": 70, "color": "#00d4ff", "family": "Arial Black"}},
                        title={"text": "Umkehr-Wahrscheinlichkeit", "font": {"size": 22, "color": "white"}},
                        gauge={
                            "axis":      {"range": [0, 100], "tickcolor": "white"},
                            "bar":       {"color": "#00d4ff"},
                            "bgcolor":   "#161b22",
                            "steps":     [{"range": [0, 45], "color": "#444"}, {"range": [45, 75], "color": "#666"}],
                            "threshold": {"line": {"color": "#00ff88", "width": 4}, "value": 75},
                        },
                    ))
                    fig_gauge.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)", font={"color": "white"}, height=400,
                    )
                    st.plotly_chart(fig_gauge, use_container_width=True)

                with col_right:
                    st.subheader("Analyse-Checkliste")
                    for r in reasons:
                        st.write(f"✅ {r}")
                    if   prob_score >= 75: st.success("🔥 MASSIVES UMKEHR-SIGNAL!")
                    elif prob_score >= 45: st.warning("⚠️ BODENBILDUNG LÄUFT …")
                    else:                  st.error("📉 KEIN BODEN ERKENNBAR.")

                # Volume-Profile / POC
                st.divider()
                st.subheader("📊 Price-Volume Distribution (POC)")
                hist_data   = df["Close"].tail(200)
                counts, edges = np.histogram(hist_data, bins=40)
                centers     = (edges[:-1] + edges[1:]) / 2
                poc_price   = centers[np.argmax(counts)]

                fig_vp = go.Figure()
                fig_vp.add_trace(go.Bar(
                    y=centers, x=counts, orientation="h",
                    marker=dict(color=counts, colorscale="Blues", showscale=False),
                ))
                fig_vp.add_hline(
                    y=poc_price, line_dash="solid", line_color="#ff4b4b", line_width=4,
                    annotation_text=f" 🎯 POC: {poc_price:.2f} {currency} ",
                    annotation_position="bottom left",
                    annotation_font=dict(color="white", size=20, family="Arial Black"),
                    annotation_bgcolor="#ff4b4b",
                )
                fig_vp.add_hline(
                    y=data["Preis"], line_dash="dash", line_color="#f9d423", line_width=5,
                    annotation_text=f" 💵 AKTUELL: {data['Preis']} {currency} ",
                    annotation_position="top right",
                    annotation_font=dict(color="black", size=20, family="Arial Black"),
                    annotation_bgcolor="#f9d423",
                )
                fig_vp.update_layout(
                    template="plotly_dark", height=650,
                    paper_bgcolor="#0e1117", plot_bgcolor="#161b22",
                    xaxis=dict(title="Handelsintensität", showgrid=False),
                    yaxis=dict(title=f"Preis ({currency})", showgrid=True, gridcolor="#2d333b"),
                    bargap=0.1,
                )
                st.plotly_chart(fig_vp, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — AUTOMATION
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.header("📅 Bericht-Versand & Automation")
    st.info("Der tägliche Report wird automatisch per GitHub Actions gesendet. Hier kannst du ihn manuell auslösen.")

    if st.button("📧 Report jetzt senden"):
        if not st.session_state.results.empty:
            try:
                pw     = st.secrets["DAILY_EMAIL_PASS"]
                status = send_mail_report(st.session_state.results, pw)
                st.success(status)
            except Exception as e:
                st.error(f"Fehler: {e}")
        else:
            st.warning("⚠️ Kein Scan-Ergebnis vorhanden. Bitte zuerst Tab 1 ausführen.")
