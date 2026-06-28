"""
Dashboard BMV — Streamlit
Correr: streamlit run app.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# Cargar variables de entorno desde .env si existe
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

# ─── Config ───────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="BMV Trading",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA = ROOT / "data"

# ─── Helpers de carga ─────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def load_json(name: str) -> dict:
    path = DATA / name
    if not path.exists():
        return {}
    return json.loads(path.read_text())


@st.cache_data(ttl=60)
def load_csv(name: str) -> pd.DataFrame:
    path = DATA / name
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def run_script(cmd: list[str]) -> tuple[int, str]:
    venv_python = str(ROOT / "venv" / "bin" / "python")
    result = subprocess.run(
        [venv_python] + cmd,
        capture_output=True, text=True, cwd=str(ROOT),
    )
    return result.returncode, result.stdout + result.stderr


# ─── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("📈 GBM Trading Hub")
    st.caption(f"Actualizado: {datetime.now().strftime('%H:%M:%S')}")

    # ── Capital global ─────────────────────────────────────────────────────────
    capital_global = st.number_input(
        "Capital disponible", value=50_000, step=10_000, min_value=5_000,
        help="Se divide equitativamente entre el top-5 del universo seleccionado",
    )
    st.caption(f"≈ ${capital_global/5:,.0f} por posición")

    st.divider()

    page = st.radio("Navegación", [
        "🏆  Ranking Mensual",
        "📰  Noticias & Gemini",
        "🎯  Señales de hoy",
        "👀  Monitor",
        "📋  Paper Trading",
        "🕹️  Simulador",
        "🏦  GBM Broker",
        "🧠  Modelo",
        "🗄️  Base de datos",
        "📖  Documentación",
    ])

    st.divider()
    if st.button("🔄 Actualizar datos", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA 0 — RANKING MENSUAL (multi-universo: BMV, USA, ETFs, Cripto, FIBRAs)
# ══════════════════════════════════════════════════════════════════════════════

if page.startswith("🏆"):
    from src.data.universes import UNIVERSES, UNIVERSE_ORDER

    st.title("🏆 Ranking Mensual — GBM Universe")
    st.caption("Modelo cross-seccional · rebalanceo ~20 días hábiles · long-only top-5")

    # ── Helper: carga señal de un universo ─────────────────────────────────────
    @st.cache_data(ttl=300)
    def load_universe_signal(slug: str) -> dict:
        p = ROOT / "data" / "signals" / f"{slug}.json"
        return json.loads(p.read_text()) if p.exists() else {}

    # ── Botón de regeneración (genera TODOS los universos) ──────────────────────
    col_gen1, col_gen2 = st.columns([4, 1])
    with col_gen2:
        gen_all = st.button("🔄 Generar señales", type="primary", use_container_width=True,
                            help="Entrena el modelo para todos los universos (~2 min)")
    if gen_all:
        with st.spinner("Generando señales para todos los universos (~2 min)..."):
            rc, out = run_script(["scripts/generate_all_signals.py",
                                  "--capital", str(int(capital_global))])
        if rc == 0:
            st.cache_data.clear()
            st.success("✅ Señales generadas para todos los universos")
            st.rerun()
        else:
            st.error("Error al generar señales")
            st.code(out[-2000:])

    # ── Tabs por clase de activo ────────────────────────────────────────────────
    tab_labels = list(UNIVERSE_ORDER)
    tabs = st.tabs(tab_labels)

    for tab, uname in zip(tabs, UNIVERSE_ORDER):
        cfg  = UNIVERSES[uname]
        slug = cfg["slug"]
        sig  = load_universe_signal(slug)

        with tab:
            if not sig:
                st.info(f"Sin señal para **{uname}**. Haz clic en **Generar señales** arriba.")

                # Botón para generar solo este universo
                if st.button(f"Generar solo {uname}", key=f"gen_{slug}"):
                    with st.spinner(f"Generando {uname}..."):
                        rc, out = run_script(["scripts/generate_all_signals.py",
                                              "--capital", str(int(capital_global)),
                                              "--universe", uname])
                    if rc == 0:
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.code(out[-1500:])
                continue

            if "error" in sig:
                st.error(f"⚠️ {sig['error']}")
                continue

            # ── Régimen del mercado ──────────────────────────────────────────
            mercado   = sig.get("mercado", {})
            reg_emoji = mercado.get("emoji", "⚪")
            reg_est   = mercado.get("estado", "—").upper()
            reg_desc  = mercado.get("descripcion", "")
            moneda_sym = "$" if cfg["moneda"] == "MXN" else "USD "
            monto_por  = sig.get("monto_por_nombre", capital_global / 5)

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("📅 Fecha", sig.get("fecha", "—"))
            m2.metric("🔢 Universo", f"{sig.get('n_tickers_analizados', '—')} tickers · {cfg['moneda']}")
            m3.metric(f"{reg_emoji} Mercado", reg_est)
            m4.metric("💰 Capital/posición", f"${monto_por:,.0f} {cfg['moneda']}")

            if mercado.get("estado") == "alcista":
                st.success(f"🟢 {reg_desc}")
            elif mercado.get("estado") == "bajista":
                st.warning(f"🔴 {reg_desc} — considera reducir posiciones")
            else:
                st.info(f"🟡 {reg_desc}")
            st.caption(f"*{cfg['descripcion']}*")

            # ── Consenso — tickers en top-5 de múltiples horizontes ──────────
            consensus = sig.get("consensus", [])
            strong    = [c for c in consensus if c["n_horizontes"] >= 3]
            if strong:
                st.divider()
                st.subheader("⭐ Picks de consenso (fuertes en 3-4 horizontes)")
                for c in strong:
                    sems = " · ".join(c["horizontes"])
                    n    = c["n_horizontes"]
                    bar  = "🟩" * n + "⬜" * (4 - n)
                    st.markdown(f"**{c['ticker']}** — {bar} aparece en {n}/4 horizontes ({sems})")

            st.divider()

            # ── Tabs por horizonte temporal ───────────────────────────────────
            by_horizon = sig.get("by_horizon", {})
            if not by_horizon:
                st.info("Señal generada con el motor antiguo. Regenera para ver multi-horizonte.")
                by_horizon = {"4s": {
                    "label": "4 semanas", "top5": sig.get("top5", []),
                    "evitar": sig.get("evitar", []),
                    "proximo_rebalanceo": sig.get("proximo_rebalanceo", "—"),
                    "universo_completo": sig.get("universo_completo", []),
                }}

            horizon_keys   = [h for h in ["1s", "2s", "3s", "4s"] if h in by_horizon]
            horizon_labels = [by_horizon[k]["label"] for k in horizon_keys]
            h_tabs = st.tabs([f"📅 {lbl}" for lbl in horizon_labels])

            for h_tab, hkey in zip(h_tabs, horizon_keys):
                hdata = by_horizon[hkey]

                with h_tab:
                    picks    = hdata.get("top5", [])
                    evitar   = hdata.get("evitar", [])
                    rebal    = hdata.get("proximo_rebalanceo", "—")
                    universo = hdata.get("universo_completo", [])

                    st.caption(f"⏰ Próximo rebalanceo: **{rebal}**")

                    # ── Picks ─────────────────────────────────────────────────
                    medals       = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
                    accion_colors = {"COMPRA FUERTE": "🟢", "COMPRA": "🟢",
                                     "ESPERA": "🟡", "EVITA": "🔴"}
                    sent_icons   = {"positivo": "📈", "neutral": "➡️", "negativo": "📉"}

                    for i, p in enumerate(picks):
                        precio     = p.get("precio_actual")
                        precio_str = f"{moneda_sym}{precio:,.2f}" if precio else "—"
                        accion_str = str(p.get("acciones_aprox", "")) or "fraccionado"
                        gem        = p.get("gemini", {})
                        gem_accion = gem.get("accion", "")
                        gem_icon   = accion_colors.get(gem_accion, "⚪")

                        # Marcar si es pick de consenso
                        tick_consensus = next((c for c in consensus if c["ticker"] == p["ticker"]), None)
                        consensus_badge = f" ⭐×{tick_consensus['n_horizontes']}" if tick_consensus and tick_consensus["n_horizontes"] >= 3 else ""

                        with st.expander(
                            f"{medals[i]}  **{p['ticker']}**{consensus_badge}  —  confianza {p['score_pct']}  "
                            f"|  {precio_str}  |  ≈ {accion_str} acciones/títulos  "
                            + (f"|  {gem_icon} **{gem_accion}**" if gem_accion else ""),
                            expanded=(i < 3),
                        ):
                            if gem.get("resumen"):
                                sent_ico = sent_icons.get(gem.get("sentimiento_news", ""), "")
                                st.markdown(f"### {gem_icon} {gem.get('resumen', '')}")
                                g1, g2 = st.columns(2)
                                with g1:
                                    if gem.get("catalizador"):
                                        st.success(f"**Catalizador:** {gem['catalizador']}")
                                with g2:
                                    if gem.get("riesgo"):
                                        st.warning(f"**Riesgo:** {gem['riesgo']}")
                                if gem.get("sentimiento_news"):
                                    st.caption(f"{sent_ico} Noticias: **{gem['sentimiento_news']}**")
                            else:
                                st.caption("_(Agrega GEMINI_API_KEY al .env para análisis Gemini)_")

                            st.divider()
                            cc1, cc2, cc3 = st.columns(3)
                            cc1.metric("Score", p["score_pct"])
                            cc2.metric(f"Monto ({cfg['moneda']})", f"${monto_por:,.0f}")
                            cc3.metric("Acciones", accion_str)

                            with st.expander("🔬 Señales técnicas", expanded=False):
                                for r in p.get("razones", []):
                                    st.markdown(f"- {r}")

                            noticias_p = p.get("noticias", [])
                            if noticias_p:
                                with st.expander(f"📰 {len(noticias_p)} noticias", expanded=False):
                                    for n in noticias_p:
                                        link  = n.get("link", "")
                                        title = n.get("title", "")
                                        pub   = n.get("publisher", "")
                                        ago   = n.get("ago", "")
                                        fuente = n.get("fuente", "")
                                        line   = f"- [{title}]({link})" if link else f"- {title}"
                                        st.markdown(f"{line} — *{pub}* {ago} `{fuente}`")

                    if evitar:
                        st.markdown(f"⛔ **Evitar este ciclo:** {' · '.join(evitar)}")

                    # ── Ranking completo ──────────────────────────────────────
                    if universo:
                        st.divider()
                        with st.expander(f"📊 Ranking completo ({len(universo)} instrumentos)", expanded=False):
                            df_u = pd.DataFrame(universo)
                            n    = len(df_u)
                            df_u["Score %"] = (df_u["score"] * 100).round(1).astype(str) + "%"
                            df_u["Barra"]   = df_u["score"].apply(lambda s: "█" * max(1, int(s * 25)))

                            def _color_rank(row):
                                if row["#"] <= 5:
                                    return ["background-color: #1a472a; color: white"] * len(row)
                                if row["#"] >= n - 3:
                                    return ["background-color: #4a1a1a; color: white"] * len(row)
                                return [""] * len(row)

                            st.dataframe(
                                df_u[["rank", "ticker", "Score %", "Barra"]].rename(
                                    columns={"rank": "#", "ticker": "Instrumento"}
                                ).style.apply(_color_rank, axis=1),
                                use_container_width=True, hide_index=True,
                                height=min(700, 38 * n + 40),
                            )

                    # ── Plan de acción ────────────────────────────────────────
                    if picks:
                        tickers_comprar = " + ".join(p["ticker"] for p in picks)
                        st.info(
                            f"**🗓️ Plan:** Hoy compra **{tickers_comprar}** — "
                            f"${monto_por:,.0f} {cfg['moneda']} c/u  |  "
                            f"Rebalanceo: {rebal}"
                        )

            st.caption(
                f"Modelo: LGBMRegressor · features rank-normalizadas"
                + (" · validación 2016-2024: +7.7% anual (7/9 años)" if slug == "bmv" else "")
            )

# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA — NOTICIAS & GEMINI por clase de activo
# ══════════════════════════════════════════════════════════════════════════════

if page.startswith("📰"):
    from src.api.gemini_analyst import NEWS_SOURCES, fetch_news_yfinance, fetch_news_for_ticker
    from src.data.universes import UNIVERSES, UNIVERSE_ORDER

    st.title("📰 Noticias & Gemini por universo")
    st.caption("Noticias en tiempo real por clase de activo · análisis ejecutivo con Gemini 2.5-flash")

    api_key_ok = bool(os.environ.get("GEMINI_API_KEY"))
    if not api_key_ok:
        st.warning("⚠️ **GEMINI_API_KEY** no configurada. Agrega tu key al `.env` para análisis ejecutivo. "
                   "Puedes obtenerla gratis en [aistudio.google.com](https://aistudio.google.com/app/apikey).", icon="⚠️")

    news_tabs = st.tabs(list(UNIVERSE_ORDER))

    for tab, uname in zip(news_tabs, UNIVERSE_ORDER):
        cfg     = UNIVERSES[uname]
        sources = NEWS_SOURCES.get(uname, {})

        with tab:
            st.caption(f"*{cfg['descripcion']}*")

            # ── Fuentes de noticias disponibles ─────────────────────────────
            st.subheader("🔌 Fuentes de noticias")
            fuentes = sources.get("fuentes", [])
            integradas = set(sources.get("integrado", []))
            proximas   = set(sources.get("proximos", []))

            for f in fuentes:
                nombre = f["nombre"]
                estado = "✅ Activa" if nombre in integradas else ("🔜 Próxima" if nombre in proximas else "⬜ Disponible")
                st.markdown(
                    f"**{nombre}** — {estado} &nbsp;·&nbsp; {f['tipo']} &nbsp;·&nbsp; "
                    f"💰 {f['costo']} &nbsp;·&nbsp; {f['cobertura']}"
                )

            st.divider()

            # ── Noticias live por ticker (top-10 del universo) ───────────────
            st.subheader("📡 Noticias en tiempo real")
            tickers = cfg["tickers"]
            sample  = list(tickers.items())[:10]   # primeros 10 para no saturar

            if st.button(f"Cargar noticias ({uname})", key=f"news_{cfg['slug']}"):
                with st.spinner("Obteniendo noticias..."):
                    all_news = {}
                    for name, sym in sample:
                        news = fetch_news_for_ticker(name, sym, cfg["slug"], max_items=3)
                        if news:
                            all_news[name] = news

                if not all_news:
                    st.info("No se encontraron noticias recientes para este universo.")
                else:
                    for name, news_list in all_news.items():
                        with st.expander(f"**{name}** — {len(news_list)} artículos"):
                            for n in news_list:
                                link  = n.get("link", "")
                                title = n.get("title", "")
                                pub   = n.get("publisher", "")
                                ago   = n.get("ago", "")
                                if link:
                                    st.markdown(f"- [{title}]({link}) — *{pub}* {ago}")
                                else:
                                    st.markdown(f"- {title} — *{pub}* {ago}")

            st.divider()

            # ── Análisis ejecutivo Gemini en tiempo real ─────────────────────
            st.subheader("🤖 Análisis Gemini en tiempo real")
            ticker_input = st.selectbox(
                "Selecciona un instrumento", list(tickers.keys()),
                key=f"sel_{cfg['slug']}"
            )
            if st.button("Analizar con Gemini", key=f"analyze_{cfg['slug']}", disabled=not api_key_ok):
                sym = tickers[ticker_input]
                with st.spinner(f"Gemini analizando {ticker_input}..."):
                    from src.api.gemini_analyst import analyze_ticker, fetch_news_for_ticker
                    news = fetch_news_for_ticker(ticker_input, sym, cfg["slug"], max_items=5)
                    result = analyze_ticker(
                        ticker=ticker_input, sym=sym, rank=1, score=0.5,
                        razones=[], universe_name=uname, news=news,
                    )

                if result:
                    accion = result.get("accion", "")
                    color  = {"COMPRA FUERTE": "success", "COMPRA": "success",
                              "ESPERA": "warning", "EVITA": "error"}.get(accion, "info")
                    getattr(st, color)(f"**{accion}** — {result.get('resumen', '')}")
                    c1, c2 = st.columns(2)
                    c1.success(f"**Catalizador:** {result.get('catalizador', '—')}")
                    c2.warning(f"**Riesgo:** {result.get('riesgo', '—')}")
                    st.caption(f"Noticias: {result.get('sentimiento_news','—')}")
                else:
                    st.error("No se pudo obtener análisis de Gemini.")


# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA 1 — SEÑALES DE HOY
# ══════════════════════════════════════════════════════════════════════════════

if page.startswith("🎯"):
    st.title("Señales de hoy")

    signals_data = load_json("signals_today.json")

    if not signals_data:
        st.warning("No hay señales generadas. Corre el modelo primero.")
        capital = st.number_input("Capital (MXN)", value=10_000, step=5_000)
        if st.button("🚀 Generar señales ahora", type="primary"):
            with st.spinner("Entrenando modelo y generando señales (~30 seg)..."):
                rc, out = run_script(["scripts/generate_signals.py", "--capital", str(int(capital))])
            st.code(out[-3000:])
            st.cache_data.clear()
            st.rerun()
        st.stop()

    meta = signals_data.get("meta", {})
    signals = signals_data.get("signals", [])
    summary = signals_data.get("summary", {})
    candidates = signals_data.get("all_candidates", [])
    regime_data = signals_data.get("regime", {})

    # Header metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Señales", len(signals))
    col2.metric("Capital invertido", f"{summary.get('pct_invested', 0):.1f}%")
    col3.metric("Capital en riesgo", f"{summary.get('pct_at_risk', 0):.2f}%")
    col4.metric("P(↑) promedio", f"{summary.get('avg_p_up', 0)*100:.1f}%")
    col5.metric("Generado", meta.get("date", "—")[-5:])

    # Régimen HMM
    if regime_data:
        st.divider()
        r_state = regime_data.get("state", "unknown")
        r_proba = regime_data.get("proba", {})
        r_icon  = {"bull": "🟢", "lateral": "🟡", "bear": "🔴"}.get(r_state, "⚪")
        rc1, rc2, rc3, rc4 = st.columns(4)
        rc1.metric("Régimen HMM", f"{r_icon} {r_state.upper()}")
        rc2.metric("P(bull)",    f"{r_proba.get('bull',0)*100:.0f}%")
        rc3.metric("P(lateral)", f"{r_proba.get('lateral',0)*100:.0f}%")
        rc4.metric("P(bear)",    f"{r_proba.get('bear',0)*100:.0f}%")
        if r_state == "bear":
            st.warning("Mercado en régimen BEAR — el modelo eleva el umbral a 0.56. Solo las señales más fuertes se muestran.")
        elif r_state == "bull":
            st.success("Mercado en régimen BULL — condiciones favorables para operar.")
        model_label = meta.get("model", "WoE+LR+LightGBM")
        st.caption(f"Modelo: **{model_label}**  ·  Umbral P: {meta.get('threshold', 0.53):.2f}  ·  Horizonte: {meta.get('horizon', 5)} días")

    # ── Contexto de mercado en vivo (DataBursátil) ─────────────────────────────
    mctx = signals_data.get("market_context", {})
    if mctx:
        st.divider()
        st.subheader("🌐 Contexto de mercado en vivo")
        st.caption("Datos en tiempo real de DataBursátil — información nueva para tu decisión (no entra al modelo, es contexto).")

        rates   = mctx.get("rates", {})
        indices = mctx.get("indices", {})
        mc1, mc2, mc3, mc4 = st.columns(4)
        tobj = rates.get("Tasa_Objetivo", {}).get("tasa")
        tiie = rates.get("TIIE28", {}).get("tasa")
        ipc  = indices.get("IPC", {})
        spx  = indices.get("SP500", {})
        mc1.metric("Tasa objetivo Banxico", f"{tobj}%" if tobj is not None else "—")
        mc2.metric("TIIE 28d", f"{tiie}%" if tiie is not None else "—")
        mc3.metric("IPC", f"{ipc.get('nivel','—')}",
                   delta=f"{ipc.get('cambio_pct')}%" if ipc.get('cambio_pct') is not None else None)
        mc4.metric("S&P 500", f"{spx.get('nivel','—')}",
                   delta=f"{spx.get('cambio_pct')}%" if spx.get('cambio_pct') is not None else None)

        sent = mctx.get("sentiment")
        if sent:
            score = sent.get("score", 0)
            s_icon = "🟢" if score > 0.2 else "🔴" if score < -0.2 else "🟡"
            st.info(f"{s_icon} **Sentimiento de noticias (LLM): {score:+.2f}** — {sent.get('etiqueta','')}. {sent.get('resumen','')}")
        else:
            st.caption("💡 Sentimiento Gemini desactivado. Agrega `GEMINI_API_KEY` al `.env` (obtén tu key gratis en [aistudio.google.com](https://aistudio.google.com/app/apikey)).")

        news = mctx.get("news", [])
        if news:
            with st.expander(f"📰 {mctx.get('n_news', len(news))} noticias del día"):
                for n in news[:15]:
                    titulo = n.get("titulo") or "—"
                    st.markdown(f"- **[{n.get('categoria','')}]** {titulo}")

    st.divider()

    # Botón para regenerar
    capital = st.sidebar.number_input("Capital (MXN)", value=int(meta.get("capital", 10_000)), step=5_000)
    if st.sidebar.button("🔄 Regenerar señales", type="primary", use_container_width=True):
        with st.spinner("Entrenando modelo (~30 seg)..."):
            rc, out = run_script(["scripts/generate_signals.py", "--capital", str(int(capital))])
        st.cache_data.clear()
        st.rerun()

    # Tabla de señales
    st.subheader(f"{len(signals)} señales de compra — lunes {meta.get('date', '')[:10]}")

    for s in signals:
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
            c1.markdown(f"### {s['ticker']}")
            c1.caption(s.get("reason", ""))
            c2.metric("P(subida 5d)", f"{s['p_up']*100:.1f}%")
            c3.metric("Entry → Stop", f"${s['entry']:.2f} → ${s['stop']:.2f}")
            c4.metric("T1 / T2", f"${s['target_1']:.2f} / ${s['target_2']:.2f}")
            c5.metric("Capital / Acciones", f"${s['capital_mxn']:,.0f} / {s['shares']}")

            # Price bar
            lo, hi = s["stop"] * 0.985, s["target_2"] * 1.015
            fig = go.Figure()
            fig.add_shape(type="rect", x0=lo, x1=s["entry"], y0=0, y1=1,
                          fillcolor="rgba(239,68,68,0.15)", line_width=0)
            fig.add_shape(type="rect", x0=s["entry"], x1=hi, y0=0, y1=1,
                          fillcolor="rgba(34,197,94,0.12)", line_width=0)
            for x, label, color in [
                (s["stop"],     f"SL ${s['stop']:.2f}",     "#ef4444"),
                (s["entry"],    f"Entry ${s['entry']:.2f}",  "#f59e0b"),
                (s["target_1"], f"T1 ${s['target_1']:.2f}", "#86efac"),
                (s["target_2"], f"T2 ${s['target_2']:.2f}", "#22c55e"),
            ]:
                fig.add_vline(x=x, line_color=color, line_width=2.5,
                              annotation_text=label,
                              annotation_font_size=11,
                              annotation_position="top")
            atr_val  = s.get("atr", 0)
            rr_ratio = s.get("rr_ratio", 0)
            fig.update_layout(
                height=100,
                margin=dict(l=10, r=10, t=35, b=10),
                xaxis=dict(showgrid=False, zeroline=False,
                           range=[lo, hi],
                           tickformat="$.2f"),
                yaxis=dict(visible=False),
                plot_bgcolor="rgba(15,15,25,0.6)",
                paper_bgcolor="rgba(0,0,0,0)",
                annotations=[dict(
                    x=hi, y=0.5, xanchor="right", yanchor="middle",
                    text=f"ATR ${atr_val:.2f}  |  R/R {rr_ratio:.1f}x",
                    font=dict(size=10, color="#9ca3af"),
                    showarrow=False,
                )],
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # Ranking completo
    st.divider()
    st.subheader("Ranking de los 19 tickers")
    df_cands = pd.DataFrame(candidates)
    if not df_cands.empty:
        df_cands["pct"] = (df_cands["p_up"] * 100).round(1)
        fig = px.bar(df_cands, x="pct", y="ticker", orientation="h",
                     color="pct", color_continuous_scale=["#ef4444","#f59e0b","#22c55e"],
                     labels={"pct": "P(subida 5d) %", "ticker": ""},
                     range_color=[44, 65])
        fig.add_vline(x=meta.get("threshold", 0.53)*100, line_dash="dash",
                      line_color="white", annotation_text="Umbral")
        fig.update_layout(height=480, showlegend=False,
                          coloraxis_showscale=False,
                          plot_bgcolor="rgba(0,0,0,0)",
                          paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA 2 — MONITOR
# ══════════════════════════════════════════════════════════════════════════════

elif page.startswith("👀"):
    st.title("Monitor de posiciones")

    auto_refresh = st.sidebar.toggle("Auto-refresh 60s", value=False)
    if auto_refresh:
        import time
        st.sidebar.caption("Actualizando en vivo...")

    state_data = load_json("monitor_state.json")
    positions = state_data if isinstance(state_data, list) else []

    if not positions:
        st.info("No hay posiciones activas. Genera señales y corre el monitor primero.")
        if st.button("▶ Iniciar monitor (una vez)"):
            with st.spinner("Consultando precios..."):
                rc, out = run_script(["scripts/monitor_intraday.py", "--once"])
            st.code(out)
            st.cache_data.clear()
            st.rerun()
        st.stop()

    # Resumen
    open_pos = [p for p in positions if p["state"] in ("OPEN","T1_HIT")]
    total_pnl = sum(p.get("pnl_mxn", 0) for p in positions)
    total_inv = sum(p.get("capital_mxn", 0) for p in open_pos)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Posiciones abiertas", len(open_pos))
    c2.metric("Capital invertido", f"${total_inv:,.0f}")
    c3.metric("PnL total", f"${total_pnl:+,.0f}",
              delta=f"{total_pnl/total_inv*100:+.2f}%" if total_inv else None)
    c4.metric("Última actualización", load_json("monitor_state.json") and
              positions[0].get("opened_at", "—")[:10] or "—")

    st.divider()

    # Tabla de posiciones
    rows = []
    for p in positions:
        px_last = p.get("price_last", p.get("entry", 0))
        rows.append({
            "Ticker":   p["ticker"],
            "Estado":   p["state"],
            "Precio":   px_last,
            "Entry":    p["entry"],
            "Stop":     p["stop_current"],
            "T1":       p["target_1"],
            "T2":       p["target_2"],
            "PnL %":    round(p.get("pnl_pct", 0), 2),
            "PnL MXN":  round(p.get("pnl_mxn", 0), 0),
            "P(↑)":     f"{p.get('p_up',0)*100:.0f}%",
        })

    df = pd.DataFrame(rows)
    st.dataframe(
        df.style
          .map(lambda v: "color: #22c55e" if isinstance(v, (int,float)) and v > 0
                        else "color: #ef4444" if isinstance(v, (int,float)) and v < 0
                        else "", subset=["PnL %","PnL MXN"])
          .format({"Precio":"${:.2f}","Entry":"${:.2f}","Stop":"${:.2f}",
                   "T1":"${:.2f}","T2":"${:.2f}","PnL MXN":"${:,.0f}",
                   "PnL %":"{:+.2f}%"}),
        use_container_width=True, hide_index=True,
    )

    if st.button("🔄 Actualizar precios ahora", type="primary"):
        with st.spinner("Consultando precios..."):
            rc, out = run_script(["scripts/monitor_intraday.py", "--once"])
        st.code(out[-2000:])
        st.cache_data.clear()
        st.rerun()

    # Log de alertas
    log_path = DATA / "monitor_log.jsonl"
    if log_path.exists() and log_path.stat().st_size > 0:
        st.divider()
        st.subheader("Log de alertas")
        alerts = [json.loads(l) for l in log_path.read_text().strip().split("\n") if l]
        df_alerts = pd.DataFrame(alerts)
        st.dataframe(df_alerts, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA 3 — PAPER TRADING
# ══════════════════════════════════════════════════════════════════════════════

elif page.startswith("📋"):
    st.title("Paper Trading")

    pt_data = load_json("paper_trades.json")
    trades  = pt_data.get("trades", [])
    capital = pt_data.get("initial_capital", 100_000)
    eq_curve = pt_data.get("equity_curve", [])

    closed  = [t for t in trades if t["status"] not in ("PENDING","OPEN","T1_HIT","CANCELLED")]
    open_t  = [t for t in trades if t["status"] in ("OPEN","T1_HIT","PENDING")]

    # Scorecard
    n = len(closed)
    wins = [t for t in closed if t["pnl_mxn"] > 0]
    total_pnl = sum(t["pnl_mxn"] for t in closed)

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Trades cerrados", n)
    c2.metric("Win rate", f"{len(wins)/n*100:.1f}%" if n else "—")
    c3.metric("PnL total", f"${total_pnl:+,.0f}" if n else "—",
              delta=f"{total_pnl/capital*100:+.2f}%" if n else None)
    c4.metric("Capital actual", f"${capital+total_pnl:,.0f}")
    c5.metric("Posiciones abiertas", len(open_t))

    # Acciones
    st.divider()
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("📥 Init — cargar señales de hoy", use_container_width=True):
            with st.spinner("Registrando señales..."):
                rc, out = run_script(["scripts/paper_trading.py", "init"])
            st.code(out); st.cache_data.clear(); st.rerun()
    with col_b:
        if st.button("⚖️ Settle — cerrar semana", use_container_width=True, type="primary"):
            with st.spinner("Descargando OHLC real y simulando (~20 seg)..."):
                rc, out = run_script(["scripts/paper_trading.py", "settle"])
            st.code(out); st.cache_data.clear(); st.rerun()
    with col_c:
        if st.button("📊 Report completo", use_container_width=True):
            rc, out = run_script(["scripts/paper_trading.py", "report"])
            st.code(out)

    # Posiciones abiertas
    if open_t:
        st.subheader("Posiciones abiertas / pendientes")
        rows = [{
            "Ticker": t["ticker"], "Estado": t["status"],
            "P(↑)": f"{t['p_up']*100:.0f}%",
            "Entry": t["entry_price"], "Stop": t["stop_current"],
            "T1": t["target_1"], "T2": t["target_2"],
            "Capital": f"${t['capital_invested']:,.0f}",
            "PnL MXN": t["pnl_mxn"],
        } for t in open_t]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Curva de equity
    if eq_curve:
        st.subheader("Curva de equity")
        df_eq = pd.DataFrame(eq_curve)
        df_eq["date"] = pd.to_datetime(df_eq["date"]).dt.strftime("%b %d, %Y")
        df_eq["equity_k"] = df_eq["equity"] / 1000
        pnl_total   = df_eq["equity"].iloc[-1] - capital if len(df_eq) > 1 else 0
        pnl_pct     = pnl_total / capital * 100
        delta_color = "normal" if pnl_total >= 0 else "inverse"

        col_e1, col_e2, col_e3 = st.columns(3)
        col_e1.metric("Capital inicial", f"${capital:,.0f}")
        col_e2.metric("Capital actual",  f"${df_eq['equity'].iloc[-1]:,.0f}",
                      delta=f"{pnl_pct:+.2f}%" if len(df_eq) > 1 else None)
        col_e3.metric("PnL acumulado",   f"${pnl_total:+,.0f}" if len(df_eq) > 1 else "—")

        fig = px.area(df_eq, x="date", y="equity_k",
                      labels={"equity_k": "Capital (k MXN)", "date": ""},
                      color_discrete_sequence=["#22c55e"])
        fig.add_hline(y=capital/1000, line_dash="dash", line_color="#9ca3af",
                      annotation_text=f"Inicial ${capital/1000:.0f}k",
                      annotation_font_color="#9ca3af")
        fig.update_traces(fill="tozeroy", fillcolor="rgba(34,197,94,0.1)")
        fig.update_layout(
            height=280,
            xaxis=dict(tickangle=-30, nticks=10),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)

    # Historial
    if closed:
        st.subheader("Historial de trades cerrados")
        rows = [{
            "Semana": t.get("signal_date",""),
            "Ticker": t["ticker"],
            "Estado": t["status"],
            "P(↑) pred.": f"{t['p_up']*100:.0f}%",
            "Entry": f"${t['entry_price']:.2f}",
            "Exit": f"${t.get('exit_price',0):.2f}",
            "PnL MXN": t["pnl_mxn"],
            "PnL %": f"{t['pnl_pct']:+.2f}%",
            "Modelo acertó": "✅" if t.get("model_correct") else "❌",
        } for t in sorted(closed, key=lambda x: x.get("exit_date",""))]
        df_hist = pd.DataFrame(rows)
        st.dataframe(df_hist, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA 4 — SIMULADOR HISTÓRICO
# ══════════════════════════════════════════════════════════════════════════════

elif page.startswith("🕹️"):
    st.title("Simulador — EnsembleModel en cualquier semana histórica")
    st.caption("Entrena el Ensemble v1 con datos hasta la fecha elegida, genera señales y evalúa el resultado real de esa semana.")

    # ── Controles ─────────────────────────────────────────────────────────────
    col_ctrl1, col_ctrl2, col_ctrl3 = st.columns([3, 1, 1])

    # Generar viernes de los últimos 2 años
    import datetime as _dt
    _today   = _dt.date.today()
    _fridays = []
    _d       = _today - _dt.timedelta(days=(_today.weekday() - 4) % 7)
    while len(_fridays) < 104:
        _fridays.append(str(_d))
        _d -= _dt.timedelta(weeks=1)

    selected_date = col_ctrl1.selectbox(
        "Viernes de señales (datos hasta esa fecha)",
        options=_fridays,
        index=1,
        help="El modelo se entrena solo con datos hasta este día. Simula el proceso real de trading."
    )
    sim_capital = col_ctrl2.number_input("Capital MXN", value=5_000, step=1_000, min_value=1_000)

    run_btn = col_ctrl3.button("▶ Simular", type="primary", use_container_width=True)

    st.divider()

    # ── Caché por fecha+capital ────────────────────────────────────────────────
    cache_key = f"sim_{selected_date}_{int(sim_capital)}"
    if run_btn or cache_key not in st.session_state:
        with st.spinner(f"Entrenando EnsembleModel con datos hasta {selected_date}... (~30 seg)"):
            try:
                from scripts.simulate_week import run_simulation
                result = run_simulation(
                    signal_date=selected_date,
                    capital=sim_capital,
                    verbose=False,
                )
                st.session_state[cache_key] = result
            except Exception as _e:
                st.error(f"Error en simulación: {_e}")
                st.stop()

    result = st.session_state.get(cache_key)
    if not result:
        st.info("Haz clic en '▶ Simular' para correr el EnsembleModel en esa semana.")
        st.stop()

    sim_signals = result.get("signals", [])
    sim_results = result.get("results", [])
    sim_summary = result.get("summary", {})
    sim_regime  = result.get("regime", {})
    sim_preds   = result.get("all_preds", [])

    # ── Cabecera de la semana ──────────────────────────────────────────────────
    r_state = sim_regime.get("state", "unknown")
    r_proba = sim_regime.get("proba", {})
    r_icon  = {"bull": "🟢", "lateral": "🟡", "bear": "🔴"}.get(r_state, "⚪")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Semana",   selected_date)
    c2.metric("Señales",  f"{len(sim_signals)} generadas")
    c3.metric("Trades",   f"{len(sim_results)} ejecutados")
    c4.metric("Régimen",  f"{r_icon} {r_state.upper()}")
    c5.metric("Win rate", f"{sim_summary.get('win_rate',0)*100:.0f}%")

    if r_state == "bear":
        st.warning(f"Semana en régimen BEAR — umbral de señales elevado a 0.56")
    elif r_state == "bull":
        st.success(f"Semana en régimen BULL — condiciones favorables")

    st.divider()

    # ── Ranking de predicciones ────────────────────────────────────────────────
    with st.expander(f"Ranking de los {len(sim_preds)} tickers — predicciones del EnsembleModel", expanded=False):
        df_rank = pd.DataFrame(sim_preds)
        if not df_rank.empty:
            df_rank["señal"]   = (df_rank["p_up"] >= 0.53).map({True: "🎯 Señal", False: "—"})
            df_rank["P(↑)"]    = (df_rank["p_up"]*100).round(1).astype(str) + "%"
            df_rank["precio"]  = df_rank["price"].apply(lambda x: f"${x:.2f}")
            st.dataframe(df_rank[["ticker","P(↑)","precio","señal"]],
                         use_container_width=True, hide_index=True)

    # ── Sin señales ────────────────────────────────────────────────────────────
    if len(sim_signals) == 0:
        max_p = max((p["p_up"] for p in sim_preds), default=0)
        best  = sim_preds[0]["ticker"] if sim_preds else "—"
        st.info(f"""
