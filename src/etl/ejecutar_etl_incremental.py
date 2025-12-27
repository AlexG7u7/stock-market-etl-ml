"""
Script para ejecutar ETL incremental basado en configuración
Lee la lista de tickers activos desde config/tickers_config.yml
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import logging
import argparse
import yaml

# Agregar el directorio raíz del proyecto al path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.etl.cargar_precios import cargar_precios

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def load_config():
    """Cargar configuración desde YAML"""
    config_path = project_root / 'config' / 'tickers_config.yml'
    
    if not config_path.exists():
        logger.error(f"❌ Archivo de configuración no encontrado: {config_path}")
        return None
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    logger.info(f"✅ Configuración cargada desde {config_path}")
    return config


def ejecutar_etl_incremental(config, fecha_inicio=None, fecha_fin=None):
    """
    Ejecutar ETL incremental para los tickers configurados
    
    Args:
        config: Configuración cargada desde YAML
        fecha_inicio: Fecha inicio opcional (override)
        fecha_fin: Fecha fin opcional (override)
    """
    tickers_activos = config.get('tickers_activos', [])
    
    if not tickers_activos:
        logger.warning("⚠️  No hay tickers activos configurados")
        return False
    
    # Determinar fechas
    if not fecha_fin:
        fecha_fin = datetime.now().strftime('%Y-%m-%d')
    
    if not fecha_inicio:
        lookback = config.get('incremental', {}).get('lookback_days', 1)
        fecha_inicio = (datetime.now() - timedelta(days=lookback)).strftime('%Y-%m-%d')
    
    logger.info(f"🚀 ETL Incremental - {len(tickers_activos)} tickers activos")
    logger.info(f"📅 Rango: {fecha_inicio} a {fecha_fin}")
    logger.info(f"📊 Tickers: {', '.join(tickers_activos)}")
    
    exitosos = 0
    fallidos = 0
    
    for idx, ticker in enumerate(tickers_activos, 1):
        logger.info(f"\n{'='*60}")
        logger.info(f"[{idx}/{len(tickers_activos)}] Procesando {ticker}")
        logger.info(f"{'='*60}")
        
        try:
            exito = cargar_precios(
                ticker=ticker,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                todos=False
            )
            
            if exito:
                exitosos += 1
                logger.info(f"✅ {ticker} completado")
            else:
                fallidos += 1
                logger.warning(f"⚠️  {ticker} sin datos")
                
        except Exception as e:
            fallidos += 1
            logger.error(f"❌ Error procesando {ticker}: {e}")
    
    # Resumen final
    logger.info(f"\n{'='*60}")
    logger.info("📊 RESUMEN FINAL")
    logger.info(f"{'='*60}")
    logger.info(f"Total tickers: {len(tickers_activos)}")
    logger.info(f"✅ Exitosos: {exitosos}")
    logger.info(f"❌ Fallidos: {fallidos}")
    logger.info(f"📅 Período: {fecha_inicio} a {fecha_fin}")
    logger.info(f"{'='*60}")
    
    return fallidos == 0


def main():
    """Punto de entrada principal"""
    parser = argparse.ArgumentParser(
        description='ETL Incremental basado en configuración'
    )
    parser.add_argument(
        '--fecha-inicio',
        type=str,
        help='Fecha inicial (YYYY-MM-DD). Si no se especifica, usa lookback_days de config'
    )
    parser.add_argument(
        '--fecha-fin',
        type=str,
        help='Fecha final (YYYY-MM-DD). Si no se especifica, usa hoy'
    )
    parser.add_argument(
        '--config',
        type=str,
        help='Ruta al archivo de configuración (opcional)'
    )
    
    args = parser.parse_args()
    
    # Cargar configuración
    config = load_config()
    if not config:
        logger.error("❌ No se pudo cargar la configuración")
        sys.exit(1)
    
    # Ejecutar ETL
    exito = ejecutar_etl_incremental(
        config,
        fecha_inicio=args.fecha_inicio,
        fecha_fin=args.fecha_fin
    )
    
    sys.exit(0 if exito else 1)


if __name__ == "__main__":
    main()
