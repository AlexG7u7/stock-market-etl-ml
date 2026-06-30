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
        "🦾  Super Modelo",
        "🏆  Ranking Mensual",
        "📊  Research & Eval",
        "👀  Monitor",
        "📋  Paper Trading",
        "🏦  GBM Broker",
        "🗄️  Base de datos",
    ])

    st.divider()

    # ── Generar señales (siempre visible) ──────────────────────────────────────
    st.caption("**Generar señales**")
    try:
        from src.data.universes import UNIVERSES as _U, UNIVERSE_ORDER as _UO
        _gen_options = ["🌐 Todos"] + list(_UO)
    except Exception:
        _gen_options = ["🌐 Todos"]
    universo_sidebar = st.selectbox("Universo", _gen_options, key="_gen_u_sb", label_visibility="collapsed")
    if st.button("▶️ Generar señales", type="primary", use_container_width=True):
        st.session_state["_gen_trigger"] = universo_sidebar
        st.session_state["_gen_capital"] = capital_global
        st.rerun()

    st.divider()
    if st.button("🔄 Actualizar datos", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA — SUPER MODELO (meta-orquestador cross-universo)
# ══════════════════════════════════════════════════════════════════════════════

if page.startswith("🦾"):
    st.title("🦾 Super Modelo — Meta-orquestador")
    st.caption("Fusiona 4 modelos base (LGBM + ensemble + heurístico + LSTM) + régimen + noticias · KB operativa en Gemini · ranking maestro ~87 tickers")

    sm_path = ROOT / "data" / "super_signals.json"
    insights_path = ROOT / "data" / "insights_today.json"

    col_a, col_b = st.columns([3, 1])
    with col_b:
        top_g = st.number_input("Top a validar con Gemini", 3, 20, 10, step=1)
        use_gem = st.toggle("Usar Gemini", value=True)
        use_stack = st.toggle("Stacking LR (KB-060)", value=True)
        if st.button("🦾 Correr Super Modelo", type="primary", use_container_width=True):
            cmd = ["scripts/run_super_model.py", "--top-gemini", str(int(top_g))]
            if not use_gem:
                cmd.append("--no-gemini")
            if not use_stack:
                cmd.append("--no-stacking")
            with st.spinner("Entrenando modelos base, fusionando y validando… (~30s)"):
                rc, out = run_script(cmd)
            if rc == 0:
                st.success("✅ Super modelo actualizado")
                st.cache_data.clear()
            else:
                st.error("❌ Error")
                with st.expander("Log"):
                    st.code(out[-2000:])
            st.rerun()

    if not sm_path.exists():
        st.info("Aún no hay resultados. Pulsa **🦾 Correr Super Modelo**.")
        st.stop()

    @st.cache_data(ttl=120)
    def _load_insights() -> dict | None:
        if insights_path.exists():
            return json.loads(insights_path.read_text())
        return None

    @st.cache_data(ttl=120)
    def _load_super() -> dict:
        return json.loads(sm_path.read_text())

    bundle = _load_insights()
    sm = _load_super()
    ranking = sm.get("master_ranking", [])
    gs = sm.get("gemini_summary", {})
    if bundle:
        gs = bundle.get("gemini_summary") or gs
        pb = bundle.get("portfolio") or {}
    else:
        pb = sm.get("portfolio_brief") or {}

    with col_a:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Tickers rankeados", sm.get("n_tickers", 0))
        if gs.get("agent") == "gemini_trader":
            c2.metric("APOSTAR", gs.get("apostar", 0))
            c3.metric("ESPERAR", gs.get("esperar", 0))
            c4.metric("EVITAR", gs.get("evitar", 0))
        else:
            c2.metric("Validados Gemini", gs.get("validados", 0))
            c3.metric("Confirmados", gs.get("confirma", 0))
            c4.metric("Vetados", gs.get("veta", 0))
        modo = gs.get("modo", "?")
        st.caption(f"Generado: {sm.get('generated_at','?')[:16]} · "
                   f"Gemini: {modo} · {sm.get('elapsed_sec','?')}s")
        if bundle:
            st.caption(f"📦 InsightsBundle v{bundle.get('schema_version','?')} · "
                       f"{'paper only' if bundle.get('bet_policy',{}).get('paper_only') else 'live'}")

    if pb.get("resumen_ejecutivo"):
        st.subheader("📋 Brief de portafolio (trader agent)")
        st.info(pb["resumen_ejecutivo"])
        pc1, pc2, pc3 = st.columns(3)
        if pb.get("apostar"):
            pc1.markdown("**Apostar:** " + ", ".join(pb["apostar"]))
        if pb.get("esperar"):
            pc2.markdown("**Esperar:** " + ", ".join(pb["esperar"][:8]))
        if pb.get("evitar"):
            pc3.markdown("**Evitar:** " + ", ".join(pb["evitar"][:8]))
        if pb.get("incertidumbres_globales"):
            with st.expander("Incertidumbres globales"):
                for u in pb["incertidumbres_globales"]:
                    st.markdown(f"- {u}")

    eval_s = (bundle or {}).get("eval_summary") or {}
    if eval_s.get("message"):
        st.warning(f"Eval: {eval_s.get('verdict')} — {eval_s.get('message')}")

    # ── Insights cross-universo ──────────────────────────────────────────────
    insights = sm.get("insights", [])
    if insights:
        st.subheader("💡 Insights masivos")
        for ins in insights:
            tipo = ins.get("tipo", "")
            icon = {"Consenso fuerte": "🟢", "Divergencia": "🟡", "Veto por noticias": "🔴",
                    "Concentración": "⚠️", "Régimen": "🌐"}.get(tipo, "•")
            st.markdown(f"{icon} **{tipo}** — {ins.get('texto','')}")

    st.divider()

    # ── Top validado por Gemini ──────────────────────────────────────────────
    st.subheader("🎯 Top — SuperModel + perspectiva del trader (Gemini)")
    top_items = [r for r in ranking if "gemini" in r][:int(top_g)]
    if not top_items:
        top_items = ranking[:10]

    for item in top_items:
        g = item.get("gemini", {})
        ver = g.get("veredicto", "—")
        ver_color = {
            "CONFIRMA": "🟢", "DEGRADA": "🟡", "VETA": "🔴",
            "APOSTAR": "🟢", "ESPERAR": "🟡", "EVITAR": "🔴",
        }.get(ver, "⚪")
        accion = g.get("accion_final") or (g.get("como_apostar") or {}).get("tamano", "—")

        with st.container(border=True):
            h1, h2, h3, h4 = st.columns([2, 1, 1, 1])
            h1.markdown(f"### #{item['rank_global']} {item['ticker']}")
            h1.caption(f"{item['universe']} · {item.get('moneda','')}")
            h2.metric("Convicción", f"{item['conviction']:.2f}")
            h3.metric("Desacuerdo", f"{item['disagreement']:.2f}")
            h4.metric("Gemini", f"{ver_color} {ver}")

            sigs = item.get("signals", {})
            sig_txt = " · ".join(f"{m}={v:.2f}" for m, v in sigs.items())
            st.caption(f"**Modelos base:** {sig_txt}  ·  **Régimen:** {item.get('regime','?')} "
                       f"(×{item.get('regime_factor',1)})"
                       + (f"  ·  **News:** {item['news_sent']:+.2f}" if item.get("news_sent") is not None else ""))

            if g.get("perspectiva_trader"):
                st.markdown(f"**Trader:** _{g['perspectiva_trader']}_")
            if g.get("tesis"):
                st.markdown(f"**Tesis:** {g['tesis']}")
            cev, crf = st.columns(2)
            if g.get("evidencia_a_favor"):
                cev.markdown("**A favor:**")
                for e in g["evidencia_a_favor"][:4]:
                    cev.markdown(f"- ✅ {e}")
            if g.get("red_flags"):
                crf.markdown("**Red flags:**")
                for r in g["red_flags"][:4]:
                    crf.markdown(f"- ⚠️ {r}")
            if g.get("incertidumbres_clave"):
                with st.expander("Incertidumbres"):
                    for u in g["incertidumbres_clave"][:5]:
                        st.markdown(f"- {u}")
            m = item.get("metrics") or {}
            ci = (m.get("conviction") or {}).get("ci_90")
            if ci:
                st.caption(f"Convicción IC90: [{ci[0]}, {ci[1]}]")
            st.markdown(f"**Acción sugerida: {accion}**")

    st.divider()

    # ── Ranking maestro completo ─────────────────────────────────────────────
    st.subheader("📊 Ranking maestro cross-universo")
    df_rank = pd.DataFrame([{
        "#": r["rank_global"],
        "Ticker": r["ticker"],
        "Universo": r["universe_slug"],
        "Convicción": round(r["conviction"], 3),
        "Desacuerdo": round(r["disagreement"], 3),
        "Régimen": r.get("regime", ""),
        "News": r.get("news_sent"),
        "Gemini": r.get("gemini", {}).get("veredicto", ""),
    } for r in ranking])
    st.dataframe(df_rank, use_container_width=True, hide_index=True,
                 height=min(700, 38 * len(df_rank) + 40))

    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA 0 — RANKING MENSUAL (multi-universo: BMV, USA, ETFs, Cripto, FIBRAs)
# ══════════════════════════════════════════════════════════════════════════════

if page.startswith("🏆"):
    from src.data.universes import UNIVERSES, UNIVERSE_ORDER

    st.title("🏆 Ranking Mensual — GBM Universe")
    st.caption("Modelo cross-seccional · 4 horizontes (1/2/3/4 semanas) · long-only top-5 · Gemini por ticker")

    # ── Helper: carga señal de un universo ─────────────────────────────────────
    @st.cache_data(ttl=300)
    def load_universe_signal(slug: str) -> dict:
        p = ROOT / "data" / "signals" / f"{slug}.json"
        return json.loads(p.read_text()) if p.exists() else {}

    # ── Manejar generación de señales (disparada desde sidebar) ───────────────
    if st.session_state.get("_gen_trigger"):
        universo_sel   = st.session_state.pop("_gen_trigger")
        capital_gen    = st.session_state.pop("_gen_capital", capital_global)
        universo_arg   = None if universo_sel.startswith("🌐") else universo_sel
        universos_run  = list(UNIVERSE_ORDER) if universo_arg is None else [universo_arg]

        progress_bar = st.progress(0)
        status_box   = st.empty()
        all_ok = True

        for idx, uname in enumerate(universos_run):
            slug = UNIVERSES[uname]["slug"]
            status_box.info(f"⏳ Procesando **{uname}** ({idx+1}/{len(universos_run)})…")
            progress_bar.progress(idx / len(universos_run))

            rc, out = run_script([
                "scripts/generate_all_signals.py",
                "--capital", str(int(capital_gen)),
                "--universe", uname,
            ])

            if rc == 0:
                try:
                    sig_new = json.loads((ROOT / "data" / "signals" / f"{slug}.json").read_text())
                    cons = [c["ticker"] for c in sig_new.get("consensus", []) if c["n_horizontes"] >= 3]
                    m = sig_new.get("mercado", {})
                    status_box.success(
                        f"✅ **{uname}** — {m.get('emoji','⚪')} {m.get('estado','').upper()}"
                        + (f" · Consenso: **{' · '.join(cons)}**" if cons else "")
                    )
                except Exception:
                    status_box.success(f"✅ **{uname}** generado")
            else:
                status_box.error(f"❌ Error en **{uname}**")
                with st.expander("Ver log de error"):
                    st.code(out[-1500:])
                all_ok = False

            progress_bar.progress((idx + 1) / len(universos_run))

        if all_ok:
            progress_bar.progress(1.0)
            status_box.success(f"🎉 ¡Listo! {len(universos_run)} universo(s) actualizados.")
        st.cache_data.clear()
        st.rerun()

    # ── Tabs por clase de activo ────────────────────────────────────────────────
    tab_labels = list(UNIVERSE_ORDER)
    tabs = st.tabs(tab_labels)

    for tab, uname in zip(tabs, UNIVERSE_ORDER):
        cfg  = UNIVERSES[uname]
        slug = cfg["slug"]
        sig  = load_universe_signal(slug)

        with tab:
            if not sig:
                st.info(
                    f"Sin señal para **{uname}**. Usa **▶️ Generar señales** en el panel izquierdo."
                )
                continue

            if "error" in sig:
                st.error(f"⚠️ {sig['error']}")
                continue

            # ── Régimen del mercado ──────────────────────────────────────────
            mercado    = sig.get("mercado", {})
            reg_emoji  = mercado.get("emoji", "⚪")
            reg_est    = mercado.get("estado", "—").upper()
            reg_desc   = mercado.get("descripcion", "")
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

            # ── Consenso mejorado — acción Gemini inline ──────────────────────
            consensus  = sig.get("consensus", [])
            strong     = [c for c in consensus if c["n_horizontes"] >= 3]
            by_horizon = sig.get("by_horizon", {})

            # índice de análisis Gemini: {ticker: {resumen, accion, ...}}
            gemini_idx: dict = {}
            for hdata in by_horizon.values():
                for p in hdata.get("top5", []):
                    gem = p.get("gemini", {})
                    if gem.get("resumen") and p["ticker"] not in gemini_idx:
                        gemini_idx[p["ticker"]] = gem

            if strong:
                st.divider()
                accion_colors = {"COMPRA FUERTE": "🟢", "COMPRA": "🟢", "ESPERA": "🟡", "EVITA": "🔴"}
                st.subheader("⭐ Consenso — picks sólidos en múltiples horizontes")
                for c in sorted(strong, key=lambda x: -x["n_horizontes"]):
                    n    = c["n_horizontes"]
                    bar  = "🟩" * n + "⬜" * (4 - n)
                    gem  = gemini_idx.get(c["ticker"], {})
                    accion    = gem.get("accion", "")
                    confianza = gem.get("confianza", "")
                    hz_opt    = gem.get("horizonte_optimo", "")
                    icon      = accion_colors.get(accion, "")
                    conf_icon = {"ALTA": "🔵", "MEDIA": "🟡", "BAJA": "🔸"}.get(confianza, "")
                    resumen   = gem.get("resumen", "")
                    line = f"**{c['ticker']}** &nbsp;{bar}&nbsp; {n}/4 horizontes"
                    if accion:
                        line += f" &nbsp;·&nbsp; {icon} **{accion}**"
                    if confianza:
                        line += f" &nbsp;·&nbsp; {conf_icon} {confianza}"
                    if hz_opt:
                        line += f" &nbsp;·&nbsp; ⏱ {hz_opt}"
                    if resumen:
                        line += f"  \n&nbsp;&nbsp;&nbsp;&nbsp;_{resumen}_"
                    st.markdown(line)

            st.divider()

            # ── Tabs por horizonte + Noticias ─────────────────────────────────
            if not by_horizon:
                st.info("Señal del motor antiguo. Regenera para ver multi-horizonte.")
                by_horizon = {"4s": {
                    "label": "4 semanas", "top5": sig.get("top5", []),
                    "evitar": sig.get("evitar", []),
                    "proximo_rebalanceo": sig.get("proximo_rebalanceo", "—"),
                    "universo_completo": sig.get("universo_completo", []),
                }}

            # Orden: 4s primero (estrategia principal mensual)
            horizon_keys   = [h for h in ["4s", "3s", "2s", "1s"] if h in by_horizon]
            horizon_labels = {
                "4s": "📅 4 semanas",
                "3s": "📅 3 semanas",
                "2s": "📅 2 semanas",
                "1s": "📅 1 semana",
            }
            tab_names = [horizon_labels.get(k, k) for k in horizon_keys] + ["📰 Noticias"]
            h_tabs = st.tabs(tab_names)

            medals        = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
            sent_icons    = {"positivo": "📈", "neutral": "➡️", "negativo": "📉"}

            for h_tab, hkey in zip(h_tabs[:-1], horizon_keys):
                hdata = by_horizon[hkey]

                with h_tab:
                    picks    = hdata.get("top5", [])
                    evitar   = hdata.get("evitar", [])
                    rebal    = hdata.get("proximo_rebalanceo", "—")
                    universo = hdata.get("universo_completo", [])

                    st.caption(f"⏰ Próximo rebalanceo: **{rebal}**")

                    for i, p in enumerate(picks):
                        precio     = p.get("precio_actual")
                        precio_str = f"{moneda_sym}{precio:,.2f}" if precio else "—"
                        accion_str = str(p.get("acciones_aprox", "")) or "fraccionado"
                        gem        = p.get("gemini", {})
                        gem_accion = gem.get("accion", "")
                        gem_icon   = accion_colors.get(gem_accion, "⚪")

                        tick_consensus = next((c for c in consensus if c["ticker"] == p["ticker"]), None)
                        consensus_badge = f" ⭐×{tick_consensus['n_horizontes']}" if tick_consensus and tick_consensus["n_horizontes"] >= 3 else ""

                        with st.expander(
                            f"{medals[i]}  **{p['ticker']}**{consensus_badge}  —  {p['score_pct']}  "
                            f"|  {precio_str}  |  ≈ {accion_str}"
                            + (f"  |  {gem_icon} **{gem_accion}**" if gem_accion else ""),
                            expanded=(i < 2),
                        ):
                            if gem.get("resumen"):
                                sent_ico    = sent_icons.get(gem.get("sentimiento_news", ""), "")
                                confianza   = gem.get("confianza", "")
                                hz_optimo   = gem.get("horizonte_optimo", "")
                                contradict  = gem.get("contradiccion")
                                conf_icon   = {"ALTA": "🔵", "MEDIA": "🟡", "BAJA": "🔸"}.get(confianza, "")
                                hz_label    = {"1s": "1 sem", "2s": "2 sem", "3s": "3 sem", "4s": "4 sem"}.get(hz_optimo, hz_optimo)

                                st.markdown(f"### {gem_icon} {gem.get('resumen', '')}")

                                # Confianza + horizonte óptimo
                                meta_cols = st.columns(3)
                                meta_cols[0].metric("Confianza", f"{conf_icon} {confianza}" if confianza else "—")
                                meta_cols[1].metric("Horizonte óptimo", hz_label or "—")
                                meta_cols[2].metric("Noticias", f"{sent_ico} {gem.get('sentimiento_news','—')}")

                                g1, g2 = st.columns(2)
                                with g1:
                                    if gem.get("catalizador"):
                                        st.success(f"**Catalizador:** {gem['catalizador']}")
                                with g2:
                                    if gem.get("riesgo"):
                                        st.warning(f"**Riesgo:** {gem['riesgo']}")

                                if contradict and contradict not in ("null", "None", ""):
                                    st.error(f"⚠️ **Señal contradictoria:** {contradict}")
                            else:
                                st.caption("_Análisis Gemini no disponible para este ticker (cuota agotada o sin datos)_")

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
                                        link   = n.get("link", "")
                                        title  = n.get("title", "")
                                        pub    = n.get("publisher", "")
                                        ago    = n.get("ago", "")
                                        fuente = n.get("fuente", "")
                                        line   = f"- [{title}]({link})" if link else f"- {title}"
                                        st.markdown(f"{line} — *{pub}* {ago} `{fuente}`")

                    if evitar:
                        st.markdown(f"⛔ **Evitar este ciclo:** {' · '.join(evitar)}")

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

                    if picks:
                        tickers_comprar = " + ".join(p["ticker"] for p in picks)
                        st.info(
                            f"**🗓️ Plan:** Compra **{tickers_comprar}** — "
                            f"${monto_por:,.0f} {cfg['moneda']} c/u  |  Rebalanceo: {rebal}"
                        )

            # ── Tab Noticias ──────────────────────────────────────────────────
            with h_tabs[-1]:
                try:
                    from src.api.gemini_analyst import NEWS_SOURCES, fetch_news_for_ticker
                    sources   = NEWS_SOURCES.get(uname, {})
                    fuentes   = sources.get("fuentes", [])
                    integradas = set(sources.get("integrado", []))

                    if fuentes:
                        st.subheader("🔌 Fuentes")
                        for f in fuentes:
                            estado = "✅" if f["nombre"] in integradas else "⬜"
                            st.markdown(
                                f"{estado} **{f['nombre']}** — {f['tipo']} · 💰 {f['costo']} · {f['cobertura']}"
                            )
                        st.divider()

                    st.subheader("📡 Noticias en tiempo real")
                    tickers_n = list(cfg["tickers"].items())[:10]
                    if st.button(f"Cargar noticias", key=f"news_btn_{slug}"):
                        with st.spinner("Obteniendo noticias…"):
                            all_news = {}
                            for name, sym in tickers_n:
                                news = fetch_news_for_ticker(name, sym, slug, max_items=3)
                                if news:
                                    all_news[name] = news
                        if not all_news:
                            st.info("No se encontraron noticias recientes.")
                        else:
                            for name, news_list in all_news.items():
                                with st.expander(f"**{name}** — {len(news_list)} artículos"):
                                    for n in news_list:
                                        link  = n.get("link", "")
                                        title = n.get("title", "")
                                        pub   = n.get("publisher", "")
                                        ago   = n.get("ago", "")
                                        line  = f"- [{title}]({link})" if link else f"- {title}"
                                        st.markdown(f"{line} — *{pub}* {ago}")

                    st.divider()
                    st.subheader("🤖 Análisis Gemini on-demand")
                    api_key_ok = bool(os.environ.get("GEMINI_API_KEY"))
                    ticker_sel = st.selectbox("Instrumento", list(cfg["tickers"].keys()), key=f"gem_sel_{slug}")
                    if st.button("Analizar con Gemini", key=f"gem_btn_{slug}", disabled=not api_key_ok):
                        sym = cfg["tickers"][ticker_sel]
                        with st.spinner(f"Gemini analizando {ticker_sel}…"):
                            from src.api.gemini_analyst import analyze_ticker
                            news_g = fetch_news_for_ticker(ticker_sel, sym, slug, max_items=5)
                            result = analyze_ticker(ticker_sel, sym, 1, 0.5, [], uname, news_g)
                        if result:
                            ac = result.get("accion", "")
                            col = {"COMPRA FUERTE": "success", "COMPRA": "success",
                                   "ESPERA": "warning", "EVITA": "error"}.get(ac, "info")
                            getattr(st, col)(f"**{ac}** — {result.get('resumen', '')}")
                            c1, c2 = st.columns(2)
                            c1.success(f"**Catalizador:** {result.get('catalizador','—')}")
                            c2.warning(f"**Riesgo:** {result.get('riesgo','—')}")
                        else:
                            st.error("No se pudo obtener análisis (cuota agotada o error).")
                    if not api_key_ok:
                        st.caption("Agrega GEMINI_API_KEY al .env para activar el análisis.")
                except Exception as _e:
                    st.warning(f"Error cargando módulo de noticias: {_e}")

            st.caption(
                f"Modelo: LGBMRegressor · features rank-normalizadas"
                + (" · validación 2016-2024: +7.7% anual (7/9 años)" if slug == "bmv" else "")
            )

# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA 2 — MONITOR
# ══════════════════════════════════════════════════════════════════════════════

if page.startswith("👀"):
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
# PÁGINA — RESEARCH & EVAL (literatura → código, backtest neto, LSTM, agent KB)
# ══════════════════════════════════════════════════════════════════════════════

elif page.startswith("📊"):
    st.title("📊 Research & Eval — Literatura → Código")
    st.caption(
        "KB-001/003/081 backtest con costos BMV · news dedup/decay · LSTM en SuperModel · "
        "Gemini + agent knowledge · export: data/eval/dashboard_eval.json"
    )

    eval_path = DATA / "eval" / "dashboard_eval.json"

    col_run, col_info = st.columns([1, 2])
    with col_run:
        skip_lstm = st.toggle("Omitir LSTM compare (rápido)", value=True)
        if st.button("▶️ Correr evaluaciones", type="primary", use_container_width=True):
            cmd = ["scripts/run_all_evaluations.py"]
            if skip_lstm:
                cmd.append("--skip-lstm")
            with st.spinner("Backtest top-K + grid search + calibración… (~1-2 min)"):
                rc, out = run_script(cmd)
            if rc == 0:
                st.success("Evaluaciones actualizadas")
                st.cache_data.clear()
            else:
                st.error("Error en evaluaciones")
            with st.expander("Log"):
                st.code(out[-3000:])
            st.rerun()
        if st.button("🧪 Correr experimentos P0", use_container_width=True):
            with st.spinner("News A/B + Stacking + Grid umbrales… (~30s)"):
                rc, out = run_script(["scripts/run_experiments.py"])
            if rc == 0:
                st.success("Experimentos guardados")
                st.cache_data.clear()
            else:
                st.error("Error en experimentos")
            with st.expander("Log"):
                st.code(out[-3000:])
            st.rerun()

    dash = {}
    if eval_path.exists():
        dash = json.loads(eval_path.read_text())
    else:
        st.warning("Sin datos aún. Pulsa **Correr evaluaciones**.")
        st.stop()

    summary = dash.get("summary", {})
    portfolio = dash.get("default_backtest", {})
    dual = portfolio.get("portfolio_dual", {})
    bench = portfolio.get("benchmark_naftrac", {})
    costs = portfolio.get("costs", {})
    grid = dash.get("grid_search", [])
    lstm = dash.get("lstm_vs_lgbm") or {}
    agent = dash.get("agent_knowledge", {})
    kbs = dash.get("implemented_kbs", [])

    verdict = summary.get("verdict", "?")
    v_icon = "🔴" if verdict == "NO_BET_LIVE" else "🟢"
    st.info(f"{v_icon} **{verdict}** — {summary.get('message', '')}")

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Sharpe bruto", f"{summary.get('sharpe_gross', 0):.2f}")
    c2.metric("Sharpe neto", f"{summary.get('sharpe_net', 0):.2f}",
              delta=f"vs NAFTRAC {summary.get('benchmark_sharpe', 0):.2f}")
    c3.metric("Retorno neto", f"{summary.get('total_return_net_pct', 0):+.1f}%")
    c4.metric("Retorno NAFTRAC", f"{summary.get('benchmark_return_pct', 0):+.1f}%")
    c5.metric("Costo RT", f"{summary.get('round_trip_cost_pct', 0):.2f}%")
    c6.metric("AUC OOS", f"{summary.get('auc', 0):.3f}" if summary.get("auc") else "—")

    st.caption(f"Generado: {dash.get('generated_at', '?')[:19]} · "
               f"Test: {summary.get('test_range', ['?','?'])[0]} → {summary.get('test_range', ['?','?'])[1]} · "
               f"{summary.get('n_periods', '?')} períodos rebalance")

    experiments = dash.get("experiments") or {}

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "Backtest top-K", "Grid search", "LSTM vs LGBM", "Experimentos P0", "Agent KB", "Tickets KB"
    ])

    with tab1:
        st.subheader("Top-K long-only (Ghosh 2022) — neto de costos BMV")
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Estrategia (neto)**")
            for label, key in [
                ("Sharpe", "sharpe_net"), ("Max DD", "max_drawdown"),
                ("Win rate", "win_rate_net"), ("Calmar", "calmar_ratio"),
                ("Retorno total", "total_return_net"),
            ]:
                val = dual.get(key, 0)
                if "rate" in key:
                    st.metric(label, f"{val*100:.1f}%")
                elif key == "total_return_net":
                    st.metric(label, f"{val*100:+.1f}%")
                elif key == "max_drawdown":
                    st.metric(label, f"{val*100:.1f}%")
                else:
                    st.metric(label, f"{val:.2f}")
        with col_b:
            st.markdown("**Benchmark NAFTRAC B&H**")
            st.metric("Sharpe", f"{bench.get('sharpe_ratio', 0):.2f}")
            st.metric("Retorno", f"{bench.get('total_return', 0)*100:+.1f}%")
            st.metric("Max DD", f"{bench.get('max_drawdown', 0)*100:.1f}%")
            st.caption(
                f"Comisión {costs.get('commission_pct', 0)*100:.2f}%/lado · "
                f"Slippage {costs.get('slippage_pct', 0)*100:.3f}%/lado"
            )

        curves = dash.get("equity_curves", {})
        if curves.get("net") and curves.get("naftrac"):
            df_eq = pd.DataFrame({
                "Período": range(len(curves["net"])),
                "Estrategia neto (k)": [v / 1000 for v in curves["net"]],
                "NAFTRAC (k)": [v / 1000 for v in curves["naftrac"]],
            })
            fig = px.line(df_eq, x="Período", y=["Estrategia neto (k)", "NAFTRAC (k)"],
                          labels={"value": "Capital (k MXN)", "variable": ""})
            fig.update_layout(height=320, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.subheader("Grid search — mejores parámetros top-K")
        if grid:
            df_g = pd.DataFrame(grid)
            st.dataframe(
                df_g[[
                    "top_k", "score_mode", "weight_mode",
                    "sharpe_net", "sharpe_gross", "total_return_net",
                    "max_drawdown", "win_rate_net", "auc", "vs_naftrac_sharpe",
                ]],
                use_container_width=True, hide_index=True,
            )
            best = dash.get("best_variant")
            if best:
                st.success(
                    f"Mejor variante: K={best['top_k']}, score={best['score_mode']}, "
                    f"weight={best['weight_mode']} → Sharpe neto {best['sharpe_net']}"
                )
        else:
            st.caption("Corre evaluaciones sin omitir grid.")

    with tab3:
        st.subheader("LSTM-seq vs xs_lgbm (purged CV)")
        lstm_sum = (lstm or {}).get("summary", [])
        if lstm_sum:
            df_l = pd.DataFrame(lstm_sum)
            st.dataframe(df_l, use_container_width=True, hide_index=True)
            st.caption(f"Generado: {(lstm or {}).get('generated_at', '?')[:19]}")
            if any(
                f.get("lstm_error") == "tensorflow_not_available"
                for t in (lstm or {}).get("tickers", {}).values()
                for f in t.get("folds", [])[:1]
            ):
                st.warning("Último run sin TensorFlow. Re-correr compare_lstm_lgbm.py.")
        else:
            st.info("Sin resultados LSTM. Desactiva 'Omitir LSTM' o corre: scripts/compare_lstm_lgbm.py")

    with tab4:
        st.subheader("Experimentos P0 — News / Stacking / Umbrales")
        if not experiments:
            st.info("Pulsa **🧪 Correr experimentos P0** en la barra lateral.")
        else:
            ex_sum = experiments.get("summary", {})
            e1, e2, e3 = st.columns(3)
            e1.metric("News ΔAUC≥0.01", "✅" if ex_sum.get("news_helps") else "❌")
            e2.metric("Stacking > AUC-wt", "✅" if ex_sum.get("stacking_beats_auc_weight") else "❌")
            e3.metric("Sharpe neto > 0 (≥20p)", "✅" if ex_sum.get("positive_sharpe_found") else "❌")
            if ex_sum.get("low_n_warning"):
                st.warning("El mejor Sharpe bruto usa muy pocos períodos (<20) — no es confiable.")

            exp1 = experiments.get("exp1_news_ab", {})
            st.markdown("**1. News A/B**")
            st.caption(
                f"Baseline AUC {exp1.get('baseline_auc')} → +News {exp1.get('with_news_auc')} "
                f"(Δ {exp1.get('delta_auc'):+.4f}) · cache={exp1.get('news_cache_available')}"
            )

            exp2 = experiments.get("exp2_stacking_ab", {})
            st.markdown("**2. Stacking vs AUC-weight**")
            st.caption(
                f"Sharpe neto stacking {exp2.get('sharpe_net_stacking')} vs "
                f"auc-weight {exp2.get('sharpe_net_auc_weight')} → "
                f"ganador **{exp2.get('winner_sharpe')}**"
            )

            exp3 = experiments.get("exp3_threshold_grid", {})
            st.markdown("**3. Grid K × min P(up)**")
            if exp3.get("variants"):
                df_e3 = pd.DataFrame(exp3["variants"])
                st.dataframe(df_e3, use_container_width=True, hide_index=True)
            st.caption(exp3.get("recommendation", ""))
            st.caption(f"Generado: {experiments.get('generated_at', '?')[:19]}")

    with tab5:
        st.subheader("Agent Knowledge Layer")
        cal = agent.get("calibration") or {}
        live = cal.get("live_stats") or cal.get("model_performance") or {}
        st.markdown(f"**Reglas literatura cargadas:** {agent.get('literature_rules_count', '?')}")
        if live:
            st.json(live)
        perf_path = ROOT / "articles" / "knowledge" / "agent" / "performance_log.yaml"
        if perf_path.exists():
            st.caption(f"Performance log: `{perf_path.relative_to(ROOT)}`")
        verdicts_path = DATA / "gemini_verdicts.jsonl"
        if verdicts_path.exists():
            n_v = len([l for l in verdicts_path.read_text().splitlines() if l.strip()])
            st.metric("Veredictos Gemini registrados", n_v)

    with tab6:
        st.subheader("Tickets implementados (P1–P2)")
        st.markdown(" ".join(f"`{k}`" for k in kbs))
        st.markdown("""
| Área | Módulos |
|------|---------|
| Costos + backtest | `backtester.py`, `scripts/backtest_topk.py` |
| News pipeline | `news.py` dedup TF-IDF + decay, `NEWS_FEATURE_COLS` |
| LSTM | `lstm_seq.py`, integrado en `super_model.py` |
| Stacking | `SuperModel(use_stacking=True)` |
| Agent KB | `knowledge_loader.py` → `gemini_validator.py` |
        """)
        with st.expander("JSON completo"):
            st.json(dash)

    st.stop()


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


