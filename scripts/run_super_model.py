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

from src.ml.signal_pipeline import run_super_pipeline


OUT = ROOT / "data" / "super_signals.json"


def main():
    parser = argparse.ArgumentParser(description="Super Modelo cross-universo")
    parser.add_argument("--top-gemini", type=int, default=10,
                        help="Cuántos tickers del top valida Gemini (default 10)")
    parser.add_argument("--no-gemini", action="store_true",
                        help="Saltar la validación Gemini (solo cuantitativo)")
    parser.add_argument("--no-stacking", action="store_true",
                        help="Desactivar meta-LR stacking (default: ON, KB-060)")
    args = parser.parse_args()

    t0 = datetime.now()

    result = run_super_pipeline(
        top_gemini_global=args.top_gemini,
        top_gemini_bmv=args.top_gemini,
        use_gemini=not args.no_gemini,
        use_stacking=not args.no_stacking,
        verbose=True,
    )
    result["generated_at"] = datetime.now().isoformat()
    result["elapsed_sec"] = round((datetime.now() - t0).total_seconds(), 1)

    gs = result.get("gemini_summary", {})
    if gs.get("modo") != "skip":
        print("\n" + "═" * 62)
        print("  CAPA 4 — Gemini validador")
        print("═" * 62)
        print(f"  CONFIRMA {gs.get('confirma',0)} · DEGRADA {gs.get('degrada',0)} · VETA {gs.get('veta',0)}")
        print("\n  Veredictos del top global:")
        for item in result["master_ranking"][:args.top_gemini]:
            g = item.get("gemini", {})
            if not g:
                continue
            print(f"    #{item['rank_global']:<2} {item['ticker']:<10} "
                  f"{g.get('veredicto','?'):<9} → {g.get('accion_final','?')}")
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    print(f"\n  Apuestas paper BMV (K=2, conv≥0.56): {len(result.get('actionable_bets_bmv', []))}")
    print(f"  Apuestas paper global: {len(result.get('actionable_bets', []))}")
    print(f"  Guardado en: {OUT}")
    print(f"  Tiempo total: {result['elapsed_sec']}s\n")


if __name__ == "__main__":
    main()