**El EnsembleModel no generó señales esa semana.**

La probabilidad máxima fue **{max_p*100:.1f}%** ({best}), por debajo del umbral de señal.

Esto significa que el modelo detectó condiciones poco favorables — quedarse en efectivo fue la decisión correcta según el Ensemble v1.
""")
        st.stop()

    # ── Cards de señales + resultado ──────────────────────────────────────────
    st.subheader(f"Simulación trade a trade — lunes siguiente a {selected_date}")
    st.caption(f"*EnsembleModel v1 (WoE+LR+LightGBM) · Régimen {r_state} · Capital ${sim_capital:,}*")

    for r in sim_results:
        won  = r["pnl_net"] > 0
        icon = "✅" if won else "❌"
        with st.container(border=True):
            h1, h2, h3, h4, h5 = st.columns([2, 1, 1, 1, 1])
            h1.markdown(f"### {icon} {r['ticker']}")
            h1.caption(f"P(↑) ensemble: **{r['p_up']*100:.1f}%**")
            h2.metric("PnL neto", f"${r['pnl_net']:+,.0f}", delta=f"{r['pnl_pct']:+.1f}%")
            h3.metric("Entrada real", f"${r['entry_actual']:.2f}")
            h4.metric("Salida", f"${r['exit_price']:.2f}")
            h5.metric("Razón", r["exit_reason"])

            entry_sig = next((s["entry"] for s in sim_signals if s["ticker"] == r["ticker"]), r["entry_actual"])
            st.markdown(f"""
