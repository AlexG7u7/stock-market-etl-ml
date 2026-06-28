"""
PASO 1 — Configuración inicial de autenticación GBM+ con Playwright.

Este script se corre UNA SOLA VEZ para autorizar el perfil de navegador
que usaremos para renovaciones automáticas futuras.

Abre un navegador visible donde:
  1. Inicias sesión con tu correo y contraseña de GBM+
  2. Completas cualquier verificación de nuevo dispositivo (email o SMS)
  3. El perfil del navegador queda guardado en ~/.gbm-playwright-profile/
  4. Futuras renovaciones son automáticas y headless

USO:
    python scripts/gbm_auth_setup.py
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

from src.broker.gbm_client import parse_gbm_session_json, save_tokens_to_env

PROFILE_DIR = Path.home() / ".gbm-playwright-profile"
GBM_URL     = "https://invertir.gbm.com"


def main() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: Instala playwright: pip install playwright && playwright install chromium")
        sys.exit(1)

    email    = os.environ.get("GBM_EMAIL", "")
    password = os.environ.get("GBM_PASSWORD", "")

    print("\n" + "=" * 60)
    print("  Configuración inicial — GBM+ Playwright")
    print("=" * 60)
    print()
    print(f"Perfil guardado en: {PROFILE_DIR}")
    print()
    print("Se abrirá un navegador Chrome. Pasos:")
    print("  1. Inicia sesión con tu correo y contraseña")
    print("  2. Si GBM pide verificar dispositivo, complétalo")
    print("     (llegará un email o SMS de verificación)")
    print("  3. Cuando veas el dashboard de GBM, regresa aquí")
    print("     y presiona Enter para guardar los tokens")
    print()
    input("Presiona Enter para abrir el navegador...")

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            slow_mo=100,
            viewport={"width": 1280, "height": 800},
            args=["--no-sandbox"],
        )

        page = context.new_page()
        page.goto(GBM_URL)
        print(f"\nNavegador abierto en: {GBM_URL}")
        print()

        # Intentar autocompletar email/password si están en el .env
        if email and password:
            try:
                page.wait_for_selector('input[type="email"], input[name="email"], input[name="username"]',
                                       timeout=8000)
                email_input = page.locator('input[type="email"], input[name="email"], input[name="username"]').first
                email_input.fill(email)
                print(f"Email prellenado: {email}")

                pwd_input = page.locator('input[type="password"]').first
                pwd_input.fill(password)
                print("Password prellenado")
                print()
                print("Si hay verificación de dispositivo, complétala en el navegador.")
                print("Cuando veas el dashboard de GBM+, regresa aquí.")
            except Exception:
                print("No se pudo prellenar las credenciales. Inicia sesión manualmente.")

        print()
        input(">>> Cuando estés logueado en el dashboard, presiona Enter aquí: ")

        # Extraer tokens de localStorage
        session_raw = page.evaluate("localStorage.getItem('gbm-session')")

        if not session_raw:
            print()
            print("ERROR: No se encontró 'gbm-session' en localStorage.")
            print("Asegúrate de estar en el dashboard de GBM+ antes de continuar.")
            context.close()
            sys.exit(1)

        try:
            access_token, id_token = parse_gbm_session_json(session_raw)
        except Exception as e:
            print(f"ERROR al parsear sesión: {e}")
            context.close()
            sys.exit(1)

        context.close()

    save_tokens_to_env(access_token, id_token)

    print()
    print("✅ Perfil guardado en:", PROFILE_DIR)
    print("✅ Tokens guardados en .env")
    print()
    print("Ahora puedes ejecutar el auto-refresh automático:")
    print("  python scripts/refresh_gbm_session.py")
    print()
    print("Para que los tokens se renueven solos en background:")
    print("  python scripts/gbm_token_daemon.py &")
    print()


if __name__ == "__main__":
    main()
