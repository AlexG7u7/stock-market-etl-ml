# Guía de reproducibilidad: evaluación y riesgo

## 1. Objetivo

Reproducir los resultados de evaluación de múltiples estrategias,
su integración Medallion y las consultas de la capa semántica MCP.

Todos los comandos deben ejecutarse desde la raíz del repositorio.

## 2. Entorno utilizado

- Sistema operativo: Linux mediante WSL.
- Python: 3.14.4.
- Entorno virtual: .venv-linux.

Activación del entorno existente:

    source .venv-linux/bin/activate

Versiones de las dependencias principales verificadas:

| Dependencia | Versión |
|---|---|
| numpy | 2.5.4 |
| pandas | 3.1.1 |
| pyarrow | 26.0.1 |
| scikit-learn | 1.9.1 |
| lightgbm | 4.7.0 |
| yfinance | 1.8.0 |
| requests | 2.34.2 |
| python-dotenv | 1.2.4 |
| loguru | 0.8.0 |
| pytest | 9.2.0 |
| mcp | 2.3.0 |
| claude-agent-sdk | 0.2.189 |
| pydantic | 2.14.4 |
| jsonschema | 4.26.0 |
| uvicorn | 0.54.0 |
| starlette | 1.10.0 |

Comprobar la instalación:

    python --version
    python -m pip check

Las versiones anteriores corresponden al entorno utilizado durante
las pruebas y no constituyen un archivo de bloqueo completo
de todas las dependencias del proyecto.

## 3. Datos requeridos

Para reproducir las simulaciones completas se requiere disponer
de los datos históricos locales utilizados en la evaluación.

Directorios principales:

    data/market/
    data/rates/banxico/
    data/estrategias_corregidas/
    data/estrategias_homologadas/
    data/eval/

Los datos de mercado proceden de Yahoo Finance.

Las tasas de interés proceden del Sistema de Información
Económica del Banco de México.

No se deben incluir credenciales ni tokens de acceso
en los archivos versionados.

La actualización de los datos históricos puede modificar
los resultados respecto a la evaluación documentada.

## 4. Reproducción rápida

Este procedimiento utiliza los resultados de evaluación
existentes y no requiere volver a entrenar modelos.

### 4.1. Verificar archivos de entrada

    ls -lh data/estrategias_corregidas/
    ls -lh data/estrategias_homologadas/
    ls -lh data/eval/strategies_comparison_real.json

### 4.2. Generar las capas Medallion

    python -m scripts.medallion_estrategias

El procedimiento genera:

- Bronze: archivos originales y manifiesto de integridad.
- Silver: archivos validados y reporte de calidad.
- Gold: producto consolidado de evaluación.

Producto final:

    data/eval/medallion/gold/evaluacion_multiples_estrategias.json

### 4.3. Consultar la capa semántica

Resumen general:

    python -c "from src.agents_mcp.domains.evaluacion_semantica import resumen_estrategias, serializar; print(serializar(resumen_estrategias()))"

Consultar SMA:

    python -c "from src.agents_mcp.domains.evaluacion_semantica import consultar_estrategia, serializar; print(serializar(consultar_estrategia('sma_50_200')))"

Comparar por Sharpe:

    python -c "from src.agents_mcp.domains.evaluacion_semantica import comparar_estrategias, serializar; print(serializar(comparar_estrategias('sharpe_neto')))"

Consultar decisión:

    python -c "from src.agents_mcp.domains.evaluacion_semantica import consultar_decision, serializar; print(serializar(consultar_decision()))"

Estas consultas no requieren una API de inteligencia artificial.

## 5. Reproducción completa de las evaluaciones

Este procedimiento puede consumir más tiempo porque las
estrategias Top-K requieren entrenamiento de modelos.

Los comandos regeneran archivos de resultados existentes.
Se recomienda conservar una copia de los resultados anteriores
antes de ejecutar el procedimiento.

### 5.1. Preparar directorios

    mkdir -p data/estrategias_corregidas
    mkdir -p data/estrategias_homologadas

