"""
Genetic Algorithm - Optimización de hiperparámetros
"""
import random
import numpy as np
from typing import List, Dict, Any, Optional, Callable
from loguru import logger
from tqdm import tqdm

from .chromosome import Chromosome
from .fitness_evaluator import FitnessEvaluator


class GeneticAlgorithm:
    """
    Algoritmo Genético para optimizar hiperparámetros de LSTM
    
    Proceso:
    1. Inicializar población aleatoria
    2. Evaluar fitness de cada individuo
    3. Selección (torneo)
    4. Crossover (combinar padres)
    5. Mutación
    6. Elitismo (mantener mejores)
    7. Repetir 2-6 por N generaciones
    """
    
    def __init__(
        self,
        search_space: Dict[str, Any],
        population_size: int = 20,
        num_generations: int = 10,
        mutation_rate: float = 0.15,
        crossover_rate: float = 0.7,
        elitism_count: int = 2,
        tournament_size: int = 3,
        fitness_evaluator: Optional[FitnessEvaluator] = None
    ):
        """
        Args:
            search_space: Espacio de búsqueda de hiperparámetros
            population_size: Tamaño de la población
            num_generations: Número de generaciones
            mutation_rate: Probabilidad de mutación
            crossover_rate: Probabilidad de crossover
            elitism_count: Mejores individuos que pasan directo
            tournament_size: Tamaño del torneo para selección
            fitness_evaluator: Evaluador de fitness
        """
        self.search_space = search_space
        self.population_size = population_size
        self.num_generations = num_generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.elitism_count = elitism_count
        self.tournament_size = tournament_size
        
        self.fitness_evaluator = fitness_evaluator or FitnessEvaluator()
        
        self.population: List[Chromosome] = []
        self.best_chromosome: Optional[Chromosome] = None
        self.generation_stats: List[Dict] = []
    
    def initialize_population(self):
        """Crear población inicial aleatoria"""
        logger.info(f"🧬 Inicializando población de {self.population_size} individuos...")
        
        self.population = [
            Chromosome.random(self.search_space)
            for _ in range(self.population_size)
        ]
        
        logger.success(f"✅ Población inicial creada")
    
    def evaluate_fitness(
        self,
        fitness_function: Callable[[Chromosome], float]
    ):
        """
        Evaluar fitness de toda la población
        
        Args:
            fitness_function: Función que toma un Chromosome y retorna fitness
        """
        logger.info("📊 Evaluando fitness de la población...")
        
        for chromosome in tqdm(self.population, desc="Evaluando individuos"):
            if chromosome.fitness is None:
                chromosome.fitness = fitness_function(chromosome)
        
        # Ordenar por fitness (menor es mejor)
        self.population.sort()
        
        # Actualizar mejor cromosoma global
        if self.best_chromosome is None or self.population[0].fitness < self.best_chromosome.fitness:
            self.best_chromosome = self.population[0]
    
    def selection_tournament(self) -> Chromosome:
        """
        Selección por torneo
        
        Returns:
            Cromosoma ganador del torneo
        """
        # Seleccionar individuos aleatorios para torneo
        tournament = random.sample(self.population, self.tournament_size)
        
        # Retornar el mejor del torneo
        return min(tournament, key=lambda x: x.fitness)
    
    def crossover(self, parent1: Chromosome, parent2: Chromosome) -> tuple:
        """
        Aplicar crossover con probabilidad
        
        Args:
            parent1: Primer padre
            parent2: Segundo padre
            
        Returns:
            (child1, child2)
        """
        if random.random() < self.crossover_rate:
            return Chromosome.crossover(parent1, parent2)
        else:
            # Sin crossover, clonar padres
            return parent1, parent2
    
    def evolve(self, fitness_function: Callable[[Chromosome], float]):
        """
        Ejecutar algoritmo genético completo
        
        Args:
            fitness_function: Función para evaluar fitness de un cromosoma
        """
        logger.info("=" * 80)
        logger.info("🧬 ALGORITMO GENÉTICO - INICIO")
        logger.info("=" * 80)
        logger.info(f"Población: {self.population_size}")
        logger.info(f"Generaciones: {self.num_generations}")
        logger.info(f"Mutation rate: {self.mutation_rate}")
        logger.info(f"Crossover rate: {self.crossover_rate}")
        logger.info(f"Elitismo: {self.elitism_count}")
        logger.info("")
        
        # Inicializar población
        self.initialize_population()
        
        # Evaluar población inicial
        self.evaluate_fitness(fitness_function)
        
        # Evolucionar por N generaciones
        for generation in range(self.num_generations):
            logger.info(f"\n{'='*80}")
            logger.info(f"GENERACIÓN {generation + 1}/{self.num_generations}")
            logger.info(f"{'='*80}")
            
            # Crear nueva población
            new_population = []
            
            # Elitismo: mantener mejores individuos
            elite = self.population[:self.elitism_count]
            new_population.extend(elite)
            logger.info(f"🏆 Elitismo: {self.elitism_count} mejores pasan directamente")
            
            # Generar resto de población
            while len(new_population) < self.population_size:
                # Selección
                parent1 = self.selection_tournament()
                parent2 = self.selection_tournament()
                
                # Crossover
                child1, child2 = self.crossover(parent1, parent2)
                
                # Mutación
                child1 = child1.mutate(self.mutation_rate)
                child2 = child2.mutate(self.mutation_rate)
                
                new_population.append(child1)
                if len(new_population) < self.population_size:
                    new_population.append(child2)
            
            # Reemplazar población
            self.population = new_population
            
            # Evaluar nueva población
            self.evaluate_fitness(fitness_function)
            
            # Estadísticas de generación
            stats = self._calculate_generation_stats(generation + 1)
            self.generation_stats.append(stats)
            
            # Log de progreso
            logger.info(f"\n📊 Estadísticas de Generación {generation + 1}:")
            logger.info(f"   Mejor fitness:    {stats['best_fitness']:.6f}")
            logger.info(f"   Fitness promedio: {stats['avg_fitness']:.6f}")
            logger.info(f"   Peor fitness:     {stats['worst_fitness']:.6f}")
            logger.info(f"   Desv. estándar:   {stats['std_fitness']:.6f}")
            logger.info(f"\n🏆 Mejor individuo global:")
            logger.info(f"   Fitness: {self.best_chromosome.fitness:.6f}")
            logger.info(f"   Genes: {self.best_chromosome.genes}")
        
        logger.info("\n" + "=" * 80)
        logger.info("🎉 ALGORITMO GENÉTICO - COMPLETADO")
        logger.info("=" * 80)
        logger.info(f"\n🏆 MEJOR MODELO ENCONTRADO:")
        logger.info(f"   Fitness: {self.best_chromosome.fitness:.6f}")
        logger.info(f"   Hiperparámetros:")
        for param, value in self.best_chromosome.genes.items():
            logger.info(f"      {param}: {value}")
        logger.info("")
        
        return self.best_chromosome
    
    def _calculate_generation_stats(self, generation: int) -> Dict:
        """
        Calcular estadísticas de una generación
        
        Args:
            generation: Número de generación
            
        Returns:
            Dict con estadísticas
        """
        fitnesses = [c.fitness for c in self.population if c.fitness is not None]
        
        stats = {
            'generation': generation,
            'best_fitness': min(fitnesses),
            'avg_fitness': np.mean(fitnesses),
            'worst_fitness': max(fitnesses),
            'std_fitness': np.std(fitnesses),
            'best_genes': self.population[0].genes.copy()
        }
        
        return stats
    
    def get_best_chromosome(self) -> Chromosome:
        """Obtener mejor cromosoma encontrado"""
        return self.best_chromosome
    
    def get_generation_history(self) -> List[Dict]:
        """Obtener historial de generaciones"""
        return self.generation_stats
    
    def plot_evolution(self, save_path: Optional[str] = None):
        """
        Graficar evolución del fitness a través de generaciones
        
        Args:
            save_path: Ruta donde guardar gráfico (opcional)
        """
        try:
            import matplotlib.pyplot as plt
            
            generations = [s['generation'] for s in self.generation_stats]
            best_fitness = [s['best_fitness'] for s in self.generation_stats]
            avg_fitness = [s['avg_fitness'] for s in self.generation_stats]
            worst_fitness = [s['worst_fitness'] for s in self.generation_stats]
            
            plt.figure(figsize=(12, 6))
            
            plt.plot(generations, best_fitness, 'g-', label='Mejor', linewidth=2)
            plt.plot(generations, avg_fitness, 'b--', label='Promedio')
            plt.plot(generations, worst_fitness, 'r:', label='Peor')
            
            plt.xlabel('Generación')
            plt.ylabel('Fitness (menor es mejor)')
            plt.title('Evolución del Algoritmo Genético')
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
