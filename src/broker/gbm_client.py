"""
GBM+ broker client — autenticación via tokens de sesión del navegador.

NOTA: GBM+ requiere verificación de dispositivo para autenticación con usuario/contraseña
desde scripts externos. La solución práctica es usar el accessToken de tu sesión web activa.

Variables de entorno (.env):
    GBM_ACCESS_TOKEN  — accessToken del campo gbm-session en localStorage de invertir.gbm.com
    GBM_ID_TOKEN      — idToken del mismo campo
    GBM_LIVE          — "true" para órdenes reales (default: dry-run simulado)

Cómo renovar los tokens (expiran cada hora):
    1. Abre invertir.gbm.com en Chrome y asegúrate de estar logueado
    2. F12 → Application → Local Storage → https://invertir.gbm.com
    3. Copia el valor de la clave "gbm-session"  (es un JSON)
    4. Ejecuta: python scripts/refresh_gbm_session.py
       (el script extrae y guarda los tokens en .env automáticamente)
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent.parent

# ─── Endpoints de la API de GBM+ ─────────────────────────────────────────────
_BASE_URL = "https://api.gbm.com"
_AUTH_URL = "https://auth.gbm.com"

_HEADERS_BASE = {
    "Content-Type":  "application/json",
    "Accept":        "application/json",
    "Origin":        "https://invertir.gbm.com",
    "Referer":       "https://invertir.gbm.com/",
    "User-Agent":    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class Position:
    ticker: str
    shares: float
    avg_cost: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    account_id: str = ""


@dataclass
class Portfolio:
    cash_mxn: float
    buying_power: float
    market_value: float
    total_value: float
    positions: list[Position] = field(default_factory=list)
    fetched_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class OrderRequest:
    ticker: str            # ej. "WALMEX.MX" (ticker Yahoo Finance)
    side: str              # "BUY" | "SELL"
    shares: int
    limit_price: float
    account_id: str = ""
    notes: str = ""


@dataclass
class OrderResult:
    success: bool
    order_id: str
    ticker: str
    side: str
    shares: int
    limit_price: float
    dry_run: bool
    message: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


# ─── Mapa ticker Yahoo → nombre corto GBM ─────────────────────────────────────
TICKER_TO_GBM: dict[str, str] = {
    "ALFAA.MX":      "ALFA A",
    "ALSEA.MX":      "ALSEA *",
    "AMXL.MX":       "AMX L",
    "ASURB.MX":      "ASUR B",
    "BIMBOA.MX":     "BIMBO A",
    "BOLSAA.MX":     "BOLSA A",
    "CEMEXCPO.MX":   "CEMEX CPO",
    "FEMSAUBD.MX":   "FEMSA UBD",
    "GAPB.MX":       "GAP B",
    "GCARSOA1.MX":   "GCARSO A1",
    "GMEXICOB.MX":   "GMEXICO B",
    "GRUMAB.MX":     "GRUMA B",
    "KIMBERA.MX":    "KIMBER A",
    "LABB.MX":       "LAB B",
    "OMAB.MX":       "OMA B",
    "PINFRA.MX":     "PINFRA *",
    "TLEVISACPO.MX": "TLEVISA CPO",
    "VESTA.MX":      "VESTA *",
    "WALMEX.MX":     "WALMEX *",
}


# ─── Utilidades JWT ────────────────────────────────────────────────────────────

def _decode_jwt_payload(token: str) -> dict:
    """Decodifica el payload de un JWT sin verificar firma."""
    import base64
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    payload += "=" * (4 - len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload).decode())


def _token_expires_at(token: str) -> Optional[int]:
    payload = _decode_jwt_payload(token)
    return payload.get("exp")


def _token_is_expired(token: str, buffer_secs: int = 120) -> bool:
    exp = _token_expires_at(token)
    if not exp:
        return True
    return time.time() + buffer_secs > exp


def _token_minutes_left(token: str) -> float:
    exp = _token_expires_at(token)
    if not exp:
        return 0
    return max(0, (exp - time.time()) / 60)


# ─── Lector de sesión desde .env / archivo ────────────────────────────────────

def load_session_from_env() -> tuple[str, str]:
    """Retorna (access_token, id_token) desde variables de entorno."""
    return (
        os.environ.get("GBM_ACCESS_TOKEN", ""),
        os.environ.get("GBM_ID_TOKEN", ""),
    )


def save_tokens_to_env(access_token: str, id_token: str) -> None:
    """Actualiza GBM_ACCESS_TOKEN y GBM_ID_TOKEN en el .env del proyecto."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        env_path.write_text("")

    lines = env_path.read_text().splitlines()
    updated = {"GBM_ACCESS_TOKEN": False, "GBM_ID_TOKEN": False}

    new_lines = []
    for line in lines:
        if line.startswith("GBM_ACCESS_TOKEN="):
            new_lines.append(f"GBM_ACCESS_TOKEN={access_token}")
            updated["GBM_ACCESS_TOKEN"] = True
        elif line.startswith("GBM_ID_TOKEN="):
            new_lines.append(f"GBM_ID_TOKEN={id_token}")
            updated["GBM_ID_TOKEN"] = True
        else:
            new_lines.append(line)

    if not updated["GBM_ACCESS_TOKEN"]:
        new_lines.append(f"GBM_ACCESS_TOKEN={access_token}")
    if not updated["GBM_ID_TOKEN"]:
        new_lines.append(f"GBM_ID_TOKEN={id_token}")

    env_path.write_text("\n".join(new_lines) + "\n")
    logger.info("Tokens guardados en .env")


