"""
Experiment Tracker - Registro de experimentos de Genetic Algorithm
"""
import json
from typing import Dict, Optional, List
from datetime import datetime
from loguru import logger
import pyodbc


class ExperimentTracker:
    """
    Tracker de experimentos de optimización
    
    Registra en ml.experiments y ml.experiment_generations:
    - Parámetros del experimento (GA config)
    - Historial de generaciones
    - Mejor individuo encontrado
    - Convergencia del algoritmo
    """
    
    def __init__(self, conn_str: str):
        """
        Args:
            conn_str: Connection string a SQL Server
        """
        self.conn_str = conn_str
        self.current_experiment_id: Optional[int] = None
    
    def create_experiment(
        self,
        ticker_id: int,
        horizon_days: int,
        search_space: Dict,
        ga_config: Dict,
        description: Optional[str] = None
    ) -> int:
        """
        Crear nuevo experimento
        
        Args:
            ticker_id: ID del ticker
            horizon_days: Horizonte de predicción
            search_space: Espacio de búsqueda de hyperparameters
            ga_config: Configuración del GA (population, generations, etc)
            description: Descripción opcional
            
        Returns:
            experiment_id: ID del experimento creado
        """
        logger.info("🧪 Creando nuevo experimento...")
        
        try:
            # Preparar search_space como JSON
            search_space_json = json.dumps(search_space)
            
            with pyodbc.connect(self.conn_str) as conn:
                cursor = conn.cursor()
                
                query = """
                INSERT INTO ml.experiments (
                    ticker_id,
                    experiment_name,
                    prediction_horizon,
                    population_size,
                    num_generations,
                    mutation_rate,
                    crossover_rate,
                    elitism_count,
                    search_space,
                    status
                )
                OUTPUT INSERTED.experiment_id
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                
                cursor.execute(query, (
                    ticker_id,
                    'GENETIC_ALGORITHM',
                    horizon_days,
                    ga_config.get('population_size'),
                    ga_config.get('num_generations'),
                    ga_config.get('mutation_rate'),
                    ga_config.get('crossover_rate'),
                    ga_config.get('elitism_count'),
                    search_space_json,
                    'running'
                ))
                
                experiment_id = cursor.fetchone()[0]
                conn.commit()
            
            self.current_experiment_id = experiment_id
            
            logger.success(f"✅ Experimento {experiment_id} creado")
            logger.info(f"   Ticker ID: {ticker_id}")
            logger.info(f"   Horizon: {horizon_days} días")
            logger.info(f"   Population: {ga_config.get('population_size')}")
            logger.info(f"   Generations: {ga_config.get('num_generations')}")
            
            return experiment_id
            
        except Exception as e:
            logger.error(f"❌ Error creando experimento: {e}")
            raise
    
    def log_generation(
        self,
        experiment_id: int,
        generation_number: int,
        best_fitness: float,
        avg_fitness: float,
        worst_fitness: float,
        best_hyperparameters: Dict,
        population_diversity: Optional[float] = None
    ):
        """
        Registrar una generación del GA
        
        Args:
            experiment_id: ID del experimento
            generation_number: Número de generación
            best_fitness: Mejor fitness de la generación
            avg_fitness: Fitness promedio
            worst_fitness: Peor fitness
            best_hyperparameters: Hyperparameters del mejor individuo
            population_diversity: Diversidad de la población (opcional)
        """
        try:
            hyperparams_json = json.dumps(best_hyperparameters)
            
            with pyodbc.connect(self.conn_str) as conn:
                cursor = conn.cursor()
                
                query = """
                INSERT INTO ml.experiment_generations (
                    experiment_id,
                    generation_number,
                    best_fitness,
                    avg_fitness,
                    worst_fitness,
                    std_fitness,
                    best_hyperparameters
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """
                
                cursor.execute(query, (
                    experiment_id,
                    generation_number,
                    best_fitness,
                    avg_fitness,
                    worst_fitness,
                    population_diversity,  # std_fitness
                    hyperparams_json
                ))
                
                conn.commit()
            
            logger.info(f"📝 Generación {generation_number} registrada (best fitness: {best_fitness:.6f})")
            
        except Exception as e:
            logger.error(f"❌ Error registrando generación: {e}")
    
    def finalize_experiment(
        self,
        experiment_id: int,
        best_model_id: Optional[int],
        final_metrics: Dict,
        status: str = 'COMPLETED'
    ):
        """
        Finalizar experimento
        
        Args:
            experiment_id: ID del experimento
            best_model_id: ID del mejor modelo encontrado
            final_metrics: Métricas finales
            status: Status final (COMPLETED, FAILED, CANCELLED)
        """
        logger.info(f"🏁 Finalizando experimento {experiment_id}...")
        
        try:
            with pyodbc.connect(self.conn_str) as conn:
                cursor = conn.cursor()
                
                # Calcular duración
                duration_query = """
                SELECT DATEDIFF(MINUTE, start_time, GETDATE())
                FROM ml.experiments
                WHERE experiment_id = ?
                """
                cursor.execute(duration_query, (experiment_id,))
                duration_minutes = cursor.fetchone()[0]
                
                query = """
                UPDATE ml.experiments
                SET 
                    best_model_id = ?,
                    best_fitness = ?,
                    best_hyperparameters = ?,
                    end_time = GETDATE(),
                    duration_minutes = ?,
                    status = ?
                WHERE experiment_id = ?
                """
                
                # Preparar best_hyperparameters como JSON
                best_hyperparams_json = json.dumps(final_metrics.get('best_hyperparameters', {}))
                
                cursor.execute(query, (
                    best_model_id,
                    final_metrics.get('fitness'),  # best_fitness
                    best_hyperparams_json,
                    duration_minutes,
                    status,
                    experiment_id
                ))
                
                conn.commit()
            
            logger.success(f"✅ Experimento {experiment_id} finalizado con status {status}")
            
            if best_model_id:
                logger.info(f"   Mejor modelo: {best_model_id}")
                logger.info(f"   Fitness: {final_metrics.get('fitness', 'N/A')}")
                logger.info(f"   Duración: {duration_minutes} minutos")
            
        except Exception as e:
            logger.error(f"❌ Error finalizando experimento: {e}")
            raise
    
    def get_experiment_history(self, experiment_id: int) -> List[Dict]:
        """
        Obtener historial de generaciones de un experimento
        
        Args:
            experiment_id: ID del experimento
            
        Returns:
            Lista de dicts con info de cada generación
        """
        try:
            with pyodbc.connect(self.conn_str) as conn:
                cursor = conn.cursor()
                
                query = """
                SELECT 
                    generation_number,
                    best_fitness,
                    avg_fitness,
                    worst_fitness,
                    best_hyperparameters,
                    population_diversity,
                    created_at
                FROM ml.experiment_generations
                WHERE experiment_id = ?
                ORDER BY generation_number
                """
                
                cursor.execute(query, (experiment_id,))
                
                history = []
                for row in cursor.fetchall():
                    history.append({
                        'generation': row[0],
                        'best_fitness': row[1],
                        'avg_fitness': row[2],
                        'worst_fitness': row[3],
                        'best_hyperparameters': json.loads(row[4]) if row[4] else None,
                        'diversity': row[5],
                        'timestamp': row[6]
                    })
                
                return history
                
        except Exception as e:
            logger.error(f"❌ Error obteniendo historial: {e}")
            return []
    
    def get_best_experiments(
        self,
        ticker_id: Optional[int] = None,
        limit: int = 10
    ) -> List[Dict]:
        """
        Obtener mejores experimentos
        
        Args:
            ticker_id: Filtrar por ticker (opcional)
            limit: Máximo de resultados
            
        Returns:
            Lista de experimentos ordenados por mejor métrica
        """
        try:
            with pyodbc.connect(self.conn_str) as conn:
                cursor = conn.cursor()
                
                query = f"""
                SELECT TOP {limit}
                    experiment_id,
                    ticker_id,
                    experiment_name,
                    prediction_horizon,
                    best_model_id,
                    best_fitness,
                    best_hyperparameters,
                    population_size,
                    num_generations,
                    total_models_trained,
                    status,
                    start_time,
                    end_time,
                    duration_minutes
                FROM ml.experiments
                WHERE status = 'completed'
                """
                
                params = []
                if ticker_id:
                    query += " AND ticker_id = ?"
                    params.append(ticker_id)
                
                query += " ORDER BY best_fitness DESC"
                
                cursor.execute(query, params)
                
                experiments = []
                for row in cursor.fetchall():
                    experiments.append({
                        'experiment_id': row[0],
                        'ticker_id': row[1],
                        'experiment_name': row[2],
                        'prediction_horizon': row[3],
                        'best_model_id': row[4],
                        'best_fitness': row[5],
                        'best_hyperparameters': row[6],
                        'population_size': row[7],
                        'num_generations': row[8],
                        'total_models_trained': row[9],
                        'status': row[10],
                        'start_time': row[11],
                        'end_time': row[12],
                        'duration_minutes': row[13]
                    })
                
                return experiments
                
        except Exception as e:
            logger.error(f"❌ Error obteniendo experimentos: {e}")
            return []
    
    def plot_experiment_convergence(
        self,
        experiment_id: int,
        save_path: Optional[str] = None
    ):
        """
        Graficar convergencia del experimento
        
        Args:
            experiment_id: ID del experimento
            save_path: Ruta donde guardar gráfico (opcional)
        """
        try:
            import matplotlib.pyplot as plt
            
            history = self.get_experiment_history(experiment_id)
            
            if not history:
                logger.warning("⚠️  No hay historial para graficar")
                return
            
            generations = [h['generation'] for h in history]
            best = [h['best_fitness'] for h in history]
            avg = [h['avg_fitness'] for h in history]
            worst = [h['worst_fitness'] for h in history]
            
            plt.figure(figsize=(12, 6))
            
            plt.plot(generations, best, 'g-', label='Mejor', linewidth=2)
            plt.plot(generations, avg, 'b--', label='Promedio')
            plt.plot(generations, worst, 'r:', label='Peor')
            
            plt.xlabel('Generación')
            plt.ylabel('Fitness (menor es mejor)')
            plt.title(f'Convergencia del Experimento {experiment_id}')
            plt.legend()
            plt.grid(True, alpha=0.3)
            
            if save_path:
                plt.savefig(save_path, dpi=300, bbox_inches='tight')
                logger.info(f"📊 Gráfico guardado en {save_path}")
            else:
                plt.show()
            
            plt.close()
            
        except ImportError:
            logger.warning("⚠️  matplotlib no disponible para graficar")
        except Exception as e:
            logger.error(f"❌ Error graficando convergencia: {e}")
