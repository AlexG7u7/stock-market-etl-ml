"""
Auto-refresh de tokens GBM+ usando el perfil de Playwright guardado.

Requiere haber corrido gbm_auth_setup.py al menos una vez.

USO:
    python scripts/refresh_gbm_session.py            # refresca ahora
    python scripts/refresh_gbm_session.py --check    # solo verifica si está vivo
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from src.broker.gbm_client import (
    _token_is_expired,
    _token_minutes_left,
    parse_gbm_session_json,
    save_tokens_to_env,
)

PROFILE_DIR = Path.home() / ".gbm-playwright-profile"
GBM_URL     = "https://invertir.gbm.com"


def check_current_tokens() -> dict:
    """Verifica el estado de los tokens actuales."""
    from dotenv import dotenv_values
    env = dotenv_values(ROOT / ".env")
    access = env.get("GBM_ACCESS_TOKEN", "")
    if not access:
        return {"status": "missing", "minutes_left": 0}
    if _token_is_expired(access):
        return {"status": "expired", "minutes_left": 0}
    mins = _token_minutes_left(access)
    return {"status": "valid", "minutes_left": round(mins, 1)}


def refresh_tokens_headless() -> tuple[str, str]:
    """
    Usa el perfil guardado para abrir GBM+ en headless y extraer tokens frescos.
    Requiere que el perfil ya tenga la sesión activa (desde gbm_auth_setup.py).
    """
    from playwright.sync_api import sync_playwright

    if not PROFILE_DIR.exists():
        raise RuntimeError(
            f"Perfil no encontrado: {PROFILE_DIR}\n"
            "Ejecuta primero: python scripts/gbm_auth_setup.py"
        )

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )

        page = context.new_page()

        try:
            page.goto(GBM_URL, wait_until="networkidle", timeout=30_000)
        except Exception:
            # timeout en networkidle es esperado, el SPA puede tardar
            pass

        # Esperar a que la sesión cargue
        for _ in range(10):
            session_raw = page.evaluate("localStorage.getItem('gbm-session')")
            if session_raw:
                parsed = json.loads(session_raw)
                if parsed.get("accessToken") and parsed.get("accessToken") != "undefined":
                    break
            time.sleep(1)
        else:
            context.close()
            raise RuntimeError(
                "No se encontró gbm-session en localStorage tras 10 segundos. "
                "La sesión del perfil puede haber expirado. "
                "Ejecuta: python scripts/gbm_auth_setup.py"
            )

        access_token, id_token = parse_gbm_session_json(session_raw)
        context.close()

    return access_token, id_token


def main() -> None:
    check_only = "--check" in sys.argv

    if check_only:
        state = check_current_tokens()
        if state["status"] == "valid":
            print(f"✅ Tokens válidos — {state['minutes_left']} min restantes")
        elif state["status"] == "expired":
            print("❌ Tokens expirados — ejecuta refresh")
            sys.exit(1)
        else:
            print("❌ Sin tokens configurados")
            sys.exit(1)
        return

    print("Refrescando tokens GBM+ (headless)...")

    try:
        access_token, id_token = refresh_tokens_headless()
    except RuntimeError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR inesperado: {e}")
        sys.exit(1)

    if _token_is_expired(access_token):
        print("ERROR: Los tokens obtenidos ya están expirados.")
        print("La sesión del perfil ha expirado. Ejecuta: python scripts/gbm_auth_setup.py")
        sys.exit(1)

    save_tokens_to_env(access_token, id_token)

    mins = _token_minutes_left(access_token)
    print(f"✅ Tokens renovados — válidos por {mins:.0f} minutos")


if __name__ == "__main__":
    main()
