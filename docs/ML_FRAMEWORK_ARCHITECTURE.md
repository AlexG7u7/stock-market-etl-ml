# 🤖 Framework ML - LSTM con Algoritmo Genético

## 📋 Resumen Ejecutivo

Framework completo de Machine Learning para predicción de precios de acciones usando:
- **Modelo**: LSTM (Long Short-Term Memory)
- **Optimización**: Algoritmo Genético para búsqueda de hiperparámetros
- **Horizontes**: 5, 10 y 15 días hábiles
- **A/B Testing**: Despliegue automático solo si el nuevo modelo supera al actual
- **Parametrizable**: Todos los hiperparámetros configurables vía YAML

---

## 🏗️ Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                      STAGE: stage.precios_historicos             │
│                  (Datos OHLCV + Indicators diarios)              │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│              DATA LOADER + FEATURE ENGINEERING                   │
│  - Carga datos desde SQL Server                                 │
│  - Calcula indicadores técnicos (RSI, MACD, Bollinger, etc.)    │
│  - Crea features derivados (returns, volatilidad, etc.)         │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                     PREPROCESSING                                │
│  - Train/Val/Test split temporal (sin data leakage)             │
│  - Normalización (MinMaxScaler o StandardScaler)                │
│  - Generación de secuencias para LSTM                           │
│  - Ventanas deslizantes (lookback window)                       │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│              ALGORITMO GENÉTICO (Optimización)                   │
│                                                                  │
│  Generación 1:  [Individuo1, Individuo2, ..., Individuo20]     │
│      ↓          (Población inicial aleatoria)                   │
│  Evaluación:    Entrenar LSTM con cada set de hiperparámetros  │
│      ↓          Fitness = val_rmse (o métrica compuesta)        │
│  Selección:     Torneo / Elitismo                               │
│      ↓                                                          │
│  Crossover:     Combinar mejores individuos                     │
│      ↓                                                          │
│  Mutación:      Alterar parámetros aleatoriamente (15%)         │
│      ↓                                                          │
│  Generación 2:  Nueva población mejorada                        │
│      ↓                                                          │
│  ... (Repetir 10 generaciones)                                  │
│      ↓                                                          │
│  MEJOR MODELO:  Individuo con mejor fitness                     │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                MODELO LSTM OPTIMIZADO                            │
│                                                                  │
│  Input Shape:  (sequence_length, num_features)                  │
│      ↓                                                          │
│  LSTM Layer 1: (hidden_units, return_sequences=True)            │
│  Dropout 1                                                       │
│      ↓                                                          │
│  LSTM Layer 2: (hidden_units, return_sequences=True/False)      │
│  Dropout 2                                                       │
│      ↓                                                          │
│  ... (Hasta num_layers)                                         │
│      ↓                                                          │
│  Dense Layer:  (1, activation='linear')                         │
│      ↓                                                          │
│  Output:       Predicted close price @ t+{5,10,15}              │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      BACKTESTING                                 │
│  - Walk-Forward Validation                                       │
│  - Métricas: RMSE, MAE, R², Sharpe, Win Rate                    │
│  - Simula operación en producción                               │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      A/B TESTING                                 │
│                                                                  │
│  Modelo A (Producción):  WALMEX_5d_v1.2 (actual)                │
│  Modelo B (Challenger):  WALMEX_5d_v2.0 (nuevo optimizado)      │
│      ↓                                                          │
│  Período de prueba: 30 días                                     │
│      ↓                                                          │
│  Comparar métricas:                                             │
│    - RMSE: A=2.5%, B=2.1% ✅ (16% mejor)                        │
│    - MAE: A=1.8%, B=1.5% ✅ (16% mejor)                         │
│    - Win Rate: A=58%, B=62% ✅ (7% mejor)                       │
│    - Sharpe: A=0.8, B=1.1 ✅ (37% mejor)                        │
│      ↓                                                          │
│  DECISIÓN: DESPLEGAR MODELO B ✅                                │
│      ↓                                                          │
│  - Archivar Modelo A                                            │
│  - Marcar Modelo B como is_production=1                         │
│  - Registrar en ml.ab_tests                                     │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│              PRODUCCIÓN: ml.predictions                          │
│                                                                  │
│  Cada día a las 5 PM (después del ETL incremental):             │
│    1. Cargar datos de hoy desde stage.precios_historicos        │
│    2. Generar secuencia de lookback (últimos N días)            │
│    3. Predecir precio para t+5, t+10, t+15                      │
│    4. Guardar en ml.predictions                                 │
│    5. Actualizar predictions pasadas con valores reales         │
│    6. Calcular métricas de error                                │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│              MONITOREO CONTINUO                                  │
│  - Detectar drift en distribución de datos                      │
│  - Alertar si performance degrada >10%                           │
│  - Trigger reentrenamiento automático si es necesario           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📁 Estructura de Archivos

