"""
LSTM Model Configuration
"""
from dataclasses import dataclass, asdict
from typing import Optional, List
import json


@dataclass
class LSTMConfig:
    """
    Configuración completa para modelo LSTM
    
    Todos los hiperparámetros parametrizables
    """
    # Arquitectura
    num_layers: int = 2
    hidden_units: int = 128
    dropout_rate: float = 0.2
    dense_activation: str = 'linear'
    task_type: str = 'regression'  # 'regression' | 'classification'
    
    # Training
    learning_rate: float = 0.001
    batch_size: int = 32
    epochs: int = 200
    optimizer: str = 'adam'
    
    # Data
    sequence_length: int = 60
    prediction_horizon: int = 5
    validation_split: float = 0.2
    
    # Regularization
    l1_reg: float = 0.0
    l2_reg: float = 0.01
    recurrent_dropout: float = 0.0
    
    # Early Stopping
    early_stopping_patience: int = 20
    early_stopping_min_delta: float = 0.0001
    restore_best_weights: bool = True
    
    # Features
    feature_columns: Optional[List[str]] = None
    target_column: str = 'close'
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_dict(cls, config_dict: dict) -> 'LSTMConfig':
        """Create from dictionary"""
        return cls(**config_dict)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'LSTMConfig':
        """Create from JSON string"""
        return cls.from_dict(json.loads(json_str))
    
    def validate(self):
        """Validate configuration"""
        errors = []
        
        if self.num_layers < 1:
            errors.append("num_layers debe ser >= 1")
        
        if self.hidden_units < 1:
            errors.append("hidden_units debe ser >= 1")
        
        if not 0 <= self.dropout_rate < 1:
            errors.append("dropout_rate debe estar en [0, 1)")
        
        if self.learning_rate <= 0:
            errors.append("learning_rate debe ser > 0")
        
        if self.batch_size < 1:
            errors.append("batch_size debe ser >= 1")
        
        if self.epochs < 1:
            errors.append("epochs debe ser >= 1")
        
        if self.sequence_length < 1:
            errors.append("sequence_length debe ser >= 1")
        
        if self.prediction_horizon < 1:
            errors.append("prediction_horizon debe ser >= 1")
        
        if not 0 < self.validation_split < 1:
            errors.append("validation_split debe estar en (0, 1)")

        if self.task_type not in ('regression', 'classification'):
            errors.append("task_type debe ser 'regression' o 'classification'")
        
        if errors:
            raise ValueError(f"Errores de validación: {', '.join(errors)}")
        
        return True
