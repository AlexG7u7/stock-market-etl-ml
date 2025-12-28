"""
Modelo de datos para precios históricos
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass
class PrecioHistorico:
    """
    Representa un precio histórico de un ticker
    Mapea a stage.precios_historicos
    """
    ticker_id: int
    fecha: date
    open: Optional[Decimal] = None
    high: Optional[Decimal] = None
    low: Optional[Decimal] = None
    close: Decimal = None
    volume: Optional[int] = None
    importe: Optional[Decimal] = None
    
    def __post_init__(self):
        """Validaciones básicas"""
        if self.close is None:
            raise ValueError("El precio de cierre (close) es obligatorio")
        
        # Convertir a Decimal si viene como float
        if self.open is not None and not isinstance(self.open, Decimal):
            self.open = Decimal(str(self.open))
        if self.high is not None and not isinstance(self.high, Decimal):
            self.high = Decimal(str(self.high))
        if self.low is not None and not isinstance(self.low, Decimal):
            self.low = Decimal(str(self.low))
        if self.close is not None and not isinstance(self.close, Decimal):
            self.close = Decimal(str(self.close))
        if self.importe is not None and not isinstance(self.importe, Decimal):
            self.importe = Decimal(str(self.importe))
    
    def to_dict(self):
        """Convierte a diccionario para inserción en BD"""
        return {
            'ticker_id': self.ticker_id,
            'fecha': self.fecha,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume,
            'importe': self.importe
        }