```
src/ml/
├── config/
│   ├── lstm_search_space.yml          ✅ CREADO
│   └── training_config.yml            ✅ CREADO
│
├── shared/
│   ├── data_loaders/
│   │   ├── __init__.py
│   │   ├── base_loader.py             # ABC para data loaders
│   │   ├── ohlcv_loader.py            # Carga OHLCV desde stage.precios_historicos
│   │   └── feature_engineering.py     # RSI, MACD, Bollinger, etc.
│   │
│   ├── preprocessors/
│   │   ├── __init__.py
│   │   ├── scaler.py                  # MinMax/Standard scaler
│   │   ├── sequence_generator.py      # Genera secuencias [lookback, features]
│   │   └── train_test_splitter.py     # Split temporal sin data leakage
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── lstm_model.py              # Arquitectura LSTM
│   │   └── model_config.py            # Dataclass: LSTMConfig
│   │
│   ├── optimizers/
│   │   ├── __init__.py
│   │   ├── genetic_algorithm.py       # Clase GeneticAlgorithm
│   │   ├── chromosome.py              # Representa un individuo (hiperparámetros)
│   │   └── fitness_evaluator.py       # Evalúa fitness de un modelo
│   │
│   ├── evaluators/
│   │   ├── __init__.py
│   │   ├── backtester.py              # Walk-forward backtesting
│   │   ├── metrics.py                 # RMSE, MAE, R², Sharpe, Win Rate
│   │   └── ab_tester.py               # Compara modelo A vs B
│   │
│   └── persistence/
│       ├── __init__.py
│       ├── model_registry.py          # Save/load models desde ml.model_registry
│       └── experiment_tracker.py      # Registra experimentos en ml.experiments
│
├── pipelines/
│   ├── __init__.py
│   ├── train_pipeline.py              # Pipeline completo de entrenamiento
│   ├── predict_pipeline.py            # Pipeline de predicción
│   └── optimization_pipeline.py       # Pipeline GA completo
│
└── scripts/
    ├── train_model.py                 # python train_model.py --ticker WALMEX --horizon 5
    ├── optimize_hyperparams.py        # python optimize_hyperparams.py --ticker WALMEX
    ├── predict_next_days.py           # python predict_next_days.py --ticker WALMEX
    ├── evaluate_model.py              # python evaluate_model.py --model-id 123
    └── deploy_model.py                # python deploy_model.py --model-id 124
```

---

## 🧬 Algoritmo Genético - Detalles

### Representación del Cromosoma
```python
Chromosome = {
    'num_layers': 3,
    'hidden_units': 128,
    'dropout_rate': 0.25,
    'learning_rate': 0.001,
    'batch_size': 64,
    'epochs': 200,
    'sequence_length': 60,
    'optimizer': 'adam',
    'dense_activation': 'relu'
}
```

### Proceso de Evolución
1. **Inicialización**: Población de 20 individuos con hiperparámetros aleatorios
2. **Evaluación**: Entrenar LSTM con cada cromosoma, calcular fitness (val_rmse)
3. **Selección**: Torneo de 3 individuos, seleccionar mejores
4. **Elitismo**: Los 2 mejores pasan automáticamente a siguiente generación
5. **Crossover**: Combinar genes de 2 padres (70% probabilidad)
6. **Mutación**: Alterar genes aleatoriamente (15% probabilidad)
7. **Repetir**: 10 generaciones
8. **Resultado**: Mejor individuo de todas las generaciones

### Fitness Multiobjetivo (Opcional)
```python
fitness = (
    0.4 * val_rmse +
    0.3 * val_mae +
    0.2 * (1 / sharpe_ratio) +  # Invertir porque GA minimiza
    0.1 * (1 - win_rate)
)
```

---

## 📊 Schema de Base de Datos

### `ml.model_registry`
Almacena todos los modelos entrenados con sus hiperparámetros y métricas.

