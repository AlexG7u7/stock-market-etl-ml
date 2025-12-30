"""
Chromosome - Representa un individuo (conjunto de hiperparámetros)
"""
import random
import copy
from typing import Dict, Any, List
from loguru import logger


class Chromosome:
    """
    Representa un individuo en el Algoritmo Genético
    
    Un cromosoma es un conjunto completo de hiperparámetros para un modelo LSTM
    """
    
    def __init__(self, genes: Dict[str, Any], search_space: Dict[str, Any]):
        """
        Args:
            genes: Diccionario con valores de hiperparámetros
            search_space: Definición del espacio de búsqueda
        """
        self.genes = genes
        self.search_space = search_space
        self.fitness = None
        self.metrics = {}
    
    @classmethod
    def random(cls, search_space: Dict[str, Any]) -> 'Chromosome':
        """
        Crear cromosoma aleatorio dentro del espacio de búsqueda
        
        Args:
            search_space: Definición del espacio de búsqueda
            
        Returns:
            Nuevo cromosoma aleatorio
        """
        genes = {}
        
        for param_name, param_config in search_space.items():
            param_type = param_config.get('type')
            
            if param_type == 'int':
                min_val = param_config['min']
                max_val = param_config['max']
                genes[param_name] = random.randint(min_val, max_val)
            
            elif param_type == 'float':
                min_val = param_config['min']
                max_val = param_config['max']
                scale = param_config.get('scale', 'linear')
                
                if scale == 'log':
                    # Escala logarítmica
                    log_min = np.log10(min_val)
                    log_max = np.log10(max_val)
                    genes[param_name] = 10 ** random.uniform(log_min, log_max)
                else:
                    genes[param_name] = random.uniform(min_val, max_val)
            
            elif param_type == 'categorical':
                values = param_config['values']
                genes[param_name] = random.choice(values)
            
            else:
                raise ValueError(f"Tipo de parámetro desconocido: {param_type}")
        
        return cls(genes, search_space)
    
    def mutate(self, mutation_rate: float = 0.15) -> 'Chromosome':
        """
        Mutar genes aleatoriamente
        
        Args:
            mutation_rate: Probabilidad de mutar cada gen
            
        Returns:
            Cromosoma mutado (nuevo)
        """
        mutated_genes = copy.deepcopy(self.genes)
        
        for param_name, param_config in self.search_space.items():
            # Decidir si mutar este gen
            if random.random() < mutation_rate:
                param_type = param_config.get('type')
                
                if param_type == 'int':
                    min_val = param_config['min']
                    max_val = param_config['max']
                    mutated_genes[param_name] = random.randint(min_val, max_val)
                
                elif param_type == 'float':
                    min_val = param_config['min']
                    max_val = param_config['max']
                    step = param_config.get('step', 0.01)
                    
                    # Mutación gaussiana alrededor del valor actual
                    current = mutated_genes[param_name]
                    sigma = (max_val - min_val) * 0.1  # 10% del rango
                    mutated = random.gauss(current, sigma)
                    
                    # Clip al rango válido
                    mutated = max(min_val, min(max_val, mutated))
                    mutated_genes[param_name] = round(mutated / step) * step
                
                elif param_type == 'categorical':
                    values = param_config['values']
                    mutated_genes[param_name] = random.choice(values)
        
        return Chromosome(mutated_genes, self.search_space)
    
    @staticmethod
    def crossover(parent1: 'Chromosome', parent2: 'Chromosome') -> tuple:
        """
        Combinar dos padres para crear dos hijos
        
        Usa crossover de un punto o uniforme
        
        Args:
            parent1: Primer padre
            parent2: Segundo padre
            
        Returns:
            (child1, child2)
        """
        child1_genes = {}
        child2_genes = {}
        
        # Crossover uniforme: cada gen tiene 50% probabilidad de venir de cada padre
        for param_name in parent1.genes.keys():
            if random.random() < 0.5:
                child1_genes[param_name] = parent1.genes[param_name]
                child2_genes[param_name] = parent2.genes[param_name]
            else:
                child1_genes[param_name] = parent2.genes[param_name]
                child2_genes[param_name] = parent1.genes[param_name]
        
        child1 = Chromosome(child1_genes, parent1.search_space)
        child2 = Chromosome(child2_genes, parent2.search_space)
        
        return child1, child2
    
    def to_lstm_config(self):
        """
        Convertir genes a LSTMConfig
        
        Returns:
            Dict compatible con LSTMConfig
        """
        from src.ml.shared.models import LSTMConfig
        
        config_dict = copy.deepcopy(self.genes)
        
        # Convertir a tipos correctos si es necesario
        if 'num_layers' in config_dict:
            config_dict['num_layers'] = int(config_dict['num_layers'])
        if 'hidden_units' in config_dict:
            config_dict['hidden_units'] = int(config_dict['hidden_units'])
        if 'batch_size' in config_dict:
            config_dict['batch_size'] = int(config_dict['batch_size'])
        if 'epochs' in config_dict:
            config_dict['epochs'] = int(config_dict['epochs'])
        if 'sequence_length' in config_dict:
            config_dict['sequence_length'] = int(config_dict['sequence_length'])
        
        return LSTMConfig(**config_dict)
    
    def __repr__(self) -> str:
        genes_str = ', '.join([f"{k}={v}" for k, v in self.genes.items()])
        fitness_str = f", fitness={self.fitness:.4f}" if self.fitness else ""
        return f"Chromosome({genes_str}{fitness_str})"
    
    def __lt__(self, other: 'Chromosome') -> bool:
        """Para ordenar por fitness (menor es mejor)"""
        if self.fitness is None:
            return False
        if other.fitness is None:
            return True
        return self.fitness < other.fitness


# Import necesario para mutación gaussiana
import numpy as np
