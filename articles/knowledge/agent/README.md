# Knowledge Base — Agente de Apuestas BMV

Capa operativa para el agente que **decide, dimensiona y ejecuta** apuestas.
Complementa `papers/` (literatura) con reglas ejecutables ligadas al código.

## Qué tiene hoy el agente (código)

```
SuperModel / generate_all_signals  →  ranking + P(up)
         ↓
Risk Engine (Kelly, ATR, correlación)  →  Signal con sizing
         ↓
Gemini Validator / gemini_analyst  →  CONFIRMA | DEGRADA | VETA
         ↓
paper_trading / execute_orders  →  ejecución
```

## Archivos de esta capa

| Archivo | Propósito |
|---------|-----------|
| `decision_protocol.yaml` | Árbol de decisión: cuándo apostar, cuánto, cuándo vetar |
| `bmv_market_rules.yaml` | Microestructura BMV: costos, horarios, liquidez |
| `calibration.yaml` | Stats empíricos del modelo (win rate, edge, régimen) |
| `risk_limits.yaml` | Límites duros que el agente NUNCA viola |
| `literature_rules.yaml` | Reglas destiladas de papers → políticas concretas |
| `failure_modes.yaml` | Cuándo NO confiar en el modelo (edge decay, overfitting) |

## Uso por el agente

1. Leer `decision_protocol.yaml` antes de cada sesión
2. Consultar `calibration.yaml` para interpretar P(up) y convicción
3. Aplicar `risk_limits.yaml` como guardrails
4. Validar costos con `bmv_market_rules.yaml`
5. En duda, revisar `literature_rules.yaml` y fichas en `papers/`

## Principio rector (de la literatura)

> **Clasificación direccional + Sharpe neto de costos > accuracy de precio.**
> (Sahu 2023, Ghosh 2022, stack_mapping.yaml)

El agente apuesta en **edge probabilístico cross-seccional**, no en predecir el precio exacto.