**Viernes {selected_date}** — señal del EnsembleModel:
`Entry: ${entry_sig:.2f}  Stop: ${r['stop']:.2f}  T1: ${r['target_1']:.2f}  T2: ${r['target_2']:.2f}`

**{sim_summary.get('entry_date','lunes')} (lunes)** — apertura real: **${r['entry_actual']:.2f}**  ·  {r['shares']} acc = **${r['invested']:,.0f}**

**Rango semana:** ${r['week_low']:.2f} mín  /  ${r['week_high']:.2f} máx

**Resultado** → {r['exit_reason']} a **${r['exit_price']:.2f}**  ·  PnL neto: **${r['pnl_net']:+,.0f} MXN**
""")

            # Gráfica de velas con niveles
            from src.data.store import get as _store_get2
            _full = _store_get2(r["ticker"])
            if _full is not None:
                _entry_ts  = pd.Timestamp(sim_summary.get("entry_date", selected_date))
                _settle_ts = pd.Timestamp(sim_summary.get("settle_date", selected_date))
                _week_ohlc = _full[(_full.index >= _entry_ts) & (_full.index <= _settle_ts)].head(5)
                if not _week_ohlc.empty:
                    _fig = go.Figure()
                    _fig.add_trace(go.Candlestick(
                        x=_week_ohlc.index.strftime("%a %d"),
                        open=_week_ohlc["Open"], high=_week_ohlc["High"],
                        low=_week_ohlc["Low"],   close=_week_ohlc["Close"],
                        increasing_fillcolor="#22c55e", decreasing_fillcolor="#ef4444",
                        increasing_line_color="#22c55e", decreasing_line_color="#ef4444",
                        name=r["ticker"],
                    ))
                    for _y, _lbl, _clr in [
                        (r["stop"],         "Stop",   "#ef4444"),
                        (r["entry_actual"], "Entry",  "#f59e0b"),
                        (r["target_1"],     "T1",     "#86efac"),
                        (r["target_2"],     "T2",     "#22c55e"),
                    ]:
                        _fig.add_hline(y=_y, line_color=_clr, line_dash="dash", line_width=1.5,
                                       annotation_text=f"{_lbl} ${_y:.2f}",
                                       annotation_font_color=_clr, annotation_font_size=10)
                    _fig.update_layout(
                        height=240, xaxis_rangeslider_visible=False,
                        margin=dict(l=10, r=80, t=10, b=10),
                        plot_bgcolor="rgba(10,10,20,0.8)", paper_bgcolor="rgba(0,0,0,0)",
                        xaxis=dict(showgrid=False),
                        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
                    )
                    st.plotly_chart(_fig, use_container_width=True, config={"displayModeBar": False})

    # ── Scorecard ─────────────────────────────────────────────────────────────
    if sim_results:
        st.divider()
        st.subheader("Scorecard")

        total_pnl   = sim_summary.get("total_pnl", 0)
        total_inv   = sim_summary.get("total_inv", 0)
        n_wins      = sim_summary.get("n_wins", 0)
        n_trades    = sim_summary.get("n_trades", 0)
        ret_capital = sim_summary.get("return_pct", 0)

        sc1, sc2, sc3, sc4, sc5 = st.columns(5)
        sc1.metric("Trades",            str(n_trades))
        sc2.metric("Ganadores",         f"{n_wins}/{n_trades}",
                   delta=f"{n_wins/n_trades*100:.0f}% win rate" if n_trades else "0%")
        sc3.metric("PnL total",         f"${total_pnl:+,.0f}")
        sc4.metric("Retorno vs capital",f"{ret_capital:+.2f}%")
        sc5.metric("Capital final",     f"${sim_summary.get('final_capital',sim_capital):,.0f}")

        if n_trades > 0:
            df_sc = pd.DataFrame([{
                "Ticker": r["ticker"], "PnL": round(r["pnl_net"], 0), "Salida": r["exit_reason"]
            } for r in sim_results])
            _max_abs = max(abs(df_sc["PnL"].min()), df_sc["PnL"].max(), 1)
            _fig_sc  = px.bar(df_sc, x="Ticker", y="PnL", color="PnL",
                              color_continuous_scale=["#ef4444","#374151","#22c55e"],
                              range_color=[-_max_abs, _max_abs],
                              text="PnL", title="PnL neto por trade (MXN)")
            _fig_sc.update_traces(texttemplate="$%{text:+,.0f}", textposition="outside")
            _fig_sc.update_layout(height=240, coloraxis_showscale=False, showlegend=False,
                                  plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(_fig_sc, use_container_width=True)




# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA 5 — GBM BROKER
# ══════════════════════════════════════════════════════════════════════════════

elif page.startswith("🏦"):
    st.title("GBM+ Broker")

    # ── Aviso legal ───────────────────────────────────────────────────────────
    with st.expander("⚠️ Aviso importante — leer antes de usar", expanded=False):
        st.warning("""
**Esta integración NO es oficial.**
`gbmplus` es una librería de la comunidad construida con ingeniería inversa de la app GBM+.
Los T&C de GBM mencionan restricciones sobre uso de terceros. Úsala bajo tu propio riesgo.

**Modo DRY-RUN** (default): las órdenes se *simulan* pero nunca se envían a GBM.
Para habilitar órdenes reales necesitas activar `GBM_LIVE=true` en las variables de entorno.

Nunca pongas tus credenciales directamente en el código.
""")

    # ── Configuración de credenciales ─────────────────────────────────────────
    import os as _os
    gbm_email     = _os.environ.get("GBM_EMAIL", "")
    gbm_client_id = _os.environ.get("GBM_CLIENT_ID", "")
    gbm_live      = _os.environ.get("GBM_LIVE", "false").lower() == "true"

    c1, c2, c3 = st.columns(3)
    c1.metric("Email configurado", "✅" if gbm_email else "❌ Falta GBM_EMAIL")
    c2.metric("Client ID",         "✅" if gbm_client_id else "❌ Falta GBM_CLIENT_ID")
    c3.metric("Modo", "🔴 LIVE" if gbm_live else "🟡 DRY-RUN (seguro)")

    if not gbm_email or not gbm_client_id:
        st.info("""
**Cómo configurar las credenciales:**

```bash
# Agrega estas líneas a tu ~/.zshrc (o ~/.bashrc)
export GBM_EMAIL="tucorreo@gmail.com"
export GBM_PASSWORD="tu_contraseña"
export GBM_CLIENT_ID="xxxxxxxxxxxx"

# Para habilitar órdenes reales (⚠️ hacer solo cuando estés seguro):
# export GBM_LIVE="true"
```

