"""
Descarga y procesa noticias para todos los universos.

Fuentes: Yahoo Finance, Google News RSS, El Financiero, Expansión, GDELT.
Sentiment: Gemini 2.5-flash (si GEMINI_API_KEY está en .env), fallback keywords.

Salida:
  data/news/YYYY-MM-DD.json  — features por ticker para hoy
  data/news/latest.json      — alias siempre actualizado

Uso:
  python scripts/fetch_news.py                   # todos los universos
  python scripts/fetch_news.py --universe bmv    # solo BMV
  python scripts/fetch_news.py --gdelt           # incluir GDELT (más lento, backfill)
  python scripts/fetch_news.py --days 14         # ventana de 14 días
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from src.data.universes import UNIVERSES
from src.ml.news import batch_news_features, NEWS_FEATURE_COLS, NEWS_DIR

UNIVERSE_SLUGS = {
    "bmv":    "🇲🇽 Acciones BMV",
    "usa":    "🇺🇸 Acciones USA (SIC)",
    "etf":    "📦 ETFs",
    "crypto": "₿ Cripto (proxies GBM)",
    "fibra":  "🏢 FIBRAs (bienes raíces MX)",
}


def main():
    parser = argparse.ArgumentParser(description="Descargar noticias financieras")
    parser.add_argument("--universe", choices=list(UNIVERSE_SLUGS.keys()), default=None,
                        help="Procesar solo un universo")
    parser.add_argument("--days", type=int, default=7,
                        help="Ventana de noticias en días (default: 7)")
    parser.add_argument("--gdelt", action="store_true",
                        help="Incluir GDELT para historial (más lento)")
    parser.add_argument("--no-cache", action="store_true",
                        help="No guardar cache en disco")
    args = parser.parse_args()

    gemini_ok = bool(os.environ.get("GEMINI_API_KEY"))
    sentiment_mode = "Gemini 2.5-flash" if gemini_ok else "keywords (fallback)"

    print(f"\n{'═'*62}")
    print(f"  NOTICIAS FINANCIERAS  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Ventana: {args.days} días  |  Sentiment: {sentiment_mode}")
    if args.gdelt:
        print(f"  GDELT: activado (backfill histórico)")
    print(f"{'═'*62}\n")

    selected = (
        {args.universe: UNIVERSE_SLUGS[args.universe]}
        if args.universe
        else UNIVERSE_SLUGS
    )

    all_results = {}
    for slug, uname in selected.items():
        if uname not in UNIVERSES:
            print(f"  ! Universo no encontrado: {uname}")
            continue

        tickers = UNIVERSES[uname]["tickers"]
        print(f"── {uname} ({len(tickers)} tickers) {'─'*30}\n")

        df = batch_news_features(
            tickers=tickers,
            days_back=args.days,
            use_gdelt=args.gdelt,
            verbose=True,
            save_cache=False,  # guardamos el consolidado al final
        )
        all_results[slug] = df.reset_index().to_dict(orient="records")

        # Resumen por universo
        sent_mean = df["news_sent_score"].mean()
        n_total   = df["n_articles"].sum() if "n_articles" in df.columns else 0
        print(f"\n  Resumen {uname}:")
        print(f"    Artículos totales: {int(n_total)}")
        print(f"    Sentimiento promedio: {sent_mean:+.3f}")
        top_pos = df["news_sent_score"].idxmax()
        top_neg = df["news_sent_score"].idxmin()
        print(f"    Más positivo: {top_pos} ({df.loc[top_pos, 'news_sent_score']:+.2f})")
        print(f"    Más negativo: {top_neg} ({df.loc[top_neg, 'news_sent_score']:+.2f})")
        print()

    # Guardar cache consolidado
    today = datetime.now().strftime("%Y-%m-%d")
    if not args.no_cache:
        # Por universo
        for slug, records in all_results.items():
            path = NEWS_DIR / f"{slug}_{today}.json"
            path.write_text(json.dumps(records, ensure_ascii=False, indent=2))

        # Consolidado (todos los tickers juntos)
        all_records = [r for records in all_results.values() for r in records]
        latest_path = NEWS_DIR / "latest.json"
        dated_path  = NEWS_DIR / f"{today}.json"
        latest_path.write_text(json.dumps(all_records, ensure_ascii=False, indent=2))
        dated_path.write_text(json.dumps(all_records, ensure_ascii=False, indent=2))
        print(f"  Guardado en: {dated_path}")
        print(f"  Alias:       {latest_path}")

    print(f"\n  Features disponibles: {NEWS_FEATURE_COLS}")
    print(f"  Próximo paso: estas features se integran automáticamente en")
    print(f"  generate_all_signals.py al correr las señales.\n")


if __name__ == "__main__":
    main()
