"""
Scorecard local de los agentes de observación.

Mide ranking, WoE, clima, noticias y stop con parquet y JSON ya en disco.
No reentrena modelos y no descarga nada.

    python scripts/validate_agents.py
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent.woe_obs import bin_of, scorecard_probability  # noqa: E402
from src.data.universes import UNIVERSES  # noqa: E402

MARKET = ROOT / "data" / "market"
WOE_PATH = ROOT / "data" / "woe_results.json"
NEWS_PATH = ROOT / "data" / "news" / "latest.json"
OUT_JSON = ROOT / "data" / "eval" / "agent_scorecard.json"
OUT_MD = ROOT / "data" / "eval" / "agent_scorecard.md"

IV_FLOOR = 0.02
BMV = next(cfg["tickers"] for cfg in UNIVERSES.values() if cfg["slug"] == "bmv")


def _r(x, nd: int = 4):
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return round(v, nd)


def read_ohlcv(symbol: str) -> pd.DataFrame | None:
    path = MARKET / f"{symbol}.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    keep = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns]
    if "Close" not in keep:
        return None
    out = df[keep].copy()
    out.index = pd.to_datetime(out.index)
    if getattr(out.index, "tz", None) is not None:
        out.index = out.index.tz_localize(None)
    out.index = out.index.normalize()
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out.dropna(subset=["Close"])


def load_bmv() -> tuple[dict[str, pd.DataFrame], list[str]]:
    series: dict[str, pd.DataFrame] = {}
    missing: list[str] = []
    for name, symbol in BMV.items():
        df = read_ohlcv(symbol)
        if df is None:
            missing.append(f"{name} ({symbol}) no está en data/market")
            continue
        if df.empty:
            missing.append(f"{name} ({symbol}) parquet vacío")
            continue
        series[name] = df
    return series, missing


def close_panel(series: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return pd.DataFrame({name: df["Close"] for name, df in series.items()}).sort_index()


def woe_of(values: np.ndarray, bins: list[dict]) -> np.ndarray:
    ordered = sorted(bins, key=lambda b: float(b["lo"]))
    los = np.array([float(b["lo"]) for b in ordered], dtype=float)
    woes = np.array([float(b["woe"]) for b in ordered], dtype=float)
    idx = np.searchsorted(los, values, side="right") - 1
    idx = np.clip(idx, 0, len(ordered) - 1)
    out = woes[idx].astype(float)
    return np.where(np.isnan(values), np.nan, out)


def check_woe_matches_agent(bins_map: dict, features: list[str], base: float) -> None:
    """La suma vectorizada tiene que coincidir con bin_of + scorecard del agente."""
    rng = np.random.default_rng(0)
    for feat in features:
        bins = bins_map[feat]
        los = [float(b["lo"]) for b in bins]
        his = [float(b["hi"]) for b in bins]
        grid = np.concatenate([
            rng.normal(loc=np.mean(los), scale=np.std(los) + 1e-3, size=40),
            np.array(los + his, dtype=float),
        ])
        vec = woe_of(grid, bins)
        for value, got in zip(grid, vec):
            expect = bin_of(float(value), bins)
            if expect is None or abs(float(expect["woe"]) - float(got)) > 1e-9:
                raise RuntimeError(f"bin WoE no coincide en {feat}={value}")
    sample = [0.1, -0.2, 0.0, 0.35]
    p_agent = scorecard_probability(sample, base)
    logit = math.log(base / (1 - base)) + sum(sample)
    logit = max(-20.0, min(20.0, logit))
    p_vec = 1.0 / (1.0 + math.exp(-logit))
    if abs(p_agent - p_vec) > 1e-12:
        raise RuntimeError("la probabilidad del scorecard no coincide con el agente")


def eval_ranking(panel: pd.DataFrame) -> dict:
    """Cada viernes, top-5 por retorno de 20 días contra el promedio del universo."""
    hist = panel.notna().cumsum()
    ret20 = panel / panel.shift(20) - 1.0
    fwd20 = panel.shift(-20) / panel - 1.0
    eligible = hist.ge(60) & ret20.notna() & fwd20.notna()
    fridays = panel.index[panel.index.dayofweek == 4]

    top_means = []
    uni_means = []
    n_names = []
    used_days = []
    skipped = 0
    for day in fridays:
        mask = eligible.loc[day]
        if int(mask.sum()) < 5:
            skipped += 1
            continue
        picks = ret20.loc[day][mask].nlargest(5).index
        fwd = fwd20.loc[day][mask]
        top_means.append(float(fwd.loc[picks].mean()))
        uni_means.append(float(fwd.mean()))
        n_names.append(int(mask.sum()))
        used_days.append(day)

    n = len(top_means)
    if n == 0:
        return {
            "ok": False,
            "error": "ningún viernes con 5 emisoras y 20 días por delante",
            "viernes_saltados": skipped,
        }
    top = np.array(top_means)
    uni = np.array(uni_means)
    hit = float(np.mean(top > uni))
    media_top = float(top.mean())
    media_uni = float(uni.mean())
    spread = media_top - media_uni
    if hit >= 0.55 and spread > 0.003:
        veredicto = (
            f"Aporta: el top-5 rinde {media_top * 100:.2f}% a 20 días contra "
            f"{media_uni * 100:.2f}% del universo (hit rate {hit:.0%})."
        )
    elif hit > 0.50 and spread > 0:
        veredicto = (
            f"Aporta poco: el top-5 rinde {media_top * 100:.2f}% a 20 días contra "
            f"{media_uni * 100:.2f}% del universo (hit rate {hit:.0%})."
        )
    else:
        veredicto = (
            f"No aporta: el top-5 rinde {media_top * 100:.2f}% a 20 días contra "
            f"{media_uni * 100:.2f}% del universo (hit rate {hit:.0%})."
        )
    return {
        "ok": True,
        "definicion": (
            "Cada viernes, emisoras BMV con al menos 60 cierres. "
            "Se ordenan por el retorno de los 20 días previos y se compara "
            "el retorno de los siguientes 20 días hábiles del top-5 "
            "contra el promedio igual-ponderado de las emisoras elegibles ese viernes."
        ),
        "n": n,
        "viernes_saltados": skipped,
        "emisoras_elegibles_media": _r(float(np.mean(n_names)), 2),
        "media_top5": _r(media_top),
        "media_universo": _r(media_uni),
        "media_top5_pct": _r(media_top * 100, 3),
        "media_universo_pct": _r(media_uni * 100, 3),
        "exceso_top5_pct": _r(spread * 100, 3),
        "hit_rate": _r(hit),
        "fecha_inicio": str(pd.Timestamp(used_days[0]).date()),
        "fecha_fin": str(pd.Timestamp(used_days[-1]).date()),
        "veredicto": veredicto,
    }


def _feature_frame(df: pd.DataFrame, macro: dict[str, pd.Series], needed: set[str]) -> pd.DataFrame:
    c = df["Close"]
    out = pd.DataFrame(index=df.index)
    if "williams_r" in needed:
        if "High" not in df.columns or "Low" not in df.columns:
            out["williams_r"] = np.nan
        else:
            high14 = df["High"].rolling(14).max()
            low14 = df["Low"].rolling(14).min()
            out["williams_r"] = (high14 - c) / (high14 - low14 + 1e-8) * -100
    if "mkt_ret10" in needed or "mkt_trend" in needed:
        mkt = macro.get("NAFTRAC")
        if mkt is None:
            out["mkt_ret10"] = np.nan
            out["mkt_trend"] = np.nan
        else:
            aligned = mkt.reindex(df.index, method="ffill")
            out["mkt_ret10"] = aligned.pct_change(10) * 100
            sma50 = aligned.rolling(50).mean()
            out["mkt_trend"] = (aligned - sma50) / (sma50 + 1e-8) * 100
    if "sp500_ret5" in needed:
        sp = macro.get("SP500")
        if sp is None:
            out["sp500_ret5"] = np.nan
        else:
            aligned = sp.reindex(df.index, method="ffill")
            out["sp500_ret5"] = aligned.pct_change(5) * 100
    return out


def eval_woe(series: dict[str, pd.DataFrame]) -> dict:
    if not WOE_PATH.exists():
        return {"ok": False, "error": "falta data/woe_results.json"}
    table = json.loads(WOE_PATH.read_text())
    meta = table.get("meta") or {}
    base = float(meta.get("event_rate") or 0.5)
    base = min(max(base, 1e-4), 1 - 1e-4)
    iv_rows = table.get("iv_summary") or []
    bins_map = table.get("bins_by_feature") or {}
    selected = []
    for row in iv_rows:
        if float(row["iv"]) >= IV_FLOOR and row["feature"] in bins_map:
            selected.append(row["feature"])
    if not selected:
        return {"ok": False, "error": "ninguna variable con IV>=0.02"}

    supported = {"williams_r", "mkt_ret10", "mkt_trend", "sp500_ret5"}
    unsupported = [f for f in selected if f not in supported]
    usable = [f for f in selected if f in supported]
    if not usable:
        return {
            "ok": False,
            "error": "las variables con IV>=0.02 no se pueden calcular con los parquet locales",
            "variables": selected,
        }
    check_woe_matches_agent(bins_map, usable, base)

    macro_close: dict[str, pd.Series] = {}
    notes = []
    naf = read_ohlcv("NAFTRACISHRS.MX")
    if naf is None:
        naf = read_ohlcv("NAFTRAC.MX")
    if naf is None:
        notes.append("sin NAFTRAC para mkt_ret10 y mkt_trend")
    else:
        macro_close["NAFTRAC"] = naf["Close"]
    sp = read_ohlcv("GSPC")
    if sp is None:
        notes.append("sin GSPC.parquet para sp500_ret5")
    else:
        macro_close["SP500"] = sp["Close"]

    needed = set(usable)
    frames = []
    for name, df in series.items():
        feat = _feature_frame(df, macro_close, needed)
        block = feat[usable].copy()
        block["y"] = (df["Close"].shift(-5) > df["Close"]).astype(float)
        block.loc[df["Close"].shift(-5).isna(), "y"] = np.nan
        block = block.dropna()
        if block.empty:
            continue
        woe_sum = np.zeros(len(block), dtype=float)
        for feat_name in usable:
            woe_sum += woe_of(block[feat_name].to_numpy(dtype=float), bins_map[feat_name])
        logit = math.log(base / (1.0 - base)) + woe_sum
        logit = np.clip(logit, -20.0, 20.0)
        block = block[["y"]].copy()
        block["p"] = 1.0 / (1.0 + np.exp(-logit))
        block["ticker"] = name
        block["date"] = block.index
        frames.append(block)

    if not frames:
        return {"ok": False, "error": "sin filas completas para el scorecard", "notas": notes}

    panel = pd.concat(frames, ignore_index=True)
    dates = np.sort(panel["date"].unique())
    hold_dates = dates[int(len(dates) * 0.8):]
    hold = panel[panel["date"].isin(hold_dates)]
    y = hold["y"].to_numpy(dtype=float)
    p = hold["p"].to_numpy(dtype=float)
    if len(y) == 0:
        return {"ok": False, "error": "el último 20% de fechas quedó vacío"}

    brier = float(np.mean((p - y) ** 2))
    tasa = float(np.mean(y))
    brier_ref = float(tasa * (1.0 - tasa))
    up = y == 1
    down = ~up
    p_up = float(np.mean(p[up])) if up.any() else None
    p_down = float(np.mean(p[down])) if down.any() else None
    gap = None if p_up is None or p_down is None else p_up - p_down
    skill = None if brier_ref <= 0 else 1.0 - brier / brier_ref
    p_up_txt = "n/a" if p_up is None else f"{p_up:.3f}"
    p_down_txt = "n/a" if p_down is None else f"{p_down:.3f}"
    if gap is not None and gap > 0.02 and skill is not None and skill > 0.01:
        veredicto = (
            f"Aporta: p es {p_up_txt} cuando el cierre sube y {p_down_txt} cuando no, "
            f"y el Brier {brier:.3f} mejora el {brier_ref:.3f} de la tasa base."
        )
    elif gap is not None and gap > 0 and skill is not None and skill > 0:
        veredicto = (
            f"Aporta poco: p es {p_up_txt} cuando el cierre sube y {p_down_txt} cuando no. "
            f"El Brier {brier:.3f} casi no mejora el {brier_ref:.3f} de la tasa base."
        )
    else:
        veredicto = (
            f"No aporta: p es {p_up_txt} cuando el cierre sube y {p_down_txt} cuando no, "
            f"y el Brier {brier:.3f} no mejora el {brier_ref:.3f} de la tasa base."
        )
    if unsupported:
        notes.append(
            "variables con IV>=0.02 no calculadas y excluidas de p: " + ", ".join(unsupported)
        )
    notes.append(
        "Los bins salen de data/woe_results.json "
        f"(fecha {meta.get('date')}, n_obs {meta.get('n_obs')}). "
        "Ese ajuste puede solaparse con el último 20% de fechas, así que esto no es una prueba fuera de muestra pura."
    )
    return {
        "ok": True,
        "definicion": (
            "En el último 20% de fechas con features y cierre a 5 días, "
            "p = sigmoide(logit(event_rate) + suma de WoE) usando solo variables con IV>=0.02. "
            "El evento es que el cierre suba en 5 días hábiles."
        ),
        "variables": [
            {"feature": f, "iv": next(float(r["iv"]) for r in iv_rows if r["feature"] == f)}
            for f in usable
        ],
        "event_rate_scorecard": base,
        "n": int(len(hold)),
        "n_fechas": int(len(hold_dates)),
        "n_tickers": int(hold["ticker"].nunique()),
        "fecha_inicio": str(pd.Timestamp(hold_dates[0]).date()),
        "fecha_fin": str(pd.Timestamp(hold_dates[-1]).date()),
        "brier": _r(brier),
        "brier_tasa_base": _r(brier_ref),
        "skill_brier": _r(skill),
        "tasa_base": _r(tasa),
        "p_promedio": _r(float(np.mean(p))),
        "p_promedio_cuando_sube": _r(p_up),
        "p_promedio_cuando_no_sube": _r(p_down),
        "brecha_p": _r(gap),
        "notas": notes,
        "veredicto": veredicto,
    }


def eval_clima(series: dict[str, pd.DataFrame]) -> dict:
    source = None
    bench = None
    for symbol in ("NAFTRACISHRS.MX", "NAFTRAC.MX"):
        bench = read_ohlcv(symbol)
        if bench is not None:
            source = symbol
            break
    if bench is None:
        return {"ok": False, "error": "no está NAFTRACISHRS.MX.parquet ni NAFTRAC.MX.parquet"}

    ret10 = bench["Close"].pct_change(10) * 100
    state = pd.Series(index=bench.index, dtype="object")
    state.loc[ret10 > 1] = "alcista"
    state.loc[ret10 < -1] = "bajista"
    state.loc[ret10.notna() & (ret10 <= 1) & (ret10 >= -1)] = "lateral"

    fwd = pd.DataFrame({
        name: df["Close"].shift(-5) / df["Close"] - 1.0
        for name, df in series.items()
    })
    long = fwd.stack().rename("ret5").reset_index()
    long.columns = ["date", "ticker", "ret5"]
    long["estado"] = long["date"].map(state)
    long = long.dropna(subset=["ret5", "estado"])

    por_estado = {}
    for estado in ("alcista", "bajista", "lateral"):
        part = long[long["estado"] == estado]
        por_estado[estado] = {
            "n": int(len(part)),
            "n_fechas": int(part["date"].nunique()) if len(part) else 0,
            "retorno_medio_5d": _r(part["ret5"].mean() if len(part) else None),
            "retorno_medio_5d_pct": _r(part["ret5"].mean() * 100 if len(part) else None, 3),
        }
    a = por_estado["alcista"]["retorno_medio_5d"]
    b = por_estado["bajista"]["retorno_medio_5d"]
    lat = por_estado["lateral"]["retorno_medio_5d"]
    if None in (a, b, lat):
        veredicto = "No se puede juzgar: falta algún estado con observaciones."
    elif a > lat > b and (a - b) >= 0.002:
        veredicto = (
            f"Aporta: a 5 días la BMV rinde {a * 100:.2f}% en alcista, "
            f"{lat * 100:.2f}% en lateral y {b * 100:.2f}% en bajista."
        )
    elif a > b and (a - b) >= 0.001:
        veredicto = (
            f"Aporta poco: a 5 días la BMV rinde {a * 100:.2f}% en alcista, "
            f"{b * 100:.2f}% en bajista y {lat * 100:.2f}% en lateral. "
            "El lateral no queda entre los otros dos."
        )
    else:
        veredicto = (
            f"No aporta: a 5 días la BMV rinde {a * 100:.2f}% en alcista y "
            f"{b * 100:.2f}% en bajista."
        )
    return {
        "ok": True,
        "definicion": (
            f"Con {source}, alcista si el retorno de 10 días es mayor a 1%, "
            "bajista si es menor a -1%, y lateral en el resto. "
            "El retorno es el del cierre de cada emisora BMV a 5 días hábiles."
        ),
        "benchmark": source,
        "por_estado": por_estado,
        "veredicto": veredicto,
    }


def eval_noticias() -> dict:
    if not NEWS_PATH.exists():
        return {"ok": False, "error": "falta data/news/latest.json"}
    rows = json.loads(NEWS_PATH.read_text())
    if not isinstance(rows, list) or not rows:
        return {"ok": False, "error": "data/news/latest.json no trae una lista de tickers"}
    has_score = all("news_sent_score" in r for r in rows)
    with_articles = [r for r in rows if (r.get("n_articles") or 0) > 0]
    scores = [float(r["news_sent_score"]) for r in with_articles if r.get("news_sent_score") is not None]
    cobertura = {
        "n_tickers": len(rows),
        "n_tickers_con_articulos": len(with_articles),
        "fraccion_con_articulos": _r(len(with_articles) / len(rows) if rows else None),
        "sentimiento_medio": _r(float(np.mean(scores)) if scores else None),
        "n_scores_distintos": int(len(set(scores))),
    }
    return {
        "ok": True,
        "definicion": (
            "Foto única en data/news/latest.json. Hay news_sent_score por ticker, "
            "pero no un panel histórico diario de sentimiento, así que no se calcula correlación con precios."
        ),
        "hay_news_sent_score": has_score,
        "panel_historico_diario": False,
        "cobertura": cobertura,
        "veredicto": (
            "No aporta evidencia sobre retornos: no hay panel diario de sentimiento, solo cobertura de una foto."
        ),
    }


def eval_salida(series: dict[str, pd.DataFrame], panel: pd.DataFrame) -> dict:
    if panel.empty:
        return {"ok": False, "error": "sin precios BMV"}
    full = panel.index
    end = full.max()
    start = end - pd.Timedelta(days=365)
    positions = np.flatnonzero((full >= start) & (full <= end))
    positions = positions[positions + 5 < len(full)]
    sample_dates = list(full[positions[::20]])
    touched = []
    kept = []
    n_dates = set()
    skipped_atr = 0
    for df in series.values():
        if "High" not in df.columns or "Low" not in df.columns:
            skipped_atr += 1
            continue
        c = df["Close"]
        h = df["High"]
        low = df["Low"]
        tr = pd.concat([(h - low), (h - c.shift(1)).abs(), (low - c.shift(1)).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()
        idx = df.index
        for day in sample_dates:
            if day not in idx:
                continue
            i = idx.get_loc(day)
            if isinstance(i, slice) or not isinstance(i, (int, np.integer)):
                continue
            i = int(i)
            if i + 5 >= len(idx):
                continue
            atr_i = atr.iloc[i]
            close_i = c.iloc[i]
            if pd.isna(atr_i) or pd.isna(close_i) or atr_i <= 0 or close_i <= 0:
                continue
            window = low.iloc[i + 1:i + 6]
            future_close = c.iloc[i + 5]
            if window.isna().any() or pd.isna(future_close):
                continue
            stop = float(close_i) - 1.5 * float(atr_i)
            hit = bool(float(window.min()) <= stop)
            ret = float(future_close) / float(close_i) - 1.0
            touched.append(hit)
            if not hit:
                kept.append(ret)
            n_dates.add(idx[i])
    n = len(touched)
    if n == 0:
        return {"ok": False, "error": "sin fechas de muestra con ATR(14) y 5 días por delante"}
    freq = float(np.mean(touched))
    media = float(np.mean(kept)) if kept else None
    media_txt = "n/a" if media is None else f"{media * 100:.2f}%"
    if freq < 0.02:
        veredicto = (
            f"No aporta como protección: el stop a 1.5 ATR se toca solo en {freq:.0%} "
            "de las ventanas de 5 días."
        )
    elif freq > 0.45:
        veredicto = (
            f"Aporta poco: el stop se toca en {freq:.0%} de las ventanas, "
            "así que corta la mayoría antes de 5 días."
        )
    elif media is not None and media > 0:
        veredicto = (
            f"Aporta como freno: el mínimo de 5 días toca el stop en {freq:.0%} de los casos. "
            f"El {media_txt} es el retorno de las que no lo tocan, no la ganancia de la regla."
        )
    else:
        veredicto = (
            f"El stop se toca en {freq:.0%} de los casos, pero las ventanas que no lo tocan "
            f"dejan un retorno medio de {media_txt}."
        )
    return {
        "ok": True,
        "definicion": (
            "Último año, el calendario común de la BMV cada 20 días hábiles. "
            "Stop = cierre - 1.5 * ATR(14). Se mira si el mínimo de los 5 días siguientes "
            "de cada emisora toca ese stop. ATR es la media móvil de 14 días del true range."
        ),
        "fecha_inicio": str(start.date()),
        "fecha_fin": str(end.date()),
        "n": n,
        "n_fechas": len(n_dates),
        "n_sin_high_low": skipped_atr,
        "frecuencia_toca_stop": _r(freq),
        "n_toca_stop": int(sum(touched)),
        "n_no_toca_stop": len(kept),
        "retorno_medio_si_no_toca": _r(media),
        "retorno_medio_si_no_toca_pct": _r(None if media is None else media * 100, 3),
        "veredicto": veredicto,
    }


def _md(report: dict) -> str:
    lines = [
        "# Scorecard de agentes de observación",
        "",
        f"Generado: {report['generated_at']}",
        "",
        "Medido con precios locales. Sin reentrenar y sin red.",
        "",
    ]
    if report.get("faltantes"):
        lines.append("Sin precio usable: " + ", ".join(report["faltantes"]) + ".")
        lines.append("")
    lines.append("| Agente | Métrica | Número | ¿Aporta? |")
    lines.append("| --- | --- | --- | --- |")
    for row in report["tabla"]:
        lines.append(f"| {row['agente']} | {row['metrica']} | {row['numero']} | {row['frase']} |")
    lines.append("")
    return "\n".join(lines)


def build_table(agents: dict) -> list[dict]:
    rows = []

    ranking = agents["ranking"]
    if ranking.get("ok"):
        rows.append({
            "agente": "Ranking",
            "metrica": "n viernes",
            "numero": ranking["n"],
            "frase": ranking["veredicto"],
        })
        rows.append({
            "agente": "Ranking",
            "metrica": "media top5, 20d (%)",
            "numero": ranking["media_top5_pct"],
            "frase": ranking["veredicto"],
        })
        rows.append({
            "agente": "Ranking",
            "metrica": "media universo, 20d (%)",
            "numero": ranking["media_universo_pct"],
            "frase": ranking["veredicto"],
        })
        rows.append({
            "agente": "Ranking",
            "metrica": "hit rate top5 > universo",
            "numero": ranking["hit_rate"],
            "frase": ranking["veredicto"],
        })
    else:
        rows.append({
            "agente": "Ranking",
            "metrica": "error",
            "numero": None,
            "frase": ranking.get("error", "no se pudo medir"),
        })

    woe = agents["woe"]
    if woe.get("ok"):
        rows.append({
            "agente": "WoE",
            "metrica": "Brier",
            "numero": woe["brier"],
            "frase": woe["veredicto"],
        })
        rows.append({
            "agente": "WoE",
            "metrica": "tasa base",
            "numero": woe["tasa_base"],
            "frase": woe["veredicto"],
        })
        rows.append({
            "agente": "WoE",
            "metrica": "p promedio cuando sube",
            "numero": woe["p_promedio_cuando_sube"],
            "frase": woe["veredicto"],
        })
        rows.append({
            "agente": "WoE",
            "metrica": "p promedio cuando no sube",
            "numero": woe["p_promedio_cuando_no_sube"],
            "frase": woe["veredicto"],
        })
    else:
        rows.append({
            "agente": "WoE",
            "metrica": "error",
            "numero": None,
            "frase": woe.get("error", "no se pudo medir"),
        })

    clima = agents["clima"]
    if clima.get("ok"):
        for estado in ("alcista", "bajista", "lateral"):
            rows.append({
                "agente": "Clima",
                "metrica": f"retorno medio 5d, {estado} (%)",
                "numero": clima["por_estado"][estado]["retorno_medio_5d_pct"],
                "frase": clima["veredicto"],
            })
    else:
        rows.append({
            "agente": "Clima",
            "metrica": "error",
            "numero": None,
            "frase": clima.get("error", "no se pudo medir"),
        })

    noticias = agents["noticias"]
    if noticias.get("ok"):
        cob = noticias["cobertura"]
        rows.append({
            "agente": "Noticias",
            "metrica": "tickers con n_articles>0",
            "numero": cob["n_tickers_con_articulos"],
            "frase": noticias["veredicto"],
        })
        rows.append({
            "agente": "Noticias",
            "metrica": "sentimiento medio",
            "numero": cob["sentimiento_medio"],
            "frase": noticias["veredicto"],
        })
    else:
        rows.append({
            "agente": "Noticias",
            "metrica": "error",
            "numero": None,
            "frase": noticias.get("error", "no se pudo medir"),
        })

    salida = agents["salida"]
    if salida.get("ok"):
        rows.append({
            "agente": "Salida",
            "metrica": "frecuencia toca stop 5d",
            "numero": salida["frecuencia_toca_stop"],
            "frase": salida["veredicto"],
        })
        rows.append({
            "agente": "Salida",
            "metrica": "retorno medio si no toca (%)",
            "numero": salida["retorno_medio_si_no_toca_pct"],
            "frase": salida["veredicto"],
        })
    else:
        rows.append({
            "agente": "Salida",
            "metrica": "error",
            "numero": None,
            "frase": salida.get("error", "no se pudo medir"),
        })
    return rows


def main() -> None:
    series, missing = load_bmv()
    panel = close_panel(series)
    agents = {
        "ranking": eval_ranking(panel),
        "woe": eval_woe(series),
        "clima": eval_clima(series),
        "noticias": eval_noticias(),
        "salida": eval_salida(series, panel),
    }
    table = build_table(agents)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "universo": "bmv",
        "n_tickers_con_precio": len(series),
        "n_tickers_universo": len(BMV),
        "faltantes": missing,
        "agentes": agents,
        "tabla": table,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    OUT_MD.write_text(_md(report))
    print(f"json: {OUT_JSON}")
    print(f"md:   {OUT_MD}")
    for row in table:
        print(f"{row['agente']}\t{row['metrica']}\t{row['numero']}")


if __name__ == "__main__":
    main()