El `CLIENT_ID` lo encuentras en el dashboard de GBM+ al iniciar sesión
(visible en la URL o en las herramientas de desarrollador del navegador).
""")

    st.divider()
    tab_portfolio, tab_orders, tab_execute, tab_session = st.tabs([
        "📊 Portafolio", "📋 Órdenes abiertas", "🚀 Ejecutar señales", "🔑 Sesión"
    ])

    # ── Tab Portafolio ────────────────────────────────────────────────────────
    with tab_portfolio:
        if not gbm_email:
            st.warning("Configura las variables de entorno GBM_EMAIL / GBM_PASSWORD / GBM_CLIENT_ID primero.")
        else:
            if st.button("🔄 Obtener portafolio de GBM+", type="primary"):
                try:
                    from src.broker.gbm_client import GBMClient
                    client    = GBMClient()
                    portfolio = client.get_portfolio()
                    st.session_state["gbm_portfolio"] = portfolio
                except Exception as e:
                    st.error(f"Error: {e}")

            portfolio = st.session_state.get("gbm_portfolio")
            if portfolio:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Efectivo disponible", f"${portfolio.cash_mxn:,.0f}")
                c2.metric("Buying power",        f"${portfolio.buying_power:,.0f}")
                c3.metric("Valor en acciones",   f"${portfolio.market_value:,.0f}")
                c4.metric("Total portafolio",     f"${portfolio.total_value:,.0f}")

                if portfolio.positions:
                    st.subheader("Posiciones actuales")
                    rows = [{
                        "Ticker":    p.ticker,
                        "Acciones":  p.shares,
                        "Costo prom": f"${p.avg_cost:.2f}",
                        "Precio":    f"${p.current_price:.2f}",
                        "Valor MXN": f"${p.market_value:,.0f}",
                        "PnL MXN":   p.unrealized_pnl,
                        "PnL %":     f"{p.unrealized_pnl_pct:+.2f}%",
                    } for p in portfolio.positions]
                    df_pos = pd.DataFrame(rows)
                    st.dataframe(df_pos, use_container_width=True, hide_index=True)

                    fig = px.pie(
                        values=[p.market_value for p in portfolio.positions] + [portfolio.cash_mxn],
                        names=[p.ticker for p in portfolio.positions] + ["Efectivo"],
                        title="Distribución del portafolio",
                    )
                    fig.update_layout(height=360)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No hay posiciones abiertas en acciones.")

    # ── Tab Órdenes abiertas ──────────────────────────────────────────────────
    with tab_orders:
        if not gbm_email:
            st.warning("Configura las variables de entorno primero.")
        else:
            if st.button("🔄 Ver órdenes pendientes"):
                try:
                    from src.broker.gbm_client import GBMClient
                    client = GBMClient()
                    orders = client.get_open_orders()
                    st.session_state["gbm_orders"] = orders
                except Exception as e:
                    st.error(f"Error: {e}")

            orders = st.session_state.get("gbm_orders", [])
            if orders:
                st.dataframe(pd.DataFrame(orders), use_container_width=True, hide_index=True)
            else:
                st.info("Sin órdenes pendientes (o haz clic en 'Ver órdenes pendientes').")

        # Log de órdenes enviadas por este sistema
        orders_log = DATA / "orders_log.json"
        if orders_log.exists() and orders_log.stat().st_size > 2:
            st.subheader("Historial de órdenes enviadas por el sistema")
            df_log = pd.DataFrame(json.loads(orders_log.read_text()))
            if not df_log.empty:
                df_log["dry_run"] = df_log["dry_run"].map({True: "Simulada", False: "Real"})
                df_log["success"] = df_log["success"].map({True: "✅", False: "❌"})
                st.dataframe(
                    df_log[["timestamp","ticker","side","shares","limit_price",
                             "stop","target_1","p_up","capital_mxn","dry_run","success","message"]],
                    use_container_width=True, hide_index=True,
                )

    # ── Tab Ejecutar señales ──────────────────────────────────────────────────
    with tab_execute:
        signals_data = load_json("signals_today.json")
        signals      = signals_data.get("signals", [])
        meta_s       = signals_data.get("meta", {})

        if not signals:
            st.warning("No hay señales activas. Ve a 'Señales de hoy' y genéralas primero.")
        else:
            st.subheader(f"{len(signals)} señales listas para ejecutar")
            rows = [{
                "Ticker":   s["ticker"],
                "P(↑)":     f"{s['p_up']*100:.0f}%",
                "Entry":    f"${s['entry']:.2f}",
                "Stop":     f"${s['stop']:.2f}",
                "T1":       f"${s['target_1']:.2f}",
                "Acciones": s["shares"],
                "Capital":  f"${s['capital_mxn']:,.0f}",
                "Razón":    s.get("reason",""),
            } for s in signals]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            total = sum(s["capital_mxn"] for s in signals)
            st.markdown(f"**Capital total a invertir: ${total:,.0f} MXN**")
            st.divider()

            if gbm_live:
                st.error("🔴 **MODO LIVE ACTIVO** — Las órdenes se enviarán a tu cuenta real GBM+")
                confirm_text = st.text_input(
                    "Escribe 'CONFIRMO' para ejecutar órdenes REALES:",
                    placeholder="CONFIRMO"
                )
                execute_btn = st.button(
                    "🚀 Enviar órdenes a GBM+ (REAL)",
                    type="primary",
                    disabled=(confirm_text != "CONFIRMO"),
                )
            else:
                st.success("🟡 Modo DRY-RUN — Las órdenes se simularán sin afectar tu cuenta")
                execute_btn = st.button("▶ Simular ejecución de órdenes", type="primary")

            if execute_btn:
                mode_flag = "--live" if gbm_live else "--dry-run"
                with st.spinner(f"Ejecutando en modo {'LIVE' if gbm_live else 'dry-run'}..."):
                    rc, out = run_script(["scripts/execute_orders.py", mode_flag])
                st.code(out)
                st.cache_data.clear()
                st.rerun()

    # ── Tab Sesión ────────────────────────────────────────────────────────────
    with tab_session:
        st.subheader("Estado de la sesión GBM+")

        from src.broker.gbm_client import _token_is_expired, _token_minutes_left
        from dotenv import dotenv_values as _dv

        _env    = _dv(ROOT / ".env")
        _access = _env.get("GBM_ACCESS_TOKEN", "")

        if not _access:
            token_status = "Sin tokens"
            token_color  = "🔴"
            mins_left    = 0
        elif _token_is_expired(_access):
            token_status = "Expirados"
            token_color  = "🔴"
            mins_left    = 0
        else:
            mins_left    = _token_minutes_left(_access)
            token_color  = "🟢" if mins_left > 15 else "🟡"
            token_status = f"Válidos — {mins_left:.0f} min restantes"

        # Estado del daemon
        pid_file = Path("/tmp/gbm_token_daemon.pid")
        daemon_running = pid_file.exists()
        if daemon_running:
            try:
                pid = int(pid_file.read_text())
                import subprocess as _sp
                _sp.run(["kill", "-0", str(pid)], check=True, capture_output=True)
            except Exception:
                daemon_running = False

        col1, col2 = st.columns(2)
        col1.metric("Token de sesión", f"{token_color} {token_status}")
        col2.metric("Daemon auto-refresh", "🟢 Corriendo" if daemon_running else "🔴 Detenido")

        st.divider()

        st.subheader("Cómo funciona el auto-refresh")
        st.markdown("""
**Primera vez (una sola vez):**

```bash
python scripts/gbm_auth_setup.py
```
Abre un navegador visible donde inicias sesión en GBM+ normalmente.
GBM puede pedir verificación de nuevo dispositivo (email/SMS) — complétala.
El perfil del navegador queda guardado en `~/.gbm-playwright-profile/`.

---

**Renovar tokens manualmente:**
```bash
python scripts/refresh_gbm_session.py
```

---

**Activar daemon en background (mantiene tokens frescos):**
```bash
# Opción 1: Solo esta sesión de terminal
nohup python scripts/gbm_token_daemon.py > /tmp/gbm_token_daemon.log 2>&1 &

# Opción 2: Servicio macOS (arranca automáticamente al encender la Mac)
bash scripts/install_token_daemon.sh
```

---

**Ver log del daemon:**
```bash
tail -f /tmp/gbm_token_daemon.log
```
""")

        if mins_left < 10:
            st.warning("Los tokens están a punto de expirar o ya expiraron.")

        col_a, col_b, col_c = st.columns(3)

        with col_a:
            if st.button("🔑 Setup inicial (navegador visible)", use_container_width=True):
                with st.spinner("Abriendo navegador... (completa el login y vuelve aquí)"):
                    rc, out = run_script(["scripts/gbm_auth_setup.py"])
                st.code(out)
                st.cache_data.clear()
                st.rerun()

        with col_b:
            if st.button("🔄 Refrescar tokens ahora (headless)", use_container_width=True,
                          type="primary", disabled=not Path.home().joinpath(".gbm-playwright-profile").exists()):
                with st.spinner("Abriendo GBM+ en headless..."):
                    rc, out = run_script(["scripts/refresh_gbm_session.py"])
                st.code(out)
                st.cache_data.clear()
                st.rerun()

        with col_c:
            if not daemon_running:
                if st.button("▶ Iniciar daemon", use_container_width=True):
                    import subprocess as _sp2
                    venv_python = str(ROOT / "venv" / "bin" / "python")
                    _sp2.Popen(
                        [venv_python, "scripts/gbm_token_daemon.py"],
                        cwd=str(ROOT), stdout=open("/tmp/gbm_token_daemon.log","a"),
                        stderr=_sp2.STDOUT,
                    )
                    st.success("Daemon iniciado en background")
                    st.rerun()
            else:
                if st.button("⏹ Detener daemon", use_container_width=True):
                    try:
                        pid = int(pid_file.read_text())
                        import subprocess as _sp3
                        _sp3.run(["kill", str(pid)])
                        st.success("Daemon detenido")
                    except Exception as e:
                        st.error(f"Error: {e}")
                    st.rerun()

        # Log en vivo (últimas 20 líneas)
        log_path = Path("/tmp/gbm_token_daemon.log")
        if log_path.exists() and log_path.stat().st_size > 0:
            st.divider()
            st.subheader("Log del daemon (últimas 20 líneas)")
            lines = log_path.read_text().splitlines()
            st.code("\n".join(lines[-20:]), language="bash")


# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA 5 — MODELO
# ══════════════════════════════════════════════════════════════════════════════

elif page.startswith("🧠"):
    st.title("Modelo — EnsembleModel v1")
    st.caption("WoE + Logistic Regression + LightGBM · El modelo de producción para señales y simulaciones")

    tab_ensemble, tab_meta, tab_valid, tab_holdout, tab_wf = st.tabs([
        "🏆 Ensemble v1 (producción)",
        "🧬 Meta-Labeling",
        "🔬 Validación general",
        "🎯 Hold-Out 20%",
        "🔄 Walk-Forward",
    ])

    # ── TAB ENSEMBLE (PRINCIPAL) ──────────────────────────────────────────────
    with tab_ensemble:
        st.caption("""
**Ensemble v1** combina WoE+LR y LightGBM con pesos proporcionales a su edge individual (AUC − 0.5).
Es el modelo usado en _Señales de hoy_ y el _Simulador_.
        """)

        ens_data = load_json("ensemble_results.json")
        if not ens_data:
            st.warning("No hay resultados del ensemble. Corre `run_ensemble.py` para evaluarlo.")
        else:
            e_strat  = ens_data.get("strategy_ensemble", {})
            e_models = ens_data.get("individual_auc", {})
            e_meta   = ens_data.get("meta", {})

            # Banner principal
            st.success(f"**Ensemble v1 — AUC {e_meta.get('auc_ensemble', ens_data.get('auc_ensemble', 0)):.4f}  ·  "
                       f"Win rate {e_strat.get('win_rate',0)*100:.1f}%  ·  "
                       f"Sharpe {e_strat.get('sharpe',0):.2f}  ·  "
                       f"Profit Factor {e_strat.get('profit_factor',0):.2f}**")

            st.divider()

            # Métricas del ensemble
            st.subheader("Métricas de estrategia — Hold-Out 20%")
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("AUC Ensemble",    f"{e_meta.get('auc_ensemble', ens_data.get('auc_ensemble', 0)):.4f}")
            c2.metric("Win rate",        f"{e_strat.get('win_rate',0)*100:.1f}%")
            c3.metric("Sharpe",          f"{e_strat.get('sharpe',0):.2f}")
            c4.metric("Profit Factor",   f"{e_strat.get('profit_factor',0):.2f}")
            c5.metric("Señales",         str(e_strat.get("n_signals", 0)))

            st.divider()

            # AUC por componente
            st.subheader("AUC por componente del ensemble")
            _auc_lr   = e_models.get("auc_lr",   ens_data.get("auc_lr",   0))
            _auc_lgbm = e_models.get("auc_lgbm", ens_data.get("auc_lgbm", 0))
            _auc_ens  = e_meta.get("auc_ensemble", ens_data.get("auc_ensemble", 0))

            _fig_auc = go.Figure(go.Bar(
                x=["WoE + LR", "LightGBM", "Ensemble"],
                y=[_auc_lr, _auc_lgbm, _auc_ens],
                marker_color=["#60a5fa","#f59e0b","#22c55e"],
                text=[f"{v:.4f}" for v in [_auc_lr, _auc_lgbm, _auc_ens]],
                textposition="outside",
            ))
            _fig_auc.add_hline(y=0.5, line_dash="dash", line_color="gray",
                               annotation_text="Azar 0.50")
            _fig_auc.update_layout(
                height=280, yaxis_range=[0.47, max(0.58, _auc_ens + 0.02)],
                yaxis_title="AUC", showlegend=False,
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(_fig_auc, use_container_width=True)

            # Calibración
            _cal = ens_data.get("calibration_ensemble", ens_data.get("calibration", []))
            if _cal:
                st.subheader("Calibración — P predicha vs tasa real de éxito")
                _df_cal = pd.DataFrame(_cal)
                _fig_cal = go.Figure()
                _fig_cal.add_trace(go.Bar(
                    x=_df_cal["bucket"], y=_df_cal["actual_rate"].mul(100),
                    name="Tasa real", marker_color="#22c55e",
                ))
                _fig_cal.add_trace(go.Scatter(
                    x=_df_cal["bucket"], y=_df_cal["mean_pred"].mul(100),
                    name="P predicha", mode="lines+markers",
                    line=dict(color="#f59e0b", dash="dot"),
                ))
                _fig_cal.update_layout(
                    height=280, yaxis_title="% éxito",
                    xaxis_title="Rango de probabilidad predicha",
                    legend=dict(orientation="h"),
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(_fig_cal, use_container_width=True)

        st.divider()
        if st.button("🔄 Re-evaluar Ensemble v1 en holdout 20% (~2 min)", type="primary"):
            with st.spinner("Entrenando ensemble (WoE+LR+LightGBM con Optuna)..."):
                rc, out = run_script(["scripts/run_ensemble.py"])
            st.code(out[-4000:])
            st.cache_data.clear()
            st.rerun()

    # ── TAB META-LABELING ─────────────────────────────────────────────────────
    with tab_meta:
        st.caption("""
