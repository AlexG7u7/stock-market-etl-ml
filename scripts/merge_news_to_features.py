"""
Pipeline de entrenamiento: features técnicos + news NLP → CSV.

Demuestra la integración KB-004:
  1. Carga OHLCV del store local
  2. Calcula features técnicos + macro
  3. Carga news features (cache data/news/latest.json o fetch en vivo)
  4. Merge con add_news_features()
  5. Exporta CSV listo para entrenamiento

El EnsembleModel usa news features pasando:
  feature_cols = get_all_feature_cols(include_news=True)

  news_sent_score  → tono agregado (dedup TF-IDF + decay temporal)
  news_count_7d    → volumen informativo log(1 + peso_efectivo)
  news_sent_delta  → cambio vs ventana anterior
  news_sent_vol    → dispersión de sentiment (incertidumbre)

Uso:
  python scripts/merge_news_to_features.py
  python scripts/merge_news_to_features.py --fetch-news
  python scripts/merge_news_to_features.py --output data/training/features_with_news.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.data.store import BMV_TICKERS, get as store_get, MACRO_TICKERS
from src.ml.features import (
    add_macro_features,
    add_news_features,
    compute_features,
    get_all_feature_cols,
    NEWS_FEATURE_COLS,
)
from src.ml.news import batch_news_features, load_cached_news_features


def build_training_frame(
    tickers: dict[str, str] | None = None,
    fetch_news: bool = False,
) -> pd.DataFrame:
    tickers = tickers or BMV_TICKERS

    macro: dict[str, pd.DataFrame] = {}
    for name in MACRO_TICKERS:
        df = store_get(name)
        if df is not None:
            macro[name] = df

    rows: list[pd.DataFrame] = []
    for ticker, _symbol in tickers.items():
        raw = store_get(ticker)
        if raw is None or len(raw) < 60:
            continue
        feat = compute_features(raw)
        feat = add_macro_features(feat, macro)
        feat["ticker"] = ticker
        rows.append(feat.tail(1))

    if not rows:
        raise RuntimeError("Sin datos OHLCV en store — ejecuta store_update() primero")

    features_df = pd.concat(rows, ignore_index=True)

    if fetch_news:
        news_df = batch_news_features(tickers, days_back=7, verbose=True, save_cache=True)
        news_df = news_df.reset_index()
    else:
        cached = load_cached_news_features()
        if cached is None:
            print("  Sin cache de news — ejecutando fetch...")
            news_df = batch_news_features(tickers, days_back=7, verbose=True, save_cache=True)
            news_df = news_df.reset_index()
        else:
            news_df = cached.reset_index()

    merged = add_news_features(features_df, news_df, ticker_col="ticker")
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge features técnicos + news para entrenamiento")
    parser.add_argument("--fetch-news", action="store_true", help="Forzar fetch de noticias")
    parser.add_argument(
        "--output",
        default=str(ROOT / "data" / "training" / "features_with_news.csv"),
        help="Ruta del CSV de salida",
    )
    args = parser.parse_args()

    print("Construyendo frame de entrenamiento (features + news)...")
    df = build_training_frame(fetch_news=args.fetch_news)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)

    feature_cols = get_all_feature_cols(include_news=True)
    news_present = [c for c in NEWS_FEATURE_COLS if c in df.columns]

    print(f"\n  Filas: {len(df)} tickers")
    print(f"  News columns: {news_present}")
    print(f"  Total feature cols (include_news=True): {len(feature_cols)}")
    print(f"  Guardado: {out_path}")


if __name__ == "__main__":
    main()
