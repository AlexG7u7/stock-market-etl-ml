
"""Consultas de resultados para el agente de Evaluación/Riesgo."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EVAL_DIR = ROOT / "data" / "eval"

ARCHIVOS = {
    "portafolio": "portfolio_metrics.json",
    "backtest": "backtest_topk.json",
    "experimentos": "experiments.json",
    "estrategias": "strategies_comparison.json",
    "validacion": "strategy_validation.json",
}


def cargar_resultado(tipo: str) -> dict:
    """Lee un JSON de evaluación sin modificarlo."""

    if tipo not in ARCHIVOS:
        return {"error": f"Consulta desconocida: {tipo}"}

    ruta = EVAL_DIR / ARCHIVOS[tipo]

    if not ruta.is_file():
        return {"error": f"Archivo no encontrado: {ruta.name}"}

    try:
        with ruta.open("r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
    except (OSError, json.JSONDecodeError) as error:
        return {"error": f"Error al leer {ruta.name}: {error}"}

    if not isinstance(datos, dict):
        return {"error": f"Formato inválido: {ruta.name}"}

    return datos


def consultar_resultado(tipo: str) -> str:
    """Devuelve las métricas almacenadas en los JSON."""

    datos = cargar_resultado(tipo)

    if "error" in datos:
        return datos["error"]

    if tipo == "portafolio":
        metricas = datos.get("portfolio_dual", {})
        benchmark = datos.get("benchmark_naftrac", {})

        return (
            "Evaluación del portafolio:\n"
            f"Sharpe neto: {metricas.get('sharpe_net')}\n"
            f"Drawdown máximo: {metricas.get('max_drawdown')}\n"
            f"Rendimiento neto: {metricas.get('total_return_net')}\n"
            f"Sharpe NAFTRAC: {benchmark.get('sharpe_ratio')}\n"
            f"Generado: {datos.get('generated_at')}"
        )

    if tipo == "backtest":
        estrategia = datos.get("strategy", {})
        benchmark = datos.get("benchmark_naftrac", {})

        return (
            "Backtest Top-K:\n"
            f"Sharpe neto: {estrategia.get('sharpe_net')}\n"
            f"Drawdown máximo: {estrategia.get('max_drawdown')}\n"
            f"Rendimiento neto: {estrategia.get('total_return_net')}\n"
            f"Rendimiento NAFTRAC: {benchmark.get('total_return')}\n"
            f"Periodos: {estrategia.get('n_periods')}"
        )

    if tipo == "experimentos":
        resumen = datos.get("summary", {})

        return (
            "Experimentos:\n"
            f"Noticias ayudan: {resumen.get('news_helps')}\n"
            f"Stacking supera AUC ponderado: "
            f"{resumen.get('stacking_beats_auc_weight')}\n"
            f"Sharpe positivo encontrado: "
            f"{resumen.get('positive_sharpe_found')}\n"
            f"Advertencia de pocas observaciones: "
            f"{resumen.get('low_n_warning')}"
        )

    if tipo == "estrategias":
        return (
            "Comparación de estrategias:\n"
            f"Total: {datos.get('total_estrategias')}\n"
            f"Aprobadas: {datos.get('aprobadas')}\n"
            f"Generado: {datos.get('generated_at')}"
        )

    if tipo == "validacion":
        ia = datos.get("validacion_ia", {})

        return (
            "Validación de estrategia:\n"
            f"Estrategia: {datos.get('estrategia')}\n"
            f"Aprobada: {datos.get('aprobada')}\n"
            f"Resumen: {datos.get('resumen')}\n"
            f"Estado IA: {ia.get('estado')}"
        )

    return "Consulta no disponible."