**Meta-labeling (López de Prado)**: un segundo modelo decide *si tomar* la señal del Ensemble.
Entrenado sobre **triple-barrier labels** (¿el trade tocó target o stop?). Filtra falsos positivos.
        """)

        meta_data = load_json("meta_results.json")
        if not meta_data:
            st.warning("No hay resultados de meta-labeling todavía.")
            if st.button("▶ Correr Meta-Labeling (~2 min)", type="primary"):
                with st.spinner("Entrenando primario + meta sobre triple-barrier labels..."):
                    rc, out = run_script(["scripts/run_meta.py"])
                st.code(out[-3500:])
                st.cache_data.clear()
                st.rerun()
        else:
            m_base = meta_data.get("strategy_base", {})
            m_meta = meta_data.get("strategy_meta", {})
            m_imp  = meta_data.get("improvement", {})
            m_meta_meta = meta_data.get("meta", {})
            bstats = meta_data.get("barrier_stats", {})

            # Banner
            auc_p = meta_data.get("auc_primary", 0)
            auc_m = meta_data.get("auc_meta", 0)
            if auc_m > auc_p:
                st.success(f"**Meta AUC {auc_m:.4f} > Primario {auc_p:.4f}** — el meta-modelo añade poder predictivo sobre la dirección sola")
            else:
                st.info(f"Meta AUC {auc_m:.4f}  ·  Primario {auc_p:.4f}")

            st.divider()

            # Métricas del meta-modelo
            st.subheader("Modelo meta — calidad de filtrado")
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("AUC meta",      f"{auc_m:.4f}")
            mc2.metric("Precisión",     f"{meta_data.get('meta_precision',0)*100:.1f}%",
                       help="De los trades que el meta aprueba, % que realmente ganan")
            mc3.metric("Recall",        f"{meta_data.get('meta_recall',0)*100:.1f}%",
                       help="% de ganadores que el meta logra capturar")
            mc4.metric("Umbral meta",   f"{meta_data.get('meta_cut',0):.3f}")

            # Distribución de barreras
            if bstats:
                st.caption(
                    f"Triple-barrier sobre {bstats.get('n',0):,} obs  ·  "
                    f"🎯 target {bstats.get('pct_target',0)*100:.0f}%  ·  "
                    f"🛑 stop {bstats.get('pct_stop',0)*100:.0f}%  ·  "
                    f"⏱️ tiempo {bstats.get('pct_time',0)*100:.0f}%"
                )

            st.divider()

            # Comparación base vs meta
            st.subheader("Ensemble base vs Ensemble + Meta (hold-out 20%)")
            comp = pd.DataFrame([
                {"Estrategia": "Ensemble base",   "Trades": m_base.get("n",0),
                 "Win rate": f"{m_base.get('win_rate',0)*100:.1f}%",
                 "Sharpe": m_base.get("sharpe",0), "Profit Factor": m_base.get("profit_factor",0),
                 "Retorno total": f"{m_base.get('total_ret',0):+.1f}%"},
                {"Estrategia": "Ensemble + Meta",  "Trades": m_meta.get("n",0),
                 "Win rate": f"{m_meta.get('win_rate',0)*100:.1f}%",
                 "Sharpe": m_meta.get("sharpe",0), "Profit Factor": m_meta.get("profit_factor",0),
                 "Retorno total": f"{m_meta.get('total_ret',0):+.1f}%"},
            ])
            st.dataframe(comp, use_container_width=True, hide_index=True)

            ic1, ic2, ic3 = st.columns(3)
            ic1.metric("Δ Profit Factor", f"{m_imp.get('profit_factor_delta',0):+.3f}")
            ic2.metric("Δ Win rate",      f"{m_imp.get('win_rate_delta',0):+.1f} pts")
            ic3.metric("Trades filtrados", str(m_imp.get('trades_filtered',0)),
                       help="Señales descartadas por el meta-modelo (falsos positivos evitados)")

            st.divider()

            # Barrido de selectividad
            sweep = meta_data.get("selectivity_sweep", [])
            if sweep:
                st.subheader("Barrido de selectividad — la clave del meta-labeling")
                st.caption("A mayor selectividad (solo los trades de más confianza), mejor calidad. El punto óptimo suele estar arriba del 90%.")
                df_sw = pd.DataFrame(sweep)
                df_sw["percentil"] = (df_sw["quantile"] * 100).astype(int).astype(str) + "%"

                fig_sw = go.Figure()
                fig_sw.add_trace(go.Bar(
                    x=df_sw["percentil"], y=df_sw["total_ret"],
                    name="Retorno total %",
                    marker_color=["#22c55e" if v > 0 else "#ef4444" for v in df_sw["total_ret"]],
                    text=df_sw["total_ret"].round(1), textposition="outside",
                    texttemplate="%{text:+.0f}%", yaxis="y",
                ))
                fig_sw.add_trace(go.Scatter(
                    x=df_sw["percentil"], y=df_sw["profit_factor"],
                    name="Profit Factor", mode="lines+markers",
                    line=dict(color="#f59e0b", width=2), yaxis="y2",
                ))
                fig_sw.add_hline(y=0, line_dash="dash", line_color="gray", yref="y")
                fig_sw.update_layout(
                    height=340,
                    yaxis=dict(title="Retorno total %"),
                    yaxis2=dict(title="Profit Factor", overlaying="y", side="right"),
                    xaxis_title="Selectividad del meta (percentil de confianza)",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig_sw, use_container_width=True)

                with st.expander("Ver tabla del barrido"):
                    df_show = df_sw[["percentil","n","win_rate","sharpe","profit_factor","total_ret"]].copy()
                    df_show.columns = ["Selectividad","Trades","Win rate","Sharpe","PF","Retorno %"]
                    df_show["Win rate"] = (df_show["Win rate"]*100).round(1).astype(str) + "%"
                    st.dataframe(df_show, use_container_width=True, hide_index=True)

            # Importancia de features del meta
            feat_imp = meta_data.get("meta_feat_importance", [])
            if feat_imp:
                st.subheader("¿Qué features usa el meta para decidir?")
                df_fi = pd.DataFrame(feat_imp).head(10).sort_values("importance")
                fig_fi = go.Figure(go.Bar(
                    x=df_fi["importance"], y=df_fi["feature"],
                    orientation="h", marker_color="#8b5cf6",
                ))
                fig_fi.update_layout(height=300, xaxis_title="Importancia (LightGBM)",
                                     plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_fi, use_container_width=True)

            with st.expander("¿Cómo funciona el meta-labeling?"):
                st.markdown("""
**Dos niveles de decisión** (López de Prado, AFML Cap. 3):

1. **Modelo primario (Ensemble)** decide la *dirección*: "creo que esto sube".
   Tiene edge pequeño pero muchos falsos positivos.

2. **Triple-barrier labeling** etiqueta como realmente operamos: desde la entrada,
   ¿el precio toca primero el **target** (gana), el **stop** (pierde), o expira el tiempo?

3. **Meta-modelo** aprende a predecir: "dado que el primario dice comprar,
   ¿realmente va a funcionar?". Filtra los trades de baja calidad.

**Resultado**: mejora la *precisión* (menos trades perdedores) sacrificando *recall*
(menos trades totales). Ideal cuando el costo de un trade malo es alto.

El sistema de producción usa el meta-modelo para **rankear** los candidatos:
los trades que el meta considera de mayor calidad se priorizan en el portafolio.
                """)

        # ── Backtest completo: stack de mejoras ────────────────────────────────
        st.divider()
        st.subheader("📈 Backtest completo — stack de mejoras (todas las semanas de validación)")

        bt = load_json("backtest_meta.json")
        if not bt:
            st.info("Corre el backtest semanal completo para ver el efecto acumulado de cada técnica.")
            if st.button("▶ Correr backtest completo (~2 min)", type="primary"):
                with st.spinner("Simulando 172 semanas con cada técnica..."):
                    rc, out = run_script(["scripts/backtest_meta.py"])
                st.code(out[-3500:])
                st.cache_data.clear()
                st.rerun()
        else:
            base_m = bt.get("base", {})
            meta_m = bt.get("best_meta", {})
            reg_m  = bt.get("best_regime", {})

            st.caption(
                f"Portafolio top-5 semanal, comisión 0.25% ida/vuelta  ·  "
                f"{bt.get('meta',{}).get('test_start','?')} → {bt.get('meta',{}).get('test_end','?')}"
            )

            # Tabla del stack
            stack = pd.DataFrame([
                {"Técnica": "1. Ensemble base",            "Retorno total": base_m.get("total_ret",0),
                 "Sharpe": base_m.get("sharpe",0), "Max DD": base_m.get("max_dd",0),
                 "Trades": base_m.get("n_trades",0)},
                {"Técnica": "2. + Meta-labeling",          "Retorno total": meta_m.get("total_ret",0),
                 "Sharpe": meta_m.get("sharpe",0), "Max DD": meta_m.get("max_dd",0),
                 "Trades": meta_m.get("n_trades",0)},
                {"Técnica": "3. + Filtro de régimen",      "Retorno total": reg_m.get("total_ret",0),
                 "Sharpe": reg_m.get("sharpe",0), "Max DD": reg_m.get("max_dd",0),
                 "Trades": reg_m.get("n_trades",0)},
            ])
            stack_disp = stack.copy()
            stack_disp["Retorno total"] = stack_disp["Retorno total"].map(lambda v: f"{v:+.1f}%")
            stack_disp["Max DD"]        = stack_disp["Max DD"].map(lambda v: f"{v:.1f}%")
            st.dataframe(stack_disp, use_container_width=True, hide_index=True)

            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("Retorno base",        f"{base_m.get('total_ret',0):+.1f}%")
            sc2.metric("Retorno final (stack)", f"{reg_m.get('total_ret',0):+.1f}%",
                       delta=f"{reg_m.get('total_ret',0) - base_m.get('total_ret',0):+.1f} pts")
            sc3.metric("Max Drawdown",         f"{reg_m.get('max_dd',0):.1f}%",
                       delta=f"{base_m.get('max_dd',0) - reg_m.get('max_dd',0):+.1f} pts mejor",
                       delta_color="normal")

            # Curvas de equity
            def _curve_df(curve, label):
                if not curve:
                    return pd.DataFrame()
                d = pd.DataFrame(curve)
                d["estrategia"] = label
                return d

            curves = pd.concat([
                _curve_df(bt.get("base_curve"),        "1. Base"),
                _curve_df(bt.get("best_curve"),        "2. + Meta"),
                _curve_df(bt.get("best_regime_curve"), "3. + Régimen"),
            ], ignore_index=True)

            if not curves.empty:
                fig_eq = px.line(
                    curves, x="week", y="equity", color="estrategia",
                    title="Curva de equity por estrategia (capital inicial $100k)",
                    color_discrete_map={"1. Base": "#ef4444", "2. + Meta": "#f59e0b",
                                        "3. + Régimen": "#22c55e"},
                )
                fig_eq.add_hline(y=bt.get("meta",{}).get("capital",100000),
                                 line_dash="dash", line_color="gray")
                fig_eq.update_layout(height=380, xaxis_title="Semana",
                                     yaxis_title="Equity (MXN)",
                                     plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                                     legend=dict(orientation="h", yanchor="bottom", y=1.02))
                fig_eq.update_xaxes(showticklabels=False)
                st.plotly_chart(fig_eq, use_container_width=True)

            st.info(
                "**Lectura honesta**: las tres técnicas combinadas llevan la estrategia de "
                f"**{base_m.get('total_ret',0):+.0f}%** a **{reg_m.get('total_ret',0):+.0f}%** y cortan el "
                f"drawdown de {base_m.get('max_dd',0):.0f}% a {reg_m.get('max_dd',0):.0f}%. "
                "El edge direccional crudo en este universo/período es delgado; la mejora vino "
                "sobre todo de **dejar de perder** (mejor gestión de riesgo), no de acertar mucho más."
            )

        st.divider()
        bc1, bc2 = st.columns(2)
        with bc1:
            if st.button("🔄 Re-correr Meta-Labeling (~2 min)"):
                with st.spinner("Entrenando primario + meta sobre triple-barrier..."):
                    rc, out = run_script(["scripts/run_meta.py"])
                st.code(out[-3500:])
                st.cache_data.clear()
                st.rerun()
        with bc2:
            if st.button("🔄 Re-correr backtest completo (~2 min)"):
                with st.spinner("Simulando todas las semanas..."):
                    rc, out = run_script(["scripts/backtest_meta.py"])
                st.code(out[-3500:])
                st.cache_data.clear()
                st.rerun()

    # ── TAB VALIDACIÓN GENERAL ────────────────────────────────────────────────
    with tab_valid:
        st.caption("""
**Validación anti-trampa** siguiendo a López de Prado:
purged walk-forward CV con embargo, Deflated Sharpe Ratio y AUC por fold.
        """)

        cv_data = load_json("purged_cv_results.json")
        if not cv_data:
            st.warning("No hay resultados de validación todavía.")
            if st.button("▶ Correr Purged CV (~2 min)", type="primary"):
                with st.spinner("Corriendo Purged CV con embargo (6 folds)..."):
                    rc, out = run_script(["scripts/run_purged_cv.py"])
                st.code(out[-3000:])
                st.cache_data.clear()
                st.rerun()
        else:
            cv_agg   = cv_data.get("aggregate", {})
            cv_folds = cv_data.get("folds", [])
            cv_meta  = cv_data.get("meta", {})

            # ── Banner DSR ─────────────────────────────────────────────────────
            dsr   = cv_agg.get("deflated_sharpe_ratio", 0)
            dsr_i = cv_agg.get("dsr_interpretation", "—")
            if dsr > 0.95:
                st.success(f"**DSR = {dsr:.4f}** — {dsr_i}")
            elif dsr > 0.75:
                st.warning(f"**DSR = {dsr:.4f}** — {dsr_i}")
            else:
                st.error(f"**DSR = {dsr:.4f}** — {dsr_i}")

            st.divider()

            # ── Métricas agregadas ─────────────────────────────────────────────
            st.subheader("Métricas agregadas — Purged CV")
            vc1, vc2, vc3, vc4, vc5 = st.columns(5)
            vc1.metric("AUC promedio",
                       f"{cv_agg.get('mean_auc', 0):.4f}",
                       delta=f"± {cv_agg.get('std_auc', 0):.4f}")
            vc2.metric("Sharpe promedio",  f"{cv_agg.get('mean_sharpe', 0):.2f}")
            vc3.metric("Win rate",         f"{cv_agg.get('mean_win_rate', 0)*100:.1f}%")
            vc4.metric("DSR",              f"{dsr:.4f}")
            vc5.metric("Total señales",    str(cv_agg.get("total_signals", 0)))

            st.caption(
                f"Metodología: {cv_meta.get('n_splits',6)} folds  ·  "
                f"embargo={cv_meta.get('embargo',10)}d  ·  "
                f"horizonte={cv_meta.get('horizon',5)}d  ·  "
                f"{cv_meta.get('n_features',38)} features  ·  31 tickers"
            )
            st.divider()

            # ── AUC + Sharpe por fold ──────────────────────────────────────────
            if cv_folds:
                st.subheader("AUC y Sharpe por fold — purged walk-forward")
                df_cv = pd.DataFrame(cv_folds).sort_values("fold")

                fig_cv = go.Figure()
                fig_cv.add_trace(go.Bar(
                    x=df_cv["test_start"],
                    y=df_cv["auc"],
                    name="AUC",
                    marker_color=["#22c55e" if v > 0.5 else "#ef4444" for v in df_cv["auc"]],
                    text=df_cv["auc"].round(4),
                    textposition="outside",
                    texttemplate="%{text}",
                    yaxis="y",
                ))
                fig_cv.add_trace(go.Scatter(
                    x=df_cv["test_start"],
                    y=df_cv["sharpe"],
                    name="Sharpe",
                    mode="lines+markers",
                    line=dict(color="#f59e0b", width=2),
                    marker=dict(size=8),
                    yaxis="y2",
                ))
                fig_cv.add_hline(y=0.5, line_dash="dash", line_color="gray",
                                 annotation_text="AUC azar = 0.50", yref="y")
                fig_cv.update_layout(
                    height=320,
                    yaxis=dict(title="AUC", range=[0.47, 0.60],
                               showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
                    yaxis2=dict(title="Sharpe", overlaying="y", side="right",
                                showgrid=False),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    xaxis_title="Inicio período test",
                )
                st.plotly_chart(fig_cv, use_container_width=True)

                # Tabla de folds
                with st.expander("Detalle por fold"):
                    df_show = df_cv[["fold","test_start","test_end","n_train",
                                     "n_test","auc","sharpe","win_rate","n_signals"]].copy()
                    df_show["win_rate"] = (df_show["win_rate"]*100).round(1).astype(str) + "%"
                    df_show["auc"]      = df_show["auc"].round(4)
                    df_show["sharpe"]   = df_show["sharpe"].round(2)
                    st.dataframe(df_show, use_container_width=True, hide_index=True)

                # Estabilidad
                aucs = [f["auc"] for f in cv_folds]
                delta_auc = max(aucs) - min(aucs)
                if delta_auc < 0.025:
                    st.success(f"✅ AUC estable ({min(aucs):.4f}–{max(aucs):.4f}, delta={delta_auc:.4f}) — el edge no es ruido de un período")
                else:
                    st.warning(f"⚡ AUC variable ({min(aucs):.4f}–{max(aucs):.4f}, delta={delta_auc:.4f}) — el modelo es más sensible a la época")

            st.divider()

            # ── Explicación de metodología ─────────────────────────────────────
            with st.expander("¿Qué es el Deflated Sharpe Ratio? (López de Prado)"):
                st.markdown("""
**El problema del backtest clásico**: si pruebas muchas estrategias y te quedas con
la mejor, probablemente sea buena *por suerte*, no por edge real.

**El DSR corrige esto** penalizando el Sharpe por el número de configuraciones probadas:

| DSR | Interpretación |
|---|---|
| > 0.95 | ✅ Edge estadísticamente significativo |
| 0.75 – 0.95 | ⚡ Edge moderado — monitorear con más datos |
| < 0.75 | ⚠️ Posible sobreajuste — Sharpe inflado por selección |

**Purging**: elimina las últimas N filas del train cuyo label se solapa con el test (evita contaminación directa).

**Embargo**: buffer de 10 días hábiles entre train y test (evita autocorrelación residual).

