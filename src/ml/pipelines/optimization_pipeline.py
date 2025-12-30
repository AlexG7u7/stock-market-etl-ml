"""
Optimization Pipeline - Orquestación del Genetic Algorithm
"""
import yaml
from pathlib import Path
from typing import Dict, Optional
from loguru import logger

from ..shared.optimizers.genetic_algorithm import GeneticAlgorithm
from ..shared.optimizers.chromosome import Chromosome
from ..shared.persistence.experiment_tracker import ExperimentTracker
from .train_pipeline import TrainingPipeline


class OptimizationPipeline:
    """
    Pipeline de optimización con Genetic Algorithm:
    1. Crear experimento
    2. Inicializar GA
    3. Para cada generación:
       - Entrenar modelos con diferentes hyperparams
       - Evaluar fitness
       - Evolucionar población
    4. Guardar mejor modelo
    5. Finalizar experimento
    """
    
    def __init__(
        self,
        config_path: str = "src/ml/config/lstm_search_space.yml",
        training_config_path: str = "src/ml/config/training_config.yml"
    ):
        """
        Args:
            config_path: Path a configuración de GA
            training_config_path: Path a configuración de entrenamiento
        """
        self.config_path = Path(config_path)
        self.training_config_path = Path(training_config_path)
        
        self.search_space_config = self._load_config(self.config_path)
        self.training_config = self._load_config(self.training_config_path)
        
        self.experiment_tracker = None
        self.training_pipeline = None
    
    def _load_config(self, path: Path) -> Dict:
        """Cargar configuración YAML"""
        with open(path, 'r') as f:
            return yaml.safe_load(f)
    
    def run(
        self,
        ticker: str,
        horizon_days: int = 5,
        population_size: Optional[int] = None,
        num_generations: Optional[int] = None
    ) -> Dict:
        """
        Ejecutar optimización con GA
        
        Args:
            ticker: Símbolo del ticker
            horizon_days: Días a predecir
            population_size: Tamaño población (usa config si es None)
            num_generations: Número de generaciones (usa config si es None)
            
        Returns:
            Dict con resultados de optimización
        """
        logger.info("=" * 80)
        logger.info("🧬 OPTIMIZATION PIPELINE - GENETIC ALGORITHM")
        logger.info("=" * 80)
        logger.info(f"Ticker: {ticker}")
        logger.info(f"Horizon: {horizon_days} días")
        logger.info("")
        
        # Configuración de GA
        ga_config = self.search_space_config.get('genetic_algorithm', {})
        
        if population_size:
            ga_config['population_size'] = population_size
        if num_generations:
            ga_config['num_generations'] = num_generations
        
        logger.info("🔧 Configuración GA:")
        logger.info(f"   Population: {ga_config['population_size']}")
        logger.info(f"   Generations: {ga_config['num_generations']}")
        logger.info(f"   Mutation rate: {ga_config['mutation_rate']}")
        logger.info(f"   Crossover rate: {ga_config['crossover_rate']}")
        logger.info("")
        
        # 1. Crear experimento
        logger.info("🧪 PASO 1: Crear experimento...")
        experiment_id = self._create_experiment(ticker, horizon_days, ga_config)
        logger.success(f"✅ Experimento {experiment_id} creado")
        
        # 2. Inicializar GA
        logger.info("\n🧬 PASO 2: Inicializar Genetic Algorithm...")
        ga = GeneticAlgorithm(
            search_space=self.search_space_config,
            population_size=ga_config['population_size'],
            num_generations=ga_config['num_generations'],
            mutation_rate=ga_config['mutation_rate'],
            crossover_rate=ga_config['crossover_rate'],
            elitism_count=ga_config.get('elitism', 2),
            tournament_size=ga_config.get('tournament_size', 3)
        )
        
        # 3. Definir función de fitness
        def fitness_function(chromosome: Chromosome) -> float:
            """
            Entrenar modelo con genes del cromosoma y retornar fitness
            """
            # Convertir cromosoma a LSTM config
            lstm_config = chromosome.to_lstm_config()
            
            # Entrenar modelo
            self.training_pipeline = TrainingPipeline(str(self.training_config_path))
            
            try:
                result = self.training_pipeline.run(
                    ticker=ticker,
                    horizon_days=horizon_days,
                    lstm_config=lstm_config,
                    experiment_id=experiment_id
                )
                
                # Fitness = val_rmse (menor es mejor)
                fitness = result['metrics'].get('val_rmse', float('inf'))
                
                return fitness
                
            except Exception as e:
                logger.error(f"❌ Error entrenando modelo: {e}")
                return float('inf')  # Peor fitness posible
        
        # 4. Ejecutar GA
        logger.info("\n🚀 PASO 3: Ejecutar Genetic Algorithm...")
        
        # Hook para registrar cada generación
        original_evaluate = ga.evaluate_fitness
        
        def evaluate_with_tracking(fitness_fn):
            original_evaluate(fitness_fn)
            
            # Después de evaluar, registrar generación
            if ga.generation_stats:
                last_gen = ga.generation_stats[-1]
                
                self.experiment_tracker.log_generation(
                    experiment_id=experiment_id,
                    generation_number=last_gen['generation'],
                    best_fitness=last_gen['best_fitness'],
                    avg_fitness=last_gen['avg_fitness'],
                    worst_fitness=last_gen['worst_fitness'],
                    best_hyperparameters=last_gen['best_genes']
                )
        
        # Reemplazar método
        ga.evaluate_fitness = evaluate_with_tracking
        
        # Evolucionar
        best_chromosome = ga.evolve(fitness_function)
        
        # 5. Entrenar modelo final con mejores hyperparams
        logger.info("\n🏆 PASO 4: Entrenar modelo final con mejores hyperparams...")
        
        best_config = best_chromosome.to_lstm_config()
        
        final_result = self.training_pipeline.run(
            ticker=ticker,
            horizon_days=horizon_days,
            lstm_config=best_config,
            experiment_id=experiment_id
        )
        
        best_model_id = final_result['model_id']
        
        logger.success(f"✅ Modelo final entrenado: ID {best_model_id}")
        
        # 6. Finalizar experimento
        logger.info("\n🏁 PASO 5: Finalizar experimento...")
        
        self.experiment_tracker.finalize_experiment(
            experiment_id=experiment_id,
            best_model_id=best_model_id,
            final_metrics=final_result['metrics'],
            status='COMPLETED'
        )
        
        logger.info("\n" + "=" * 80)
        logger.success("🎉 OPTIMIZACIÓN COMPLETADA")
        logger.info("=" * 80)
        logger.info(f"\nExperimento ID: {experiment_id}")
        logger.info(f"Mejor modelo ID: {best_model_id}")
        logger.info(f"\nMejores hyperparámetros:")
        for param, value in best_chromosome.genes.items():
            logger.info(f"   {param}: {value}")
        logger.info(f"\nMétricas finales:")
        logger.info(f"   Val RMSE: {final_result['metrics'].get('val_rmse', 'N/A'):.6f}")
        logger.info(f"   Val MAE: {final_result['metrics'].get('val_mae', 'N/A'):.6f}")
        logger.info(f"   Sharpe Ratio: {final_result['metrics'].get('val_sharpe_ratio', 'N/A'):.6f}")
        logger.info("")
        
        return {
            'experiment_id': experiment_id,
            'best_model_id': best_model_id,
            'best_hyperparameters': best_chromosome.genes,
            'best_fitness': best_chromosome.fitness,
            'final_metrics': final_result['metrics'],
            'generation_history': ga.get_generation_history()
        }
    
    def _create_experiment(
        self,
        ticker: str,
        horizon_days: int,
        ga_config: Dict
    ) -> int:
        """Crear experimento en base de datos"""
        import os
        from dotenv import load_dotenv
        
        # Cargar variables de entorno
        load_dotenv()
        
        # Obtener credenciales de .env
        server = os.getenv('SQL_SERVER', 'localhost')
        database = os.getenv('SQL_DATABASE', 'MercadoBursatil')
        username = os.getenv('SQL_USER', '')
        password = os.getenv('SQL_PASSWORD', '')
        
        # Construir connection string
        if username and password:
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={server};"
                f"DATABASE={database};"
                f"UID={username};"
                f"PWD={password}"
            )
        else:
            # Autenticación de Windows
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={server};"
                f"DATABASE={database};"
                f"Trusted_Connection=yes;"
            )
        
        self.experiment_tracker = ExperimentTracker(conn_str)
        
        # Obtener ticker_id
        ticker_id = self._get_ticker_id(ticker)
        
        experiment_id = self.experiment_tracker.create_experiment(
            ticker_id=ticker_id,
            horizon_days=horizon_days,
            search_space=self.search_space_config,
            ga_config=ga_config,
            description=f"GA optimization for {ticker}, horizon {horizon_days} days"
        )
        
        return experiment_id
    
    def _get_ticker_id(self, ticker: str) -> int:
        """Obtener ticker_id desde base de datos"""
        import pyodbc
        import os
        from dotenv import load_dotenv
        
        # Cargar variables de entorno
        load_dotenv()
        
        # Obtener credenciales de .env
        server = os.getenv('SQL_SERVER', 'localhost')
        database = os.getenv('SQL_DATABASE', 'MercadoBursatil')
        username = os.getenv('SQL_USER', '')
        password = os.getenv('SQL_PASSWORD', '')
        
        # Construir connection string
        if username and password:
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={server};"
                f"DATABASE={database};"
                f"UID={username};"
                f"PWD={password}"
            )
        else:
            # Autenticación de Windows
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={server};"
                f"DATABASE={database};"
                f"Trusted_Connection=yes;"
            )
        
        # Los tickers en DB están como WALMEX*, ALSEA*
        ticker_symbol = ticker if '*' in ticker else f"{ticker}*"
        
        with pyodbc.connect(conn_str) as conn:
            cursor = conn.cursor()
            
            query = "SELECT ticker_id FROM stage.cat_tickers WHERE emisora_serie = ?"
            cursor.execute(query, (ticker_symbol,))
            
            row = cursor.fetchone()
            
            if not row:
                raise ValueError(f"Ticker {ticker_symbol} no encontrado")
            
            return row[0]