### 5.2. Estrategia Top-K 2

    python -u -m scripts.backtest_topk \
        --universe bmv \
        --top-k 2 \
        --min-p-up 0.56 \
        --score p_up \
        --weight equal \
        --horizon 5 \
        --commission 0.0025 \
        --slippage 0.0005 \
        --output data/estrategias_corregidas/topk_2.json

### 5.3. Estrategia Top-K 5

    python -u -m scripts.backtest_topk \
        --universe bmv \
        --top-k 5 \
        --min-p-up 0.56 \
        --score p_up \
        --weight equal \
        --horizon 5 \
        --commission 0.0025 \
        --slippage 0.0005 \
        --output data/estrategias_corregidas/topk_5.json

### 5.4. Estrategia Top-K 10

    python -u -m scripts.backtest_topk \
        --universe bmv \
        --top-k 10 \
        --min-p-up 0.56 \
        --score p_up \
        --weight equal \
        --horizon 5 \
        --commission 0.0025 \
        --slippage 0.0005 \
        --output data/estrategias_corregidas/topk_10.json

### 5.5. Variante exploratoria Top-K 5 Ranking

    python -u -m scripts.backtest_topk \
        --universe bmv \
        --top-k 5 \
        --min-p-up 0.0 \
        --score p_up \
        --weight equal \
        --horizon 5 \
        --commission 0.0025 \
        --slippage 0.0005 \
        --output data/estrategias_corregidas/topk_5_ranking.json

Esta variante tiene carácter exploratorio y no constituye
una validación independiente.

### 5.6. Estrategias tradicionales

    python -u -m scripts.backtest_traditional

Archivos generados:

    data/estrategias_corregidas/sma_portfolio.json
    data/estrategias_corregidas/rsi_portfolio.json

### 5.7. Homologación diaria de Top-K

    python -u -m scripts.homologate_topk

Reconstruye las curvas diarias y verifica que se conserve
el rendimiento y el capital final de las simulaciones originales.

### 5.8. Benchmark NAFTRAC

    python -u -m scripts.backtest_benchmark

Archivo generado:

    data/estrategias_homologadas/buy_hold_naftrac.json

### 5.9. Consolidación

    python -u -m scripts.consolidate_strategies

Archivos principales:

    data/estrategias_homologadas/strategies_catalog.json
    data/estrategias_homologadas/strategies_summary.json

### 5.10. Validación y comparación

    python -u -m scripts.validate_strategies \
        --catalog data/estrategias_homologadas/strategies_catalog.json \
        --max-drawdown 0.30 \
        --output data/eval/strategies_comparison_real.json

### 5.11. Generación Medallion

    python -u -m scripts.medallion_estrategias

## 6. Resultados de referencia

Periodo: 2023-05-10 a 2026-10-30.

Capital inicial: 100,000 MXN.

Sesiones de evaluación: 876.

| Estrategia | Rendimiento neto | Sharpe neto | Capital final MXN |
|---|---:|---:|---:|
| SMA 50/200 | 12.46% | 0.4213 | 112,463.84 |
| RSI 14 | 11.03% | 0.5008 | 111,029.44 |
| Top-K 2 | 0.00% | 0.0000 | 100,000.00 |
| Top-K 5 | 0.00% | 0.0000 | 100,000.00 |
| Top-K 10 | 0.00% | 0.0000 | 100,000.00 |
| Top-K 5 Ranking | -45.25% | -0.8734 | 54,745.13 |
| Benchmark NAFTRAC | 24.54% | 0.4803 | 124,535.33 |

Resultado esperado con los datos de referencia:

- Calidad del producto: VALIDO.
- Estrategias evaluadas: 6.
- Estrategias aprobadas: 0.
- Estrategias no aprobadas: 6.
- Decisión global: NO_BET_LIVE.

Las simulaciones tradicionales y el benchmark fueron
ejecutados nuevamente y reprodujeron las métricas anteriores.

La reproducción completa de los modelos ML puede depender
de las versiones de software y de los datos utilizados.

