# 🧠 ML Framework - Machine Learning para Predicción de Precios

Framework completo de Machine Learning con LSTM y Genetic Algorithm para predicción de precios de acciones.

## 📁 Estructura

```
src/ml/
├── config/                    # Archivos de configuración YAML
│   ├── lstm_search_space.yml # Espacio de búsqueda para GA
│   └── training_config.yml   # Configuración de entrenamiento
├── shared/                   # Componentes reutilizables
│   ├── data_loaders/        # Carga de datos y feature engineering
│   ├── preprocessors/       # Scaling, sequences, splits
│   ├── models/              # Modelo LSTM
│   ├── optimizers/          # Genetic Algorithm
│   ├── evaluators/          # Métricas, Backtesting, A/B Testing
│   └── persistence/         # Model Registry, Experiment Tracker
├── pipelines/               # Pipelines end-to-end
│   ├── train_pipeline.py    # Pipeline de entrenamiento
│   ├── predict_pipeline.py  # Pipeline de predicción
│   └── optimization_pipeline.py  # Pipeline de optimización GA
└── scripts/                 # Scripts CLI ejecutables
    ├── train_model.py       # Entrenar modelo
    ├── optimize_hyperparams.py  # Optimizar con GA
    ├── predict_next_days.py # Generar predicciones
    ├── evaluate_model.py    # Evaluar con backtesting
    └── deploy_model.py      # A/B testing y deployment
```

## 🚀 Quick Start

### 1. Ejecutar SQL Schema

Primero, ejecutar el schema de base de datos:

```sql
-- En SQL Server Management Studio
USE MercadoBursatil;
GO

-- Ejecutar sql/02_create_ml_schema.sql
```

### 2. Entrenar un modelo

```bash
# Entrenar modelo con configuración por defecto
python src/ml/scripts/train_model.py --ticker WALMEX --horizon 5

# Entrenar con parámetros específicos
python src/ml/scripts/train_model.py \
    --ticker WALMEX \
    --horizon 10 \
    --num-layers 3 \
    --hidden-units 256 \
    --learning-rate 0.0005 \
    --batch-size 64 \
    --epochs 150
```

### 3. Optimizar hyperparámetros con GA

```bash
# Optimización estándar (20 individuos, 10 generaciones)
python src/ml/scripts/optimize_hyperparams.py \
    --ticker WALMEX \
    --horizon 5

# Optimización intensiva (30 individuos, 15 generaciones)
python src/ml/scripts/optimize_hyperparams.py \
    --ticker WALMEX \
    --horizon 10 \
    --population 30 \
    --generations 15
```

⚠️ **Nota**: La optimización puede tomar varias horas (depende de población × generaciones).

### 4. Generar predicciones

```bash
# Usar modelo en producción
python src/ml/scripts/predict_next_days.py \
    --ticker WALMEX \
    --horizon 5

# Usar modelo específico
python src/ml/scripts/predict_next_days.py \
    --ticker WALMEX \
    --horizon 10 \
    --model-id 124
```

### 5. Evaluar modelo con backtesting

```bash
# Evaluar modelo en datos históricos
python src/ml/scripts/evaluate_model.py --model-id 124

# Evaluar desde fecha específica
python src/ml/scripts/evaluate_model.py \
    --model-id 124 \
    --start-date 2024-11-01
```

### 6. Deployment con A/B Testing

```bash
# Comparar modelo actual vs challenger
python src/ml/scripts/deploy_model.py \
    --current-model-id 120 \
    --challenger-id 124 \
    --test-days 30

# Deployment automático (sin confirmación manual)
python src/ml/scripts/deploy_model.py \
    --current-model-id 120 \
    --challenger-id 124 \
    --auto-deploy
```

## 📊 Workflow Completo

### Escenario 1: Entrenar nuevo modelo desde cero