**Fuente**: Bailey & López de Prado (2014) — *The Deflated Sharpe Ratio*.
                """)

        st.divider()
        if st.button("🔄 Re-correr Purged CV (~2 min)"):
            with st.spinner("Corriendo Purged CV con embargo (6 folds, 31 tickers)..."):
                rc, out = run_script(["scripts/run_purged_cv.py"])
            st.code(out[-3000:])
            st.cache_data.clear()
            st.rerun()

    # ── TAB WALK-FORWARD ──────────────────────────────────────────────────────
    with tab_wf:
        st.caption("Entrenamiento en ventanas crecientes. Mide estabilidad del edge en el tiempo.")

    model_data = load_json("model_results.json")
    if not model_data:
        st.info("No hay resultados walk-forward. Corre run_model.py para generarlos.")

    with tab_wf:
        if model_data:
            agg    = model_data.get("aggregate", {})
            folds  = model_data.get("folds", [])
            strat  = model_data.get("strategy", {})

            c1,c2,c3,c4 = st.columns(4)
            c1.metric("AUC LR (promedio)", f"{agg.get('mean_auc_lr',0):.4f}",
                      delta=f"±{agg.get('std_auc_lr',0):.4f}")
            c2.metric("AUC LightGBM", f"{agg.get('mean_auc_lgbm',0):.4f}")
            c3.metric("Win rate (P>0.55)", f"{strat.get('logistic',{}).get('win_rate',0)*100:.1f}%")
            c4.metric("Sharpe", f"{strat.get('logistic',{}).get('sharpe',0):.2f}")

            st.divider()

            df_folds = pd.DataFrame(folds)
            if not df_folds.empty:
                st.subheader("AUC walk-forward por fold")
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=df_folds["test_start"], y=df_folds["auc_lr"],
                                         name="LR + WoE", mode="lines+markers",
                                         line=dict(color="#22c55e", width=2)))
                fig.add_trace(go.Scatter(x=df_folds["test_start"], y=df_folds["auc_lgbm"],
                                         name="LightGBM", mode="lines+markers",
                                         line=dict(color="#f59e0b", width=2)))
                fig.add_hline(y=0.5, line_dash="dash", line_color="gray",
                              annotation_text="Azar 0.50")
                fig.update_layout(height=350, yaxis_range=[0.46, 0.60],
                                  xaxis_title="Inicio período test",
                                  yaxis_title="AUC",
                                  legend=dict(orientation="h", yanchor="bottom", y=1.02),
                                  plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig, use_container_width=True)

            cal = strat.get("logistic", {}).get("calibration", [])
            if cal:
                st.subheader("Calibración")
                df_cal = pd.DataFrame(cal)
                fig = go.Figure()
                fig.add_trace(go.Bar(x=df_cal["bucket"], y=df_cal["actual_rate"].mul(100),
                                     name="Tasa real %", marker_color="#22c55e"))
                fig.add_trace(go.Scatter(x=df_cal["bucket"], y=df_cal["mean_pred"].mul(100),
                                         name="P predicha %", mode="lines+markers",
                                         line=dict(color="#f59e0b", dash="dot")))
                fig.update_layout(height=300, yaxis_title="% éxito",
                                  legend=dict(orientation="h"),
                                  plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig, use_container_width=True)

        if st.button("🔄 Re-entrenar walk-forward completo (~30 seg)"):
            with st.spinner("Corriendo walk-forward..."):
                rc, out = run_script(["scripts/run_model.py"])
            st.code(out[-3000:]); st.cache_data.clear(); st.rerun()

    # ── TAB HOLD-OUT 20% ──────────────────────────────────────────────────────
    with tab_holdout:
        st.caption("WoE + LR entrenado en el 80% inicial, evaluado en el 20% más reciente.")

        h_data = load_json("holdout_results.json")
        if not h_data:
            st.info("No hay resultados de hold-out todavía.")
            if st.button("🚀 Correr evaluación hold-out 20% (~20 seg)", type="primary"):
                with st.spinner("Entrenando sobre 80% y evaluando en 20% reciente..."):
                    rc, out = run_script(["scripts/run_model_holdout.py"])
                st.code(out[-4000:]); st.cache_data.clear(); st.rerun()
            st.stop()

        h_meta  = h_data.get("meta", {})
        h_perf  = h_data.get("performance", {})
        h_cal   = h_data.get("calibration", [])
        h_ticks = h_data.get("ticker_stats", [])
        h_coefs = h_data.get("coefficients", [])
        h_iv    = h_data.get("iv_summary", [])

        # Comparación walk-forward vs holdout
        wf_auc = (model_data or {}).get("aggregate", {}).get("mean_auc_lr", 0)
        st.subheader("Comparación Walk-Forward vs Hold-Out")
        cc1, cc2, cc3, cc4, cc5 = st.columns(5)
        cc1.metric("AUC Hold-out",     f"{h_perf.get('auc',0):.4f}",
                   delta=f"vs WF {wf_auc:.4f} ({h_perf.get('auc',0)-wf_auc:+.4f})")
        cc2.metric("Win rate",         f"{h_perf.get('win_rate',0)*100:.1f}%")
        cc3.metric("Sharpe anual",     f"{h_perf.get('sharpe',0):.2f}")
        cc4.metric("Profit factor",    f"{h_perf.get('profit_factor',0):.2f}")
        cc5.metric("Señales en test",  f"{h_perf.get('n_signals',0):,}  ({h_perf.get('signal_pct',0):.1f}%)")

        st.caption(
            f"Train: {h_meta.get('train_start','')} → {h_meta.get('train_end','')}  "
            f"({h_meta.get('n_train',0):,} obs)  |  "
            f"Test: {h_meta.get('test_start','')} → {h_meta.get('test_end','')}  "
            f"({h_meta.get('n_test',0):,} obs)"
        )
        st.divider()

        col_a, col_b = st.columns(2)

        # Calibración hold-out
        with col_a:
            st.subheader("Calibración en test set")
            if h_cal:
                df_hcal = pd.DataFrame(h_cal)
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=df_hcal["bucket"], y=(df_hcal["actual_rate"]*100).round(1),
                    name="Tasa real %", marker_color="#22c55e",
                    text=(df_hcal["actual_rate"]*100).round(1),
                    texttemplate="%{text:.0f}%", textposition="outside",
                ))
                fig.add_trace(go.Scatter(
                    x=df_hcal["bucket"], y=(df_hcal["mean_pred"]*100).round(1),
                    name="P predicha %", mode="lines+markers",
                    line=dict(color="#f59e0b", dash="dot", width=2),
                ))
                fig.add_trace(go.Scatter(
                    x=df_hcal["bucket"],
                    y=[h_meta.get("base_rate_test",0.49)*100]*len(df_hcal),
                    name="Base rate", mode="lines",
                    line=dict(color="#6b7280", dash="dash"),
                ))
                n_per_bucket = [str(r["n"]) for r in h_cal]
                for i, (bkt, n) in enumerate(zip(df_hcal["bucket"], n_per_bucket)):
                    fig.add_annotation(x=bkt, y=2, text=f"n={n}",
                                       showarrow=False, font=dict(size=9, color="#9ca3af"))
                fig.update_layout(
                    height=320, yaxis_title="% éxito",
                    xaxis_title="Rango de P predicha",
                    legend=dict(orientation="h"),
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig, use_container_width=True)
                st.caption(
                    "Calibración perfecta = barras verdes = línea naranja. "
                    "Barra > línea base = el modelo agrega valor en ese rango."
                )

        # Coeficientes del modelo
        with col_b:
            st.subheader("Coeficientes — ¿qué mueve la señal?")
            if h_coefs:
                df_coef = pd.DataFrame(h_coefs).sort_values("coef")
                colors  = ["#ef4444" if c < 0 else "#22c55e" for c in df_coef["coef"]]
                fig = go.Figure(go.Bar(
                    x=df_coef["coef"], y=df_coef["feature"],
                    orientation="h", marker_color=colors,
                    text=df_coef["coef"].round(3),
                    texttemplate="%{text:+.3f}", textposition="outside",
                ))
                fig.update_layout(
                    height=320,
                    xaxis_title="Coeficiente LR (+ = favorece subida)",
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    xaxis=dict(zeroline=True, zerolinecolor="#6b7280"),
                )
                st.plotly_chart(fig, use_container_width=True)
                st.caption("Barras verdes = la máquina apuesta a subida cuando este feature es alto.")

        # Rendimiento por ticker en test
        st.subheader("Win rate por ticker en el test set (20% reciente)")
        if h_ticks:
            df_ticks = pd.DataFrame(h_ticks).sort_values("win_rate", ascending=False)
            df_ticks["win_pct"] = (df_ticks["win_rate"] * 100).round(1)
            df_ticks["icon"]    = df_ticks["win_rate"].apply(
                lambda w: "✅" if w > 0.52 else "⚠️" if w > 0.44 else "❌"
            )
            fig = px.bar(
                df_ticks, x="win_pct", y="ticker", orientation="h",
                color="win_pct",
                color_continuous_scale=["#ef4444","#f59e0b","#22c55e"],
                range_color=[35, 70],
                text="win_pct",
                labels={"win_pct": "Win rate %", "ticker": ""},
                title="Win rate por ticker (línea punteada = 50%)"
            )
            fig.add_vline(x=50, line_dash="dash", line_color="#9ca3af")
            fig.update_traces(texttemplate="%{text:.0f}%", textposition="outside")
            fig.update_layout(
                height=420, coloraxis_showscale=False,
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True)

        col_r1, col_r2 = st.columns(2)
        with col_r1:
            if st.button("🔄 Re-correr hold-out 20%", type="primary", use_container_width=True):
                with st.spinner("Entrenando y evaluando (~20 seg)..."):
                    rc, out = run_script(["scripts/run_model_holdout.py"])
                st.code(out[-4000:]); st.cache_data.clear(); st.rerun()
        with col_r2:
            if st.button("📊 Ver predicciones detalladas", use_container_width=True):
                df_hp = load_csv("holdout_predictions.csv")
                if not df_hp.empty:
                    df_hp["señal"] = df_hp["signal"].map({1: "🎯", 0: "—"})
                    df_hp["resultado"] = df_hp["y"].map({1: "✅", 0: "❌"})
                    st.dataframe(df_hp.tail(200), use_container_width=True)

    # ── TAB ENSEMBLE ──────────────────────────────────────────────────────────
    with tab_ensemble:
        st.caption("3 modelos votan: WoE+LR, LightGBM (Optuna) y ROCKET. El peso de cada voto es proporcional a su AUC individual.")

        e_data = load_json("ensemble_results.json")
        if not e_data:
            st.info("Aún no hay resultados del ensemble.")
            if st.button("🚀 Entrenar ensemble (~5 min)", type="primary"):
                with st.spinner("Entrenando 3 modelos y combinando (~5 min — Optuna + ROCKET)..."):
                    rc, out = run_script(["scripts/run_ensemble.py"])
                st.code(out[-5000:]); st.cache_data.clear(); st.rerun()
            st.stop()

        e_meta   = e_data.get("meta", {})
        e_perf   = e_data.get("performance", {})
        e_cal    = e_data.get("calibration", [])
        e_ticks  = e_data.get("ticker_stats", [])
        e_indiv  = e_data.get("individual_auc", {})
        e_models = e_meta.get("models", {})

        # Comparación de AUC individual vs ensemble
        st.subheader("AUC por modelo — ¿gana el ensemble?")

        # Métricas individuales
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("WoE + LR",   f"{e_indiv.get('woe_lr',0):.4f}",
                  f"peso {e_models.get('woe_lr',{}).get('weight',0)*100:.0f}%")
        c2.metric("LightGBM",   f"{e_indiv.get('lightgbm',0):.4f}",
                  f"peso {e_models.get('lightgbm',{}).get('weight',0)*100:.0f}%")
        c3.metric("ROCKET",     f"{e_indiv.get('rocket',0):.4f}",
                  f"peso {e_models.get('rocket',{}).get('weight',0)*100:.0f}%")
        c4.metric("ENSEMBLE",   f"{e_indiv.get('ensemble',0):.4f}",
                  delta="combinado",
                  delta_color="normal")

        st.divider()

        col_e1, col_e2 = st.columns(2)

        with col_e1:
            # Gráfica de barras AUC individual vs ensemble
            st.subheader("Comparación AUC")
            auc_labels = ["WoE+LR", "LightGBM", "ROCKET", "Ensemble"]
            auc_values = [
                e_indiv.get("woe_lr",   0),
                e_indiv.get("lightgbm", 0),
                e_indiv.get("rocket",   0),
                e_indiv.get("ensemble", 0),
            ]
            import plotly.graph_objects as go
            colors = ["#6b7280", "#6b7280", "#6b7280", "#22c55e"]
            fig = go.Figure(go.Bar(
                x=auc_labels, y=auc_values, marker_color=colors,
                text=[f"{v:.4f}" for v in auc_values],
                textposition="outside",
            ))
            fig.add_hline(y=0.5, line_dash="dash", line_color="#9ca3af",
                          annotation_text="Azar 0.50")
            fig.update_layout(
                height=280, yaxis_range=[0.48, max(auc_values)*1.05],
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True)
            st.caption(
                f"Período test: {e_meta.get('test_start','')} → {e_meta.get('test_end','')}  "
                f"({e_meta.get('n_test',0):,} observaciones)"
            )

        with col_e2:
            # Métricas de estrategia
            st.subheader("Estrategia ensemble (P ≥ 0.53)")
            m1, m2 = st.columns(2)
            m1.metric("Señales", f"{e_perf.get('n_signals',0)}  ({e_perf.get('signal_pct',0):.1f}%)")
            m2.metric("Win rate",       f"{e_perf.get('win_rate',0)*100:.1f}%")
            m3, m4 = st.columns(2)
            m3.metric("Sharpe anual",   f"{e_perf.get('sharpe',0):.2f}")
            m4.metric("Profit factor",  f"{e_perf.get('profit_factor',0):.2f}")

            # Pesos de votación
            st.caption("Pesos de votación (proporcional a AUC - 0.5):")
            weight_data = {
                "Modelo": ["WoE+LR", "LightGBM", "ROCKET"],
                "AUC":    [e_indiv.get("woe_lr",0), e_indiv.get("lightgbm",0), e_indiv.get("rocket",0)],
                "Peso":   [
                    f"{e_models.get('woe_lr',{}).get('weight',0)*100:.1f}%",
                    f"{e_models.get('lightgbm',{}).get('weight',0)*100:.1f}%",
                    f"{e_models.get('rocket',{}).get('weight',0)*100:.1f}%",
                ],
            }
            st.dataframe(pd.DataFrame(weight_data), use_container_width=True, hide_index=True)

        # Calibración
        if e_cal:
            st.subheader("Calibración del ensemble")
            df_ecal = pd.DataFrame(e_cal)
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(x=df_ecal["bucket"], y=(df_ecal["actual_rate"]*100).round(1),
                                  name="Tasa real %", marker_color="#22c55e",
                                  text=(df_ecal["actual_rate"]*100).round(0),
                                  texttemplate="%{text:.0f}%", textposition="outside"))
            fig2.add_trace(go.Scatter(x=df_ecal["bucket"], y=(df_ecal["mean_pred"]*100).round(1),
                                      name="P predicha %", mode="lines+markers",
                                      line=dict(color="#f59e0b", dash="dot", width=2)))
            fig2.update_layout(height=280, legend=dict(orientation="h"),
                               plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig2, use_container_width=True)

        # Win rate por ticker
        if e_ticks:
            st.subheader("Win rate por ticker en señales del ensemble")
            df_et = pd.DataFrame(e_ticks).sort_values("win_rate", ascending=False)
            import plotly.express as px
            fig3 = px.bar(df_et, x="win_pct" if "win_pct" in df_et.columns else
                          df_et.assign(win_pct=lambda d: (d.win_rate*100).round(1))["win_pct"],
                          y="ticker", orientation="h",
                          text=((df_et["win_rate"]*100).round(0).astype(int).astype(str) + "%"),
                          color=(df_et["win_rate"]*100).round(1),
                          color_continuous_scale=["#ef4444","#f59e0b","#22c55e"],
                          range_color=[35, 70])
            fig3.add_vline(x=50, line_dash="dash", line_color="#9ca3af")
            fig3.update_layout(height=350, coloraxis_showscale=False,
                               plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig3, use_container_width=True)

        if st.button("🔄 Re-entrenar ensemble (~5 min)", type="primary"):
            with st.spinner("Optuna 50 trials + ROCKET + WoE..."):
                rc, out = run_script(["scripts/run_ensemble.py"])
            st.code(out[-5000:]); st.cache_data.clear(); st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA 5 — WoE ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

elif page.startswith("🔬"):
    st.title("WoE Analysis — 32 features")

    woe_data = load_json("woe_results.json")
    if not woe_data:
        st.warning("No hay análisis WoE. Corre run_woe.py primero.")
        st.stop()

    meta   = woe_data.get("meta", {})
    iv_sum = woe_data.get("iv_summary", [])
    bins   = woe_data.get("bins_by_feature", {})

    st.caption(f"Generado: {meta.get('date','—')} · {meta.get('n_obs',0):,} obs · "
               f"{meta.get('n_tickers',0)} tickers · event rate {meta.get('event_rate',0)*100:.1f}%")

    # IV ranking
    st.subheader("Information Value por feature")
    df_iv = pd.DataFrame(iv_sum)
    if not df_iv.empty:
        df_iv["iv_pct"] = df_iv["iv"] * 1000
        fig = px.bar(df_iv, x="iv_pct", y="feature", orientation="h",
                     color="iv_pct",
                     color_continuous_scale=["#374151","#22c55e"],
                     labels={"iv_pct": "IV × 1000", "feature": ""},
                     title="IV × 1000 (umbral débil = 20)")
        fig.update_layout(height=580, showlegend=False, coloraxis_showscale=False,
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)

    # Bins detallados
    st.subheader("Patrón por bins — selecciona un feature")
    feat_names = [r["feature"] for r in iv_sum[:12]]
    selected = st.selectbox("Feature", feat_names)

    if selected and selected in bins:
        df_bins = pd.DataFrame(bins[selected])
        col1, col2 = st.columns(2)
        with col1:
            fig = px.bar(df_bins, x="event_rate", y="label", orientation="h",
                         color="event_rate",
                         color_continuous_scale=["#ef4444","#f59e0b","#22c55e"],
                         range_color=[0.42, 0.60],
                         labels={"event_rate": "Tasa de subida", "label": ""},
                         title="Tasa de subida (%) por bin")
            fig.add_vline(x=meta.get("event_rate", 0.492), line_dash="dash",
                          line_color="white", annotation_text="Base rate")
            fig.update_layout(height=350, coloraxis_showscale=False,
                               plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            fig = px.bar(df_bins, x="woe", y="label", orientation="h",
                         color="woe",
                         color_continuous_scale=["#ef4444","#374151","#22c55e"],
                         range_color=[-0.35, 0.35],
                         labels={"woe": "WoE", "label": ""},
                         title="WoE por bin (positivo = favorece subida)")
            fig.update_layout(height=350, coloraxis_showscale=False,
                               plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True)

    if st.button("🔄 Re-correr análisis WoE"):
        with st.spinner("Calculando WoE sobre 9,700 observaciones..."):
            rc, out = run_script(["scripts/run_woe.py"])
        st.code(out[-2000:]); st.cache_data.clear(); st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA 6 — BASE DE DATOS
# ══════════════════════════════════════════════════════════════════════════════

elif page.startswith("🗄️"):
    st.title("Base de datos local")

    market_dir = ROOT / "data" / "market"
    parquets   = list(market_dir.glob("*.parquet")) if market_dir.exists() else []

    total_mb = sum(f.stat().st_size for f in parquets) / 1024 / 1024
    st.metric("Archivos parquet", len(parquets), f"{total_mb:.1f} MB total")

    if parquets:
        from src.data.store import ALL_SYMBOLS, load as store_load

        rows = []
        for name, symbol in ALL_SYMBOLS.items():
            df = store_load(symbol)
            safe = symbol.replace("/","_").replace("^","")
            path = market_dir / f"{safe}.parquet"
            if df is not None:
                rows.append({
                    "Nombre": name,
                    "Símbolo": symbol,
                    "Días": len(df),
                    "Desde": str(df.index[0].date()),
                    "Hasta": str(df.index[-1].date()),
                    "KB": round(path.stat().st_size/1024, 0) if path.exists() else 0,
                })
            else:
                rows.append({"Nombre": name, "Símbolo": symbol,
                             "Días": 0, "Desde": "—", "Hasta": "—", "KB": 0})

        df_store = pd.DataFrame(rows)
        st.dataframe(df_store, use_container_width=True, hide_index=True,
                     column_config={"Días": st.column_config.NumberColumn(format="%d")})

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Actualizar BD (solo días nuevos)", use_container_width=True, type="primary"):
            with st.spinner("Actualizando... (~10 seg)"):
                rc, out = run_script(["scripts/build_database.py", "--update"])
            st.code(out[-3000:]); st.cache_data.clear(); st.rerun()
    with col2:
        if st.button("⬇️ Reconstruir BD completa (~3 min)", use_container_width=True):
            with st.spinner("Descargando historial máximo de 23 símbolos..."):
                rc, out = run_script(["scripts/build_database.py"])
            st.code(out[-3000:]); st.cache_data.clear(); st.rerun()

    # Gráfica: precio histórico de cualquier ticker
    st.divider()
    st.subheader("Explorar precio histórico")
    ticker_sel = st.selectbox("Ticker", list(ALL_SYMBOLS.keys()))
    if ticker_sel:
        from src.data.store import get as store_get
        df_plot = store_get(ticker_sel)
        if df_plot is not None:
            fig = px.line(df_plot.tail(504), y="Close",
                          title=f"{ticker_sel} — últimos 2 años",
                          labels={"Close": "Precio cierre", "Date": ""})
            fig.update_layout(height=350, plot_bgcolor="rgba(0,0,0,0)",
                              paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA 7 — DOCUMENTACIÓN COMPLETA
# ══════════════════════════════════════════════════════════════════════════════

elif page.startswith("📖"):
    st.title("Documentación del sistema")
    st.caption("Explicación completa de arquitectura, modelo, features y flujo operativo.")

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "🏗️ Arquitectura",
        "📊 Datos y features",
        "🔬 WoE y selección",
        "🧠 Modelo ML",
        "⚖️ Risk engine",
        "🔄 Flujo diario",
    ])

    # ── TAB 1: ARQUITECTURA ───────────────────────────────────────────────────
    with tab1:
        st.header("Arquitectura general del sistema")
        st.markdown("""