## 7. Pruebas automatizadas

    python -m pytest -v \
        tests/test_strategy_validator.py \
        tests/test_strategy_comparator.py \
        tests/test_traditional_backtest.py \
        tests/test_strategy_homologation.py \
        tests/test_medallion_evaluacion.py \
        tests/test_medallion_estrategias.py \
        tests/test_evaluacion_semantica.py \
        tests/test_mcp_estrategias.py \
        tests/test_agents_mcp_evaluacion_lab.py

Estas pruebas comprueban la aportación de evaluación y riesgo
y su integración con los componentes correspondientes.

No sustituyen las pruebas completas de todo el repositorio.

## 8. Servidor MCP

Configurar un token temporal seguro mediante variables de entorno.

    export MCP_REQUIRE_AUTH_TOKEN=1
    read -rs MCP_AUTH_TOKEN
    export MCP_AUTH_TOKEN
    python -m mcp_server.server

El endpoint local predeterminado es:

    http://localhost:8080/mcp

No exponer el servidor a Internet durante las pruebas locales.

Consultar mcp_server/README.md para conocer las herramientas,
argumentos, autenticación y ejemplos de consultas.

## 9. Consideraciones de reproducibilidad

- Mantener los mismos datos históricos.
- Mantener el universo de instrumentos utilizado.
- Conservar las versiones de las dependencias.
- Mantener los costos y parámetros de simulación.
- No ajustar parámetros utilizando los resultados de prueba.
- No confundir resultados históricos con ganancias reales.
- Las fechas de generación y hashes pueden cambiar al regenerar
  archivos, aunque las métricas financieras sean equivalentes.
- Los scripts sin interfaz de argumentos pueden ejecutar su
  procedimiento completo incluso si reciben la opción --help.

## 10. Documentación complementaria

- docs/evaluacion_riesgo.md
- mcp_server/README.md

Los resultados tienen fines educativos y no constituyen
una recomendación de inversión.

## Anexo: restauracion del historial de Banxico

Para evitar versionar 6799 archivos JSON individuales, se entrega
el historial utilizado en el archivo:

    data/rates/banxico_historico.zip

Caracteristicas del conjunto de datos:

- Fuente: Banco de Mexico, API SIE.
- Inicio: 2008-01-02.
- Fin: 2026-11-23.
- Archivos JSON: 6799.
- Archivos invalidos: 0.
- Archivos vacios: 0.
- Tamano original: 377469 bytes.
- Tamano ZIP: 1114427 bytes.

Series utilizadas:

| Variable | Serie Banxico |
|---|---|
| TIIE 28 dias | SF43783 |
| TIIE 91 dias | SF60649 |
| CETES 28 dias | SF43936 |
| CETES 364 dias | SF43945 |
| Tasa objetivo | SF61745 |

### Verificacion del archivo

Desde la raiz del repositorio, ejecutar:

    sha256sum data/rates/banxico_historico.zip

El resultado esperado es:

    aa4b85ad115993809025f59cdf4bfb5607c5ee44f93fc776a50eb7a38b1f47ab

### Restauracion de los datos

En una copia nueva del repositorio, ejecutar:

    python -m zipfile -e data/rates/banxico_historico.zip data/rates/

Verificar la cantidad de archivos recuperados:

    find data/rates/banxico/ -type f -name '*.json' | wc -l

Resultado esperado:

    6799

La extraccion debe realizarse antes de ejecutar el backtesting
Top-K desde cero.

Los algoritmos conservan su mecanismo original de lectura de
archivos JSON individuales. No se requiere modificar el modelo
para utilizar el historial restaurado.

La extraccion puede sobrescribir archivos existentes con el
mismo nombre. Se recomienda realizarla en una copia nueva
del repositorio.

El ZIP fue verificado byte por byte contra los 6799 archivos
originales. Esto garantiza la integridad de la copia, pero no
constituye una auditoria independiente de los valores publicados.

No se incluyen tokens ni credenciales de acceso a la API.