**Campos clave**:
- `model_id`: ID único
- `ticker_id`: FK a stage.cat_tickers
- `prediction_horizon`: 5, 10, 15 días
- `hyperparameters`: JSON con todos los parámetros
- `test_rmse`, `test_mae`, `test_r2`: Métricas en test set
- `sharpe_ratio`, `win_rate`: Métricas financieras
- `is_production`: 1 si está activo en producción
- `model_file_path`: Ruta al archivo .h5

### `ml.experiments`
Registra cada experimento de optimización con GA.

**Campos clave**:
- `experiment_id`: ID único
- `best_model_id`: FK al mejor modelo encontrado
- `population_size`, `num_generations`: Configuración del GA
- `best_fitness`: Mejor fitness alcanzado

### `ml.predictions`
Almacena predicciones generadas diariamente.

**Campos clave**:
- `prediction_date`: Cuándo se hizo la predicción
- `target_date`: Fecha que se está prediciendo
- `days_ahead`: 1, 2, 3... hasta 15
- `predicted_close`: Precio predicho
- `actual_close`: Precio real (se llena después)
- `direction_correct`: Si acertó dirección (UP/DOWN)

### `ml.ab_tests`
Registra comparaciones entre modelo actual vs challenger.

**Campos clave**:
- `model_a_id`: Modelo en producción
- `model_b_id`: Modelo challenger
- `winner`: 'MODEL_A', 'MODEL_B', 'TIE'
- `improvement_percentage`: % de mejora

---

## 🎯 Uso del Framework

### 1. Optimizar hiperparámetros con GA
```bash
python src/ml/scripts/optimize_hyperparams.py \
    --ticker WALMEX \
    --horizon 5 \
    --population-size 20 \
    --generations 10
```

**Salida**:
- Mejor modelo guardado en `models/WALMEX_5d_v2.0.h5`
- Scaler guardado en `scalers/WALMEX_5d_v2.0_scaler.pkl`
- Registro en `ml.experiments` y `ml.model_registry`

### 2. Entrenar modelo con parámetros específicos
```bash
python src/ml/scripts/train_model.py \
    --ticker WALMEX \
    --horizon 5 \
    --num-layers 3 \
    --hidden-units 128 \
    --dropout 0.25 \
    --learning-rate 0.001
```

### 3. Generar predicciones
```bash
python src/ml/scripts/predict_next_days.py \
    --ticker WALMEX \
    --model-id 124
```

**Salida**: Inserta en `ml.predictions`:
```
prediction_date | target_date | days_ahead | predicted_close
2025-12-29      | 2026-01-06  | 5          | 82.50
2025-12-29      | 2026-01-13  | 10         | 83.20
2025-12-29      | 2026-01-21  | 15         | 84.10
```

### 4. A/B Testing
```bash
python src/ml/scripts/deploy_model.py \
    --current-model-id 120 \
    --challenger-model-id 124 \
    --test-days 30
```

**Proceso**:
1. Compara métricas de ambos modelos en últimos 30 días
2. Si challenger es >5% mejor en RMSE/MAE/Win Rate
3. Despliega automáticamente y archiva el anterior
4. Registra en `ml.ab_tests`

### 5. Evaluación de modelo
```bash
python src/ml/scripts/evaluate_model.py \
    --model-id 124 \
    --start-date 2025-11-01 \
    --end-date 2025-12-29
```

**Salida**:
```
📊 Evaluación del Modelo 124 (WALMEX_5d_v2.0)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Período: 2025-11-01 a 2025-12-29 (59 días)

Métricas de Error:
  RMSE:  1.85
  MAE:   1.42
  MAPE:  2.1%
  R²:    0.94

Métricas Financieras:
  Win Rate:      64.5%
  Sharpe Ratio:  1.23
  Max Drawdown:  -3.2%

Predicciones por horizonte:
  5 días:  RMSE=1.20, Win Rate=68%
  10 días: RMSE=1.85, Win Rate=62%
  15 días: RMSE=2.50, Win Rate=59%
```

---

## 🔄 Pipeline Diario Automatizado

**Script**: `src/ml/scripts/daily_ml_pipeline.py`

**Ejecución**: Todos los días a las 5:00 PM (después del ETL incremental)

**Proceso**:
1. Actualizar predicciones pasadas con valores reales
2. Calcular métricas de error
3. Generar nuevas predicciones para hoy
4. Verificar drift en distribución de datos
5. Si performance cae >10%, alertar para reentrenamiento
6. Guardar logs en `ml.predictions`