```bash
# 1. Entrenar modelo inicial
python src/ml/scripts/train_model.py --ticker WALMEX --horizon 5
# Output: Modelo ID 100

# 2. Evaluar rendimiento
python src/ml/scripts/evaluate_model.py --model-id 100

# 3. Si es el primer modelo, marcar como producción manualmente en DB:
# UPDATE ml.model_registry SET status = 'PRODUCTION' WHERE model_id = 100

# 4. Generar predicciones
python src/ml/scripts/predict_next_days.py --ticker WALMEX --horizon 5
```

### Escenario 2: Optimizar hyperparámetros

```bash
# 1. Ejecutar Genetic Algorithm
python src/ml/scripts/optimize_hyperparams.py --ticker WALMEX --horizon 5
# Output: Experimento ID 1, Mejor modelo ID 124

# 2. Evaluar mejor modelo encontrado
python src/ml/scripts/evaluate_model.py --model-id 124

# 3. A/B Testing vs modelo en producción
python src/ml/scripts/deploy_model.py --current-model-id 100 --challenger-id 124

# 4. Si pasa A/B test, se despliega automáticamente a producción
```

### Escenario 3: Pipeline diario de predicciones

```bash
# Script a ejecutar diariamente (ej: 5:00 PM)

# 1. Actualizar predicciones con valores reales (Stored Procedure)
# EXEC ml.sp_update_predictions_with_actuals

# 2. Generar nuevas predicciones para todos los tickers
python src/ml/scripts/predict_next_days.py --ticker WALMEX --horizon 5
python src/ml/scripts/predict_next_days.py --ticker WALMEX --horizon 10
python src/ml/scripts/predict_next_days.py --ticker WALMEX --horizon 15

python src/ml/scripts/predict_next_days.py --ticker ALSEA --horizon 5
# ... etc para cada ticker
```

## 🔧 Configuración

### training_config.yml

Configuración de base de datos, paths y parámetros generales:

```yaml
database:
  server: "192.168.1.5"
  database: "MercadoBursatil"
  username: "sa"
  password: "your_password"

paths:
  models_dir: "models/"
  scalers_dir: "scalers/"
  logs_dir: "logs/"

sequence_length: 60  # Días históricos para entrenar

tickers:
  - WALMEX
  - ALSEA
  - GFNORTE
```

### lstm_search_space.yml

Espacio de búsqueda para Genetic Algorithm:

```yaml
model_architecture:
  num_layers: [1, 2, 3, 4]
  hidden_units: [32, 64, 128, 256, 512]
  dropout_rate: [0.0, 0.5, 0.05]  # [min, max, step]

training:
  learning_rate: [0.00001, 0.01]  # log scale
  batch_size: [16, 32, 64, 128]
  epochs: [50, 300]

genetic_algorithm:
  population_size: 20
  num_generations: 10
  mutation_rate: 0.15
  crossover_rate: 0.7
```

## 📈 Métricas Implementadas

- **RMSE**: Root Mean Squared Error
- **MAE**: Mean Absolute Error
- **MAPE**: Mean Absolute Percentage Error
- **R²**: Coefficient of Determination
- **Win Rate**: Proporción de direcciones correctas
- **Sharpe Ratio**: Retorno ajustado por riesgo
- **Sortino Ratio**: Sharpe con solo downside risk
- **Max Drawdown**: Máxima caída desde pico
- **Calmar Ratio**: Retorno anualizado / Max Drawdown

## 🧬 Genetic Algorithm

Configuración:
- **Population**: 20 individuos
- **Generations**: 10
- **Mutation rate**: 15%
- **Crossover**: Uniform (50% de cada padre)
- **Elitism**: 2 mejores pasan directo
- **Selection**: Tournament (size=3)

Fitness:
- Simple: `val_rmse` (menor es mejor)
- Composite: `0.4*RMSE + 0.3*MAE + 0.2*(1/Sharpe) + 0.1*(1-WinRate)`

## 🧪 A/B Testing

