"""
Super Modelo — pipeline completo end-to-end.

  1. SuperModel: carga datos del store local, entrena modelos base por universo,
     fusiona señales (peso por edge), modula por régimen + noticias.
  2. Ranking maestro cross-universo de los 87 tickers.
  3. Gemini valida el top-N como comité de riesgo (CONFIRMA/DEGRADA/VETA).
  4. Guarda data/super_signals.json para el dashboard.

Uso:
    python scripts/run_super_model.py                 # todo, top-10 con Gemini
    python scripts/run_super_model.py --top-gemini 5  # validar solo top-5
    python scripts/run_super_model.py --no-gemini     # solo cuantitativo (rápido)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from src.ml.super_model import SuperModel
from src.ml.gemini_validator import validate_ranking
from src.data.universes import UNIVERSES

OUT = ROOT / "data" / "super_signals.json"


def _tickers_map() -> dict[str, str]:
    """nombre_corto → símbolo yfinance (todos los universos)."""
    m = {}
    for cfg in UNIVERSES.values():
        m.update(cfg["tickers"])
    return m


def main():
    parser = argparse.ArgumentParser(description="Super Modelo cross-universo")
    parser.add_argument("--top-gemini", type=int, default=10,
                        help="Cuántos tickers del top valida Gemini (default 10)")
    parser.add_argument("--no-gemini", action="store_true",
                        help="Saltar la validación Gemini (solo cuantitativo)")
    args = parser.parse_args()

    t0 = datetime.now()

    # ── Capas 1-3: cuantitativo ──────────────────────────────────────────────
    sm = SuperModel(top_gemini=args.top_gemini, verbose=True)
    result = sm.run()

    # ── Capa 4: Gemini validador ─────────────────────────────────────────────
    if not args.no_gemini:
        print("\n" + "═" * 62)
        print("  CAPA 4 — Gemini validador (comité de riesgo)")
        print("═" * 62)
        result = validate_ranking(result, tickers_map=_tickers_map(),
                                  top_n=args.top_gemini)
        gs = result.get("gemini_summary", {})
        print(f"\n  Modo: {gs.get('modo','?')}  |  "
              f"CONFIRMA {gs.get('confirma',0)} · "
              f"DEGRADA {gs.get('degrada',0)} · VETA {gs.get('veta',0)}")

        # Mostrar veredictos del top
        print("\n  Veredictos del top:")
        for item in result["master_ranking"][:args.top_gemini]:
            g = item.get("gemini", {})
            print(f"    #{item['rank_global']:<2} {item['ticker']:<10} "
                  f"{g.get('veredicto','?'):<9} → {g.get('accion_final','?'):<13} "
                  f"({g.get('confianza_gemini','?')}%)")
            if g.get("tesis"):
                print(f"        {g['tesis'][:90]}")
    else:
        result["gemini_summary"] = {"modo": "skip"}

    # ── Guardar ──────────────────────────────────────────────────────────────
    result["generated_at"] = datetime.now().isoformat()
    result["elapsed_sec"] = round((datetime.now() - t0).total_seconds(), 1)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    print(f"\n  Guardado en: {OUT}")
    print(f"  Tiempo total: {result['elapsed_sec']}s\n")


if __name__ == "__main__":
    main()
