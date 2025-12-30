"""
Train/Test splitter - Split temporal sin data leakage
"""
import numpy as np
import pandas as pd
from typing import Tuple
from loguru import logger


class TemporalSplitter:
    """
    Split temporal de datos para series temporales
    
    Importante: NUNCA mezclar datos de entrenamiento y test
    El split debe respetar el orden cronológico
    
    Estrategias:
    - Fixed split: Train/Val/Test fijos
    - Walk-forward: Ventana deslizante (para backtesting)
    """
    
    def __init__(
        self,
        test_size: int = 90,      # Días para test
        val_size: int = 60        # Días para validación
    ):
        """
        Args:
            test_size: Número de días para test set (final)
            val_size: Número de días para validation set (antes de test)
        """
        self.test_size = test_size
        self.val_size = val_size
    
    def split(
        self, 
        data: pd.DataFrame
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Split fijo: Train / Validation / Test
        
        Args:
            data: DataFrame con índice DatetimeIndex
            
        Returns:
            (train_df, val_df, test_df)
        """
        if not isinstance(data.index, pd.DatetimeIndex):
            raise ValueError("DataFrame debe tener índice DatetimeIndex")
        
        total_len = len(data)
        
        # Índices de corte
        test_start_idx = total_len - self.test_size
        val_start_idx = test_start_idx - self.val_size
        
        if val_start_idx < 0:
            raise ValueError(
                f"Datos insuficientes: {total_len} registros, "
                f"necesitamos al menos {self.test_size + self.val_size}"
            )
        
        # Split
        train_df = data.iloc[:val_start_idx].copy()
        val_df = data.iloc[val_start_idx:test_start_idx].copy()
        test_df = data.iloc[test_start_idx:].copy()
        
        logger.info("📊 Split temporal:")
        logger.info(f"   Train: {len(train_df)} registros ({train_df.index[0]} a {train_df.index[-1]})")
        logger.info(f"   Val:   {len(val_df)} registros ({val_df.index[0]} a {val_df.index[-1]})")
        logger.info(f"   Test:  {len(test_df)} registros ({test_df.index[0]} a {test_df.index[-1]})")
        logger.info(f"   Total: {total_len} registros")
        
        return train_df, val_df, test_df
    
    def split_arrays(
        self,
        X: np.ndarray,
        y: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Split de arrays numpy (después de crear secuencias)
        
        Args:
            X: Array de secuencias (samples, sequence_length, features)
            y: Array de targets (samples,)
            
        Returns:
            (X_train, X_val, X_test, y_train, y_val, y_test)
        """
        total_len = len(X)
        
        # Índices de corte
        test_start_idx = total_len - self.test_size
        val_start_idx = test_start_idx - self.val_size
        
        if val_start_idx < 0:
            raise ValueError(
                f"Secuencias insuficientes: {total_len}, "
                f"necesitamos al menos {self.test_size + self.val_size}"
            )
        
        # Split
        X_train = X[:val_start_idx]
        X_val = X[val_start_idx:test_start_idx]
        X_test = X[test_start_idx:]
        
        y_train = y[:val_start_idx]
        y_val = y[val_start_idx:test_start_idx]
        y_test = y[test_start_idx:]
        
        logger.info("📊 Split de secuencias:")
        logger.info(f"   X_train: {X_train.shape}, y_train: {y_train.shape}")
        logger.info(f"   X_val:   {X_val.shape}, y_val: {y_val.shape}")
        logger.info(f"   X_test:  {X_test.shape}, y_test: {y_test.shape}")
        
        return X_train, X_val, X_test, y_train, y_val, y_test
    
    def walk_forward_split(
        self,
        data: pd.DataFrame,
        initial_train_days: int = 365,
        test_window_days: int = 30,
        step_days: int = 5
    ) -> list:
        """
        Walk-forward split para backtesting
        
        Genera múltiples splits donde el entrenamiento se expande
        y el test es una ventana deslizante
        
        Args:
            data: DataFrame con índice DatetimeIndex
            initial_train_days: Días para primer entrenamiento
            test_window_days: Días para cada ventana de test
            step_days: Días entre cada ventana
            
        Returns:
            Lista de dicts con: {'train': df, 'test': df, 'fold': int}
        """
        if not isinstance(data.index, pd.DatetimeIndex):
            raise ValueError("DataFrame debe tener índice DatetimeIndex")
        
        splits = []
        total_len = len(data)
        
        # Índice inicial de test
        test_start_idx = initial_train_days
        fold = 1
        
        while test_start_idx + test_window_days <= total_len:
            test_end_idx = test_start_idx + test_window_days
            
            # Train: desde inicio hasta inicio de test
            train_df = data.iloc[:test_start_idx].copy()
            
            # Test: ventana de test_window_days
            test_df = data.iloc[test_start_idx:test_end_idx].copy()
            
            splits.append({
                'fold': fold,
                'train': train_df,
                'test': test_df,
                'train_start': train_df.index[0],
                'train_end': train_df.index[-1],
                'test_start': test_df.index[0],
                'test_end': test_df.index[-1]
            })
            
            # Avanzar ventana
            test_start_idx += step_days
            fold += 1
        
        logger.info(f"🔄 Walk-forward: {len(splits)} folds generados")
        for split in splits:
            logger.info(
                f"   Fold {split['fold']}: "
                f"Train={len(split['train'])} ({split['train_start']} a {split['train_end']}), "
                f"Test={len(split['test'])} ({split['test_start']} a {split['test_end']})"
            )
        
        return splits
    
    def validate_no_leakage(
        self,
        train_dates: pd.DatetimeIndex,
        test_dates: pd.DatetimeIndex
    ):
        """
        Validar que no hay data leakage (train siempre antes que test)
        
        Args:
            train_dates: Índice de fechas de entrenamiento
            test_dates: Índice de fechas de test
            
        Raises:
            ValueError si hay leakage
        """
        if train_dates.max() >= test_dates.min():
            raise ValueError(
                f"❌ DATA LEAKAGE DETECTADO: "
                f"Train max ({train_dates.max()}) >= Test min ({test_dates.min()})"
            )
        
        logger.success("✅ Sin data leakage: Train termina antes de Test")