**Scheduled Task**:
```cmd
schtasks /Create /TN "ML-Daily-Predictions" /TR "C:\Projects\stock-market\scripts\ml_daily.bat" /SC DAILY /ST 17:00
```

---

## 📈 Roadmap de Implementación

### Fase 1: Infraestructura Base (Semana 1) ✅ PLANIFICADO
- [x] Crear schema `ml` en SQL Server
- [ ] Implementar `data_loaders/ohlcv_loader.py`
- [ ] Implementar `preprocessors/scaler.py`
- [ ] Implementar `preprocessors/sequence_generator.py`
- [ ] Implementar `models/lstm_model.py`
- [ ] Tests unitarios

### Fase 2: Feature Engineering (Semana 2)
- [ ] Implementar indicadores técnicos (RSI, MACD, Bollinger)
- [ ] Implementar features derivados (returns, volatility)
- [ ] Crear tabla `golden.indicadores_tecnicos` (si no existe)
- [ ] Pipeline de generación de features

### Fase 3: Algoritmo Genético (Semana 3)
- [ ] Implementar `genetic_algorithm.py`
- [ ] Implementar `chromosome.py`
- [ ] Implementar `fitness_evaluator.py`
- [ ] Script `optimize_hyperparams.py`
- [ ] Validar con WALMEX 5 días

### Fase 4: Training & Backtesting (Semana 4)
- [ ] Implementar `train_pipeline.py`
- [ ] Implementar `backtester.py` (walk-forward)
- [ ] Implementar `metrics.py`
- [ ] Script `train_model.py`
- [ ] Entrenar primeros modelos para WALMEX y ALSEA

### Fase 5: A/B Testing & Deployment (Semana 5)
- [ ] Implementar `ab_tester.py`
- [ ] Implementar `model_registry.py`
- [ ] Script `deploy_model.py`
- [ ] Crear pipeline de despliegue automático

### Fase 6: Producción & Monitoreo (Semana 6)
- [ ] Implementar `predict_pipeline.py`
- [ ] Script `daily_ml_pipeline.py`
- [ ] Configurar Scheduled Task para predicciones diarias
- [ ] Dashboard de monitoreo (opcional: Streamlit/Dash)

### Fase 7: Expansión (Futuro)
- [ ] Agregar más tickers (GFNORTE, CEMEX, AMX, etc.)
- [ ] Implementar ensemble de modelos (LSTM + GRU + Transformer)
- [ ] Implementar modelos de atención (Attention mechanisms)
- [ ] Trading bot con estrategias basadas en predicciones

---

## 🔧 Comandos Útiles

### Crear schema ML en SQL Server
```bash
# Desde Windows
sqlcmd -S localhost -d MercadoBursatil -i C:\Projects\stock-market\sql\02_create_ml_schema.sql

# Desde PowerShell
Invoke-Sqlcmd -ServerInstance localhost -Database MercadoBursatil -InputFile "C:\Projects\stock-market\sql\02_create_ml_schema.sql"
```

### Ver modelos en producción
```sql
SELECT * FROM ml.v_production_models;
```

### Ver performance de predicciones
```sql
SELECT * FROM ml.v_prediction_performance
WHERE days_ahead = 5
ORDER BY direction_accuracy DESC;
```

### Actualizar predicciones con valores reales
```sql
EXEC ml.sp_update_predictions_with_actuals;
```

### Desplegar modelo a producción
```sql
EXEC ml.sp_deploy_model @model_id = 124;
```

---

## 📝 Notas Importantes

1. **Data Leakage**: El split temporal asegura que NUNCA entrenamos con datos futuros
2. **Normalización**: SIEMPRE normalizar antes de crear secuencias
3. **Guardar Scaler**: El scaler usado en training debe guardarse para producción
4. **Walk-Forward**: Backtesting usa ventanas deslizantes para simular producción real
5. **Reentrenamiento**: Modelos deben reentrenarse cada 30-60 días mínimo
6. **Drift Detection**: Monitorear distribución de features para detectar cambios

---

## 🚀 ¿Qué sigue AHORA?

1. **Ejecutar SQL**: Crear schema `ml` en tu servidor Windows
2. **Implementar Data Loader**: Primer componente crítico
3. **Implementar LSTM Model**: Arquitectura base parametrizable
4. **Validar con datos reales**: Entrenar 1 modelo simple para WALMEX 5 días
5. **Iterar**: Agregar GA, A/B testing, etc.

¿Quieres que empecemos implementando el **Data Loader** o el **LSTM Model**?