El sistema es un **pipeline completo de trading cuantitativo** para la Bolsa Mexicana
de Valores (BMV). No es un sistema de high-frequency ni de arbitraje: opera en
**horizonte de 5 días hábiles** (una semana), tomando posiciones largas (long-only)
en acciones del IPC y empresas medianas mexicanas.

---
### Diagrama de flujo
```
Datos históricos (Yahoo Finance)
        │
        ▼
  Base de datos local ─── datos/market/*.parquet
  (23 símbolos: 19 BMV + 4 macro)
        │
        ├─► Features técnicos (25 indicadores)
        │         + Features macro (7 variables)
        │                 │
        │                 ▼
        │         WoE transformation
        │         (Weight of Evidence)
        │                 │
        │                 ▼
        │         Logistic Regression
        │         Walk-Forward (6 folds)
        │                 │
        │                 ▼
        ├─► P(subida 5d) por ticker     ← OUTPUT PRINCIPAL
        │                 │
        │                 ▼
        │         Risk Engine
        │   (Kelly + ATR stops + correlación)
        │                 │
        │                 ▼
        │         signals_today.json
        │
        └─► Monitor intraday (cada 5 min)
                    │
                    ▼
            Alertas macOS + log
```

---
### Módulos del sistema

| Archivo | Función |
|---|---|
| `src/data/store.py` | Descarga y caché local en Parquet |
| `src/ml/features.py` | Cómputo de 32 features (25 técnicos + 7 macro) |
| `src/ml/woe.py` | WoE/IV: transformación y selección de variables |
| `src/ml/risk_engine.py` | Kelly criterion, ATR stops, correlación |
| `src/ml/paper_trading.py` | Motor de paper trading y métricas |
| `scripts/run_backtest.py` | Backtest heurístico (baseline) |
| `scripts/run_woe.py` | Análisis WoE sobre historial completo |
| `scripts/run_model.py` | Walk-forward training + validación |
| `scripts/generate_signals.py` | Señales para la próxima semana |
| `scripts/monitor_intraday.py` | Monitor en tiempo real durante sesión |
| `scripts/paper_trading.py` | CLI para gestión del journal |
| `scripts/daily_update.sh` | Cron job de actualización diaria |

---
### Por qué estas decisiones de diseño

**Horizonte de 5 días**: La BMV tiene menor liquidez intraday que NYSE/NASDAQ.
Los costos de transacción (comisión + spread) en GBM son ~0.25% por lado.
Para que una operación sea rentable necesita al menos 1-2% de movimiento.
Los retornos de 5 días capturan oscilaciones semanales sin tanto ruido intraday.

**Long-only**: La mayoría de los intermediarios mexicanos (GBM, Kuspit, Actinver)
no ofrecen ventas en corto sobre acciones BMV de forma sencilla para minoristas.

**19 tickers**: El universo de acciones BMV con volumen suficiente (>500k MXN/día
promedio) y datos históricos confiables en Yahoo Finance es limitado. Incluimos
las principales de IPC más algunas medianas con buen historial.
""")

    # ── TAB 2: DATOS Y FEATURES ───────────────────────────────────────────────
    with tab2:
        st.header("Datos y features")

        st.subheader("Fuente de datos")
        st.markdown("""
Toda la información proviene de **Yahoo Finance** a través de `yfinance`.
Los datos se descargan una vez al día (después del cierre, ~16:30 hora México)
y se almacenan localmente en **formato Parquet** (`data/market/*.parquet`).

- **Precio OHLCV**: Open, High, Low, Close (ajustado por splits y dividendos), Volume
- **Frecuencia**: Diaria
- **Historial máximo**: ~5 años (Yahoo Finance limita la descarga)
- **Actualización incremental**: Solo descarga los días faltantes, no reprocesa todo

**19 tickers BMV**:
`ALFAA.MX, ALSEA.MX, AMXL.MX, ASURB.MX, BIMBOA.MX, BOLSAA.MX, CEMEXCPO.MX,
FEMSAUBD.MX, GAPB.MX, GCARSOA1.MX, GMEXICOB.MX, GRUMAB.MX, KIMBERA.MX,
LABB.MX, OMAB.MX, PINFRA.MX, TLEVISACPO.MX, VESTA.MX, WALMEX.MX`

**4 símbolos macro**:
`MXN=X` (USD/MXN), `NAFTRAC.MX` (proxy del IPC), `CL=F` (WTI petróleo), `^GSPC` (S&P 500)
""")

        st.subheader("Features técnicos (25)")
        st.markdown("""
Todos se calculan sobre la ventana de datos **disponible en la fecha de señal**,
sin look-ahead bias (no se usa información del futuro).

**Osciladores (5 features)**:

| Feature | Descripción | Rango |
|---|---|---|
| `rsi14` | RSI 14 días — sobrecompra > 70, sobreventa < 30 | 0–100 |
| `stoch_k` | Stochastic %K 14 días — posición en rango HL | 0–100 |
| `williams_r` | Williams %R 14 días — similar a Stoch invertido | -100–0 |
| `cci14` | Commodity Channel Index 14 días | sin límite |
| `mfi14` | Money Flow Index — RSI ponderado por volumen | 0–100 |

**Estructura de precio (6 features)**:

| Feature | Descripción |
|---|---|
| `bb_pct` | Posición dentro de Bandas Bollinger (%B) |
| `price_vs_sma20` | (Precio / SMA20) - 1 en % |
| `price_vs_sma50` | (Precio / SMA50) - 1 en % |
| `sma20_vs_sma50` | (SMA20 / SMA50) - 1 — tendencia media |
| `pos_52w` | Posición en rango 52 semanas (0=mínimo, 1=máximo) |
| `dist_20d_low` | Distancia al mínimo de 20 días en % |

**Momentum y tendencia (5 features)**:

| Feature | Descripción |
|---|---|
| `ret_5d` | Retorno de los últimos 5 días |
| `ret_10d` | Retorno de los últimos 10 días |
| `ret_20d` | Retorno de los últimos 20 días |
| `sma20_slope` | Pendiente lineal de SMA20 (últimos 5 días) |
| `trend_5d` | Pendiente lineal del precio (últimos 5 días) |

**Volumen (4 features)**:

| Feature | Descripción |
|---|---|
| `vol_ratio_20d` | Volumen hoy / media 20 días |
| `vol_down_ratio` | Fracción del volumen en días bajistas (20d) |
| `vol_up_ratio` | Fracción del volumen en días alcistas (20d) |
| `obv_slope` | Pendiente del On-Balance Volume (20 días) |

**Volatilidad y régimen (5 features)**:

| Feature | Descripción |
|---|---|
| `atr_pct` | ATR 14 días / precio — volatilidad relativa |
| `bb_width` | Ancho de Bollinger Bands / precio medio |
| `hv_ratio` | Volatilidad histórica 20d vs 60d |
| `hl_range_pct` | (High - Low) / Close — rango intraday |
| `consec_down` | Días consecutivos a la baja (señal de capitulación) |
""")

        st.subheader("Features macro (7)")
        st.markdown("""
Capturan el contexto de mercado que afecta a **todas** las acciones BMV:

| Feature | Descripción | Por qué importa |
|---|---|---|
| `usdmxn_ret5` | Retorno USD/MXN últimos 5 días | Peso fuerte → BMV sube; depreciación → presión bajista |
| `usdmxn_vs_ma20` | USD/MXN vs su media móvil 20 días | Tendencia del tipo de cambio |
| `mkt_ret10` | Retorno NAFTRAC últimos 10 días | Momentum del mercado completo |
| `mkt_trend` | Pendiente lineal NAFTRAC 10 días | ¿Mercado en tendencia o lateral? |
| `rel_str5` | Retorno ticker - retorno NAFTRAC (5d) | ¿La acción supera al índice? |
| `wti_ret5` | Retorno WTI petróleo últimos 5 días | Crucial para PEMEX-relacionadas y economía MX |
| `sp500_ret5` | Retorno S&P 500 últimos 5 días | EE.UU. arrastra a México |

**Nota importante sobre `rel_str5`**: Si el mercado subió 3% pero la acción solo 1%,
`rel_str5 = -2%`. Una acción con `rel_str5 > 0` está outperforming al mercado —
señal de momentum relativo positivo.
""")

    # ── TAB 3: WoE ────────────────────────────────────────────────────────────
    with tab3:
        st.header("Weight of Evidence (WoE) y selección de features")

        st.subheader("¿Qué es WoE?")
        st.markdown(r"""
WoE es una técnica de transformación de variables usada ampliamente en **credit scoring**
y **riesgo financiero**. Para cada variable, mide cuánto predice el evento de interés
(en nuestro caso: ¿sube la acción más de 2% en 5 días?).

**Definición matemática**:

Para una variable $X$ binada en $k$ intervalos:

$$
\text{WoE}_k = \ln\!\left(\frac{P(\text{evento} \mid X \in \text{bin}_k)}{P(\text{no evento} \mid X \in \text{bin}_k)}\right) - \ln\!\left(\frac{P(\text{evento})}{P(\text{no evento})}\right)
$$

O equivalentemente:

$$
\text{WoE}_k = \ln\!\left(\frac{\text{Events}_k / \text{Total Events}}{\text{Non-events}_k / \text{Total Non-events}}\right)
$$

- **WoE > 0**: ese rango del indicador está asociado a subidas (favorable)
- **WoE < 0**: ese rango está asociado a bajadas (desfavorable)
- **WoE ≈ 0**: ese rango no discrimina

**Information Value (IV)**:

$$
\text{IV} = \sum_k \left(\frac{E_k}{E_T} - \frac{N_k}{N_T}\right) \cdot \text{WoE}_k
$$