Criterios de deployment:
- RMSE: Mejora >= 5%
- MAE: Mejora >= 5%
- Win Rate: Mejora >= 2% (absoluto)
- Sharpe Ratio: Mejora >= 10%
- Significancia estadística: p-value < 0.05

Pruebas estadísticas:
- Paired t-test (errores)
- Wilcoxon signed-rank test (no paramétrico)

## 📊 Base de Datos

### Tablas principales

```sql
-- Modelos entrenados
ml.model_registry
  - model_id
  - ticker_id
  - horizon_days
  - hyperparameters (JSON)
  - train_rmse, val_rmse, test_rmse
  - sharpe_ratio, win_rate
  - status (TRAINED, PRODUCTION, DEPRECATED)

-- Experimentos de optimización
ml.experiments
  - experiment_id
  - ticker_id
  - config (JSON)
  - best_model_id
  - status (RUNNING, COMPLETED, FAILED)

-- Predicciones generadas
ml.predictions
  - model_id
  - ticker_id
  - prediction_date
  - target_date
  - days_ahead
  - predicted_close
  - actual_close (NULL hasta que se tenga el valor real)

-- A/B Tests
ml.ab_tests
  - model_a_id (producción)
  - model_b_id (challenger)
  - winner (MODEL_A, MODEL_B, TIE)
  - deployed (TRUE/FALSE)
```

### Stored Procedures

```sql
-- Actualizar predicciones con valores reales
EXEC ml.sp_update_predictions_with_actuals

-- Desplegar modelo a producción
EXEC ml.sp_deploy_model @model_id = 124, @ticker_id = 1, @horizon_days = 5
```

## 🔍 Consultas Útiles

```sql
-- Ver modelos en producción
SELECT * FROM ml.v_production_models

-- Ver rendimiento de predicciones
SELECT * FROM ml.v_prediction_performance
WHERE ticker_id = 1 AND horizon_days = 5

-- Ver mejor experimento
SELECT TOP 1 *
FROM ml.experiments
WHERE status = 'COMPLETED'
ORDER BY best_val_rmse ASC

-- Ver últimas predicciones
SELECT TOP 10 *
FROM ml.predictions
WHERE ticker_id = 1
ORDER BY prediction_date DESC
```

## 🐛 Troubleshooting

### Error: "Ticker no encontrado"

Verificar que el ticker existe en `stage.cat_tickers`:

```sql
SELECT * FROM stage.cat_tickers WHERE emisora = 'WALMEX'
```

### Error: "No hay modelo en producción"

Marcar modelo como producción:

```sql
UPDATE ml.model_registry 
SET status = 'PRODUCTION' 
WHERE model_id = 100
```

### Error: "Insufficient data"

Verificar datos disponibles:

```sql
SELECT COUNT(*) 
FROM stage.precios_historicos 
WHERE ticker_id = 1
```

Debe haber al menos 1 año de datos (252 registros).

## 📚 Documentación Adicional

Ver `docs/ML_FRAMEWORK_ARCHITECTURE.md` para:
- Arquitectura completa
- Diagramas de flujo
- Roadmap de desarrollo
- Mejores prácticas

## 🎯 Próximos Pasos

1. Ejecutar SQL schema en servidor Windows
2. Entrenar primer modelo: `python src/ml/scripts/train_model.py --ticker WALMEX --horizon 5`
3. Optimizar hyperparams: `python src/ml/scripts/optimize_hyperparams.py --ticker WALMEX --horizon 5`
4. Evaluar y desplegar: `python src/ml/scripts/deploy_model.py ...`
5. Configurar pipeline diario de predicciones

## 🤝 Contribuir

Este framework está diseñado para ser extensible:
- Agregar nuevos modelos (GRU, Transformer, etc.)
- Agregar nuevas features (sentiment analysis, news, etc.)
- Agregar nuevos optimizadores (Bayesian Optimization, etc.)
- Agregar nuevos evaluadores (cross-validation, etc.)