def parse_gbm_session_json(session_json: str) -> tuple[str, str]:
    """
    Parsea el JSON del campo 'gbm-session' de localStorage.
    Retorna (access_token, id_token).
    """
    data = json.loads(session_json)
    access = data.get("accessToken", "")
    id_tok = data.get("idToken", "")
    if not access or not id_tok:
        raise ValueError("El JSON no contiene accessToken o idToken")
    return access, id_tok


# ─── Cliente principal ─────────────────────────────────────────────────────────

class GBMClient:
    """
    Cliente para la API de GBM+ usando tokens de sesión del navegador.

    Flujo de autenticación:
        1. Usuario copia gbm-session de localStorage → ejecuta refresh_gbm_session.py
        2. Los tokens se guardan en .env (GBM_ACCESS_TOKEN, GBM_ID_TOKEN)
        3. GBMClient los lee y hace peticiones autenticadas
        4. Los tokens expiran en ~1 hora — hay que renovarlos desde el navegador

    En modo dry_run (default) no se envía ninguna orden real.
    """

    def __init__(self) -> None:
        self.dry_run = os.environ.get("GBM_LIVE", "").lower() != "true"
        self._access_token, self._id_token = load_session_from_env()
        self._session = requests.Session()

        mode = "DRY-RUN" if self.dry_run else "⚠️ LIVE"
        logger.info(f"GBMClient iniciado en modo {mode}")

    # ── Estado de los tokens ──────────────────────────────────────────────────

    @property
    def has_tokens(self) -> bool:
        return bool(self._access_token and self._id_token)

    @property
    def tokens_expired(self) -> bool:
        if not self._access_token:
            return True
        return _token_is_expired(self._access_token)

    @property
    def minutes_until_expiry(self) -> float:
        if not self._access_token:
            return 0
        return _token_minutes_left(self._access_token)

    @property
    def credentials_set(self) -> bool:
        return self.has_tokens and not self.tokens_expired

    @property
    def is_live(self) -> bool:
        return not self.dry_run

    # ── Autenticación con headers ─────────────────────────────────────────────

    def _auth_headers(self) -> dict:
        if not self.has_tokens:
            raise GBMConfigError(
                "No hay tokens de sesión. Ejecuta: python scripts/refresh_gbm_session.py"
            )
        if self.tokens_expired:
            raise GBMTokenExpiredError(
                f"Los tokens de GBM expiraron. "
                "Renuévalos: abre invertir.gbm.com, copia gbm-session de LocalStorage, "
                "y ejecuta: python scripts/refresh_gbm_session.py"
            )
        return {
            **_HEADERS_BASE,
            "Authorization": f"Bearer {self._access_token}",
            "X-Id-Token":    self._id_token,
        }

    def _get(self, path: str, **kwargs) -> dict:
        url = f"{_BASE_URL}{path}"
        resp = self._session.get(url, headers=self._auth_headers(), timeout=15, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{_BASE_URL}{path}"
        resp = self._session.post(
            url, headers=self._auth_headers(), json=payload, timeout=15
        )
        resp.raise_for_status()
        return resp.json()

    # ── Portafolio y posiciones ───────────────────────────────────────────────

    def get_portfolio(self) -> Portfolio:
        """Retorna saldo, buying power y posiciones abiertas."""
        try:
            # Obtener cuentas/estrategias
            accounts_data = self._get("/v2/accounts")
            accounts      = accounts_data if isinstance(accounts_data, list) else \
                            accounts_data.get("accounts", accounts_data.get("strategies", []))

            positions: list[Position] = []
            total_cash    = 0.0
            total_market  = 0.0
            buying_power  = 0.0

            for acc in accounts:
                acc_id   = acc.get("id", acc.get("strategyId", ""))
                acc_type = acc.get("type", acc.get("strategyType", ""))
                balance  = float(acc.get("balance", acc.get("amount", 0)))

                if "CASH" in str(acc_type).upper() or "SMART" in str(acc_type).upper():
                    total_cash   += balance
                    buying_power += balance
                    continue

                # Posiciones de renta variable
                try:
                    pos_data = self._get(f"/v2/accounts/{acc_id}/positions")
                    pos_list = pos_data if isinstance(pos_data, list) else \
                               pos_data.get("positions", [])

                    for p in pos_list:
                        shares   = float(p.get("quantity", p.get("shares", 0)))
                        avg_cost = float(p.get("averageCost", p.get("avgCost", 0)))
                        price    = float(p.get("lastPrice", p.get("currentPrice", avg_cost)))
                        mv       = shares * price
                        pnl      = mv - shares * avg_cost
                        pnl_pct  = (pnl / (shares * avg_cost) * 100) if avg_cost else 0.0
                        total_market += mv

                        ticker = (p.get("issuerName", "")
                                  or p.get("ticker", "")
                                  or p.get("symbol", ""))

                        positions.append(Position(
                            ticker=ticker, shares=shares, avg_cost=avg_cost,
                            current_price=price, market_value=mv,
                            unrealized_pnl=pnl, unrealized_pnl_pct=pnl_pct,
                            account_id=acc_id,
                        ))
                except Exception:
                    pass  # cuenta sin posiciones

            return Portfolio(
                cash_mxn=total_cash, buying_power=buying_power,
                market_value=total_market, total_value=total_cash + total_market,
                positions=positions,
            )

        except (GBMConfigError, GBMTokenExpiredError):
            raise
        except Exception as exc:
            raise GBMAPIError(f"Error al obtener portafolio: {exc}") from exc

    def get_open_orders(self) -> list[dict]:
        """Retorna órdenes pendientes."""
        try:
            data = self._get("/v2/orders", params={"status": "OPEN"})
            return data if isinstance(data, list) else data.get("orders", [])
        except (GBMConfigError, GBMTokenExpiredError):
            raise
        except Exception as exc:
            raise GBMAPIError(f"Error al obtener órdenes: {exc}") from exc

    # ── Órdenes ───────────────────────────────────────────────────────────────

    def place_order(self, req: OrderRequest) -> OrderResult:
        """Envía orden límite. En dry_run solo simula."""
        gbm_name = TICKER_TO_GBM.get(req.ticker, req.ticker.replace(".MX", ""))

        if self.dry_run:
            msg = (f"[DRY-RUN] {req.side} {req.shares}x {gbm_name} "
                   f"@ ${req.limit_price:.2f} MXN — ${req.shares*req.limit_price:,.0f} total")
            logger.info(msg)
            return OrderResult(
                success=True,
                order_id="DRY-" + datetime.now().strftime("%Y%m%d%H%M%S"),
                ticker=req.ticker, side=req.side, shares=req.shares,
                limit_price=req.limit_price, dry_run=True, message=msg,
            )

        if req.shares <= 0 or req.limit_price <= 0:
            raise ValueError(f"Parámetros de orden inválidos: shares={req.shares}, price={req.limit_price}")

        try:
            account_id = req.account_id or self._get_default_account_id()
            payload = {
                "accountId":      account_id,
                "issuerName":     gbm_name,
                "quantity":       req.shares,
                "price":          req.limit_price,
                "side":           "Buy" if req.side == "BUY" else "Sell",
                "orderType":      "Limit",
                "instrumentType": "IPC",
            }
            resp     = self._post("/v2/orders", payload)
            order_id = str(resp.get("orderId", resp.get("id", "")))
            msg      = (f"Orden enviada: {req.side} {req.shares}x {gbm_name} "
                        f"@ ${req.limit_price:.2f} — ID: {order_id}")
            logger.info(msg)
            return OrderResult(
                success=True, order_id=order_id, ticker=req.ticker,
                side=req.side, shares=req.shares, limit_price=req.limit_price,
                dry_run=False, message=msg,
            )
        except Exception as exc:
            msg = f"Error al enviar orden {req.side} {gbm_name}: {exc}"
            logger.error(msg)
            return OrderResult(
                success=False, order_id="", ticker=req.ticker,
                side=req.side, shares=req.shares, limit_price=req.limit_price,
                dry_run=False, message=msg,
            )

    def cancel_order(self, order_id: str) -> bool:
        if self.dry_run:
            logger.info(f"[DRY-RUN] Cancelar orden {order_id}")
            return True
        try:
            self._session.delete(
                f"{_BASE_URL}/v2/orders/{order_id}",
                headers=self._auth_headers(), timeout=15,
            )
            logger.info(f"Orden {order_id} cancelada")
            return True
        except Exception as exc:
            logger.error(f"Error al cancelar {order_id}: {exc}")
            return False

    def _get_default_account_id(self) -> str:
        try:
            data = self._get("/v2/accounts")
            accounts = data if isinstance(data, list) else data.get("accounts", [])
            for acc in accounts:
                t = acc.get("type", acc.get("strategyType", ""))
                if "CASH" not in str(t).upper():
                    return str(acc.get("id", acc.get("strategyId", "")))
        except Exception:
            pass
        return ""


# ─── Excepciones ──────────────────────────────────────────────────────────────

class GBMConfigError(Exception):
    """Tokens faltantes o no configurados."""

class GBMTokenExpiredError(Exception):
    """Los tokens de sesión expiraron — hay que renovarlos desde el navegador."""

class GBMConnectionError(Exception):
    """No se pudo conectar a GBM+."""

class GBMAPIError(Exception):
    """Error en una llamada a la API de GBM+."""