| IV | Poder predictivo |
|---|---|
| < 0.02 | Sin valor |
| 0.02 – 0.10 | Débil |
| 0.10 – 0.30 | Medio |
| > 0.30 | Fuerte |
""")

        st.subheader("¿Por qué WoE y no usar las variables crudas?")
        st.markdown("""
**Tres razones principales**:

1. **Relaciones no lineales**: Un RSI de 30 (sobreventa) tiene un significado
   completamente diferente a RSI de 50 (neutral) y de 70 (sobrecompra). Con WoE
   capturamos esa forma no lineal automáticamente.

2. **Interpretabilidad directa**: La transformación WoE convierte el problema en
   "¿cuánto log-odds aporta este valor?". El modelo logístico final es exactamente:

   $$\\text{log-odds} = \\beta_0 + \\beta_1 \\cdot \\text{WoE}_{\\text{rsi14}} + \\beta_2 \\cdot \\text{WoE}_{\\text{ret5d}} + \\ldots$$

   Esto hace que cada coeficiente sea directamente comparable.

3. **Robustez a outliers**: Los bins absorben valores extremos. Un RSI de 95 y uno
   de 85 caen en el mismo bin y reciben el mismo WoE.

**Proceso de binning**:
- Se usan **8 bins por feature** basados en cuantiles (igual frecuencia)
- Bins con menos del 2% de observaciones se fusionan con el vecino más cercano
- El cálculo usa **todo el historial disponible** excepto la ventana de test
  (para evitar data leakage en walk-forward)
""")

        st.subheader("Resultado del análisis WoE en nuestros datos")
        st.markdown("""
Del análisis sobre ~9,700 observaciones (19 tickers × ~5 años):

**Features con mayor poder predictivo (IV más alto)**:
- `rel_str5` — fuerza relativa vs mercado
- `ret_5d` — momentum de 5 días
- `mkt_ret10` — momentum del mercado
- `price_vs_sma20` — distancia a media móvil (mean-reversion)
- `consec_down` — días consecutivos a la baja (rebote)
- `usdmxn_ret5` — movimiento del peso

**Hallazgo clave — Mean Reversion dominante**:
La BMV tiene un comportamiento marcadamente de **reversión a la media** en el
horizonte de 5 días. Acciones que cayeron mucho (`ret_5d` muy negativo, cerca de
su mínimo 52 semanas, `consec_down` alto) tienen WoE positivo — tienden a rebotar.
Esto es opuesto al momentum puro que funciona en mercados más líquidos como NYSE.
""")

    # ── TAB 4: MODELO ML ──────────────────────────────────────────────────────
    with tab4:
        st.header("Modelo de Machine Learning")

        st.subheader("Variable objetivo (target)")
        st.markdown(r"""
$$
y = \begin{cases} 1 & \text{si } \frac{C_{t+5} - C_t}{C_t} > 2\% \\ 0 & \text{en caso contrario} \end{cases}
$$

El umbral del **2% en 5 días** tiene una justificación práctica:
- Comisión GBM: ~0.25% por lado = 0.5% round-trip
- Spread estimado en acción líquida BMV: ~0.3%
- Costo total mínimo: ~0.8%
- Buffer de seguridad: dejamos que el modelo capture movimientos de ≥2%

Con el historial disponible, la **base rate (event rate) es ~49%** — el mercado
es casi moneda al aire, lo que hace que cualquier AUC > 0.53 sea valioso.
""")

        st.subheader("Logistic Regression con WoE features")
        st.markdown(r"""
El modelo es una **Regresión Logística** sobre las features ya transformadas por WoE:

$$
P(\text{subida}) = \sigma\!\left(\beta_0 + \sum_{j=1}^{32} \beta_j \cdot \text{WoE}(x_j)\right)
$$

donde $\sigma(z) = \frac{1}{1 + e^{-z}}$ es la función sigmoide.

**¿Por qué Logistic Regression y no un modelo más complejo?**

1. **Calibración**: Las probabilidades de un modelo logístico están bien calibradas.
   Si el modelo dice P=0.60, en la práctica ~60% de esos trades ganan. Esto es
   crítico para el Kelly criterion en el risk engine.

2. **Regularización**: Usamos `C=1.0` (regularización L2) para prevenir overfitting
   dado el tamaño limitado de datos (~500–800 obs por fold de entrenamiento).

3. **Velocidad**: Se re-entrena en cada fold en <1 segundo. LightGBM también se
   incluye como benchmark pero requiere más datos para superar LR.

4. **Interpretabilidad**: Con WoE + LR puedes leer directamente cuál feature
   y en qué dirección contribuye a la señal.
""")

        st.subheader("Walk-Forward Validation")
        st.markdown(r"""
La validación walk-forward es la forma **más rigurosa** de evaluar estrategias
de trading, porque simula exactamente cómo operarías en tiempo real.

**Estructura de los folds**:

```
Fold 1:  [Jan 2021 ─── Dec 2022]  TRAIN  →  [Jan-Mar 2023]  TEST
Fold 2:  [Jan 2021 ─── Mar 2023]  TRAIN  →  [Apr-Jun 2023]  TEST
Fold 3:  [Jan 2021 ─── Jun 2023]  TRAIN  →  [Jul-Sep 2023]  TEST
Fold 4:  [Jan 2021 ─── Sep 2023]  TRAIN  →  [Oct-Dic 2023]  TEST
Fold 5:  [Jan 2021 ─── Dec 2023]  TRAIN  →  [Jan-Mar 2024]  TEST
Fold 6:  [Jan 2021 ─── Mar 2024]  TRAIN  →  [Apr-Jun 2024]  TEST
```

**Ventana creciente (expanding window)**: cada fold usa todos los datos históricos
disponibles hasta la fecha de corte. Esto simula que el modelo tiene más información
conforme avanza el tiempo.

**Sin data leakage**: El WoE se re-calcula en cada fold usando SOLO datos de
entrenamiento. Las features del test set se transforman con los bins aprendidos
en train, nunca al revés.

**Métricas reportadas**:
- `AUC` (Area Under ROC Curve): discriminación general. 0.50 = azar, 1.0 = perfecto
- `Brier Score`: calibración (0 = perfecta)
- `Win Rate`: % de trades ganadores cuando P > umbral
- `Sharpe`: retorno medio / desviación estándar (mayor = mejor riesgo/retorno)
- `Profit Factor`: suma ganancias / suma pérdidas (> 1 = rentable)

**Umbral de señal**: Solo se generan señales cuando P(subida) > **0.53**.
Este umbral fue optimizado sobre los folds de validación para maximizar win rate
sin sacrificar demasiado el número de oportunidades.
""")

    # ── TAB 5: RISK ENGINE ────────────────────────────────────────────────────
    with tab5:
        st.header("Risk Engine")

        st.subheader("1. Kelly Criterion — tamaño de posición")
        st.markdown(r"""
El **Criterio de Kelly** determina qué fracción del capital invertir en cada trade
para maximizar el crecimiento logarítmico del capital a largo plazo.

**Fórmula completa de Kelly**:

$$
f^* = \frac{p \cdot b - q}{b}
$$

donde:
- $p$ = probabilidad de ganar (= P(subida) del modelo)
- $q = 1 - p$ = probabilidad de perder
- $b$ = ratio ganancia/pérdida = $\frac{\text{avg win}}{\text{avg loss}}$

**En la práctica usamos Kelly fraccional** para reducir volatilidad del portafolio:

$$
f_{\text{ajustado}} = f^* \times \text{kelly\_frac} \times \text{corr\_penalty}
$$

- `kelly_frac = 0.25` (25% del Kelly completo) — protección contra estimaciones
  erróneas del modelo
- `max_position = 0.20` (máximo 20% del capital en un solo ticker)
- `corr_penalty` — reducción si el ticker está muy correlacionado con posiciones
  ya abiertas (ver abajo)

**Intuición**: Con P=0.58 y avg_win/avg_loss=1.4, Kelly da f*≈18.6%.
Con Kelly fraccional al 25%: invertimos ~4.6% del capital.
""")

        st.subheader("2. ATR Stops — niveles de salida")
        st.markdown(r"""
El **Average True Range (ATR)** mide la volatilidad "real" del instrumento,
considerando gaps entre sesiones:

$$
TR_t = \max(H_t - L_t,\; |H_t - C_{t-1}|,\; |L_t - C_{t-1}|)
$$

$$
ATR_{14} = \frac{1}{14} \sum_{i=0}^{13} TR_{t-i}
$$

**Niveles derivados del ATR**:

| Nivel | Fórmula | Descripción |
|---|---|---|
| **Stop Loss** | Entry − 2.0 × ATR | Salida obligatoria si baja demasiado |
| **Target 1** | Entry + 1.5 × ATR | Primer objetivo de ganancia (parcial) |
| **Target 2** | Entry + 3.0 × ATR | Objetivo completo (RRR = 1.5) |

**Stop Trailing**: Cuando se alcanza T1, el stop se mueve al precio de entrada
(break-even). Así, los trades que alcanzan T1 no pueden terminar en pérdida.

**Risk/Reward Ratio mínimo**: Solo se aceptan trades con RRR ≥ 1.5
(ganar al menos 1.5 veces lo que se arriesga).
""")

        st.subheader("3. Penalización por correlación")
        st.markdown(r"""
Si ya tienes posición en CEMEXCPO.MX y GMEXICOB.MX (ambas correlacionadas con
el ciclo económico mexicano), añadir más acciones altamente correlacionadas
**no reduce el riesgo del portafolio** — solo aumenta concentración.

**Cálculo**:

$$
\rho_{\text{max}} = \max_{s \in \text{portafolio}} \text{corr}(r_{\text{nuevo}}, r_s)
$$

$$
\text{corr\_penalty} = \begin{cases}
1.0 & \text{si } \rho_{\text{max}} < 0.70 \\
0.5 & \text{si } 0.70 \leq \rho_{\text{max}} < 0.85 \\
0.0 & \text{si } \rho_{\text{max}} \geq 0.85
\end{cases}
$$

La correlación se calcula sobre **250 días hábiles** (1 año) de retornos diarios.
""")

        st.subheader("4. Reglas del portafolio")
        st.markdown("""
| Regla | Valor | Justificación |
|---|---|---|
| **Capital por posición** | 5–20% del capital total | Diversificación mínima en 5 tickers |
| **Máx posiciones simultáneas** | 5 | Con 100k MXN, posiciones de 20k son manejables |
| **Máx riesgo por trade** | 2% del capital | Regla clásica de gestión de riesgo |
| **Umbral de probabilidad** | P > 0.53 | Calibrado sobre walk-forward |
| **RRR mínimo** | 1.5 | Stop 2×ATR, Target 3×ATR |
| **Solo LONG** | Sí | Brokers mexicanos no facilitan shorts a minoristas |
""")

    # ── TAB 6: FLUJO DIARIO ───────────────────────────────────────────────────
    with tab6:
        st.header("Flujo operativo diario / semanal")

        st.subheader("Automático (cron job)")
        st.markdown("""
El archivo `scripts/daily_update.sh` se ejecuta automáticamente de lunes a viernes
a las **16:30 hora México** (después del cierre de la BMV a las 15:00).

```bash
# Cron entry:
# 30 16 * * 1-5 /Users/rod/Projects/stock-market/scripts/daily_update.sh

# 1. Actualiza todos los parquets con el precio de cierre del día
python scripts/build_database.py --update

# 2. Solo los viernes: genera señales para la semana siguiente
if [ es_viernes ]; then
    python scripts/generate_signals.py --capital 100000
    python scripts/paper_trading.py init
    osascript -e 'display notification "Señales listas" ...'
fi
```
""")

        st.subheader("Manual (tú decides cuándo)")
        st.markdown("""
**Proceso completo — inicio de semana (lunes ~8:00 AM)**:

```
1. Abrir Streamlit → Señales de hoy
2. Revisar las N señales con P(↑) > 53%
3. Para cada señal:
   - Verificar que el precio de apertura está cerca del Entry
   - Colocar orden en GBM: limite en Entry, stop en Stop Loss
   - Anotarlo en tu broker
4. Activar monitor intraday:
   python scripts/monitor_intraday.py
   (corre en background, alerta si toca Stop o Target)
```

**Cierre de semana (viernes ~15:30)**:

```
1. Streamlit → Paper Trading → botón "Settle"
   (descarga precios reales y simula los resultados)
2. Revisar scorecard: win rate, PnL, Sharpe
3. El cron job de las 16:30 ya genera las señales del lunes
```

**Si quieres re-entrenar el modelo completo** (mensual recomendado):

```bash
python scripts/run_woe.py        # ~2 min — recalcula IV de 32 features
python scripts/run_model.py      # ~5 min — walk-forward completo
python scripts/generate_signals.py  # regenera señales con modelo nuevo
```
""")

        st.subheader("Monitor intraday — ¿cómo funciona?")
        st.markdown("""
`monitor_intraday.py` corre un loop cada 5 minutos durante el horario de la BMV
(8:30 – 15:00 hora México):

1. Descarga el precio más reciente de cada posición abierta via `yfinance` (interval=2m)
2. Verifica si el precio tocó el **Stop Loss** → alerta de salida urgente
3. Verifica si tocó **Target 1** → mueve stop a break-even, alerta de T1
4. Verifica si tocó **Target 2** → alerta de cierre completo
5. Guarda el estado en `data/monitor_state.json`
6. Registra todas las alertas en `data/monitor_log.jsonl`
7. Envía notificación macOS (aparece en la esquina de la pantalla)

**Nota importante**: El monitor **no ejecuta órdenes automáticamente** — solo alerta.
Tú eres quien coloca y cierra las órdenes en GBM. Esto es intencional para mantener
control total sobre las ejecuciones.
""")

        st.subheader("Limitaciones conocidas del sistema")
        st.markdown("""
> Ser transparente sobre las limitaciones es parte del diseño robusto.

**1. Datos de Yahoo Finance**:
- Precios ajustados por splits/dividendos (correcto para backtesting), pero los
  ajustes retroactivos pueden afectar el historial.
- Volumen reportado puede diferir del volumen real BMV.
- Algunos tickers tienen gaps o datos faltantes.

**2. Universo limitado (19 tickers)**:
- Solo acciones con suficiente historial y liquidez en Yahoo Finance.
- No incluye acciones nuevas ni las de baja capitalización que pueden tener
  los movimientos más grandes.

**3. El modelo es predictivo, no causal**:
- AUC de ~0.54–0.56 significa que el modelo acierta marginalmente más que el azar.
- En mercados con régimen diferente (crisis, elecciones, pandemia) el modelo
  puede degradarse significativamente.

**4. Costos de transacción simplificados**:
- El backtest asume entrada al cierre del viernes y salida al cierre del siguiente
  viernes. En realidad entras el lunes en la apertura — puede haber gap.
- Los costos reales incluyen: comisión (~0.25%), IVA sobre comisión (16%), spread,
  e impacto de mercado en acciones de menor liquidez.

**5. Sin re-balanceo intraday**:
- El sistema toma la posición el lunes y la revisa el viernes. No ajusta ante
  noticias corporativas, cambios de guidance o eventos macro durante la semana.

**Recomendación**: Corre el sistema en **paper trading 6 meses** antes de usar
capital real. Eso te dará ~24 semanas de señales (480+ trades) para validar
estadísticamente que el edge es real en condiciones de mercado actuales.
""")

        st.info("""
**¿Cuándo usar capital real?**
Cuando el paper trading muestre:
✅ Win rate > 52% sobre ≥ 50 trades cerrados
✅ Profit factor > 1.1
✅ Sharpe ≥ 0.5 anualizado
✅ Drawdown máximo < 15%

Con esas métricas, hay evidencia estadística suficiente para asumir que el edge
es real y no ruido. Empieza con capital pequeño (~10–20k MXN) y escala gradualmente.
""")
