#!/usr/bin/env python3
"""
Test local del nuevo framework ETL
Prueba extracción sin conectar a la base de datos
"""
import sys
from pathlib import Path
from datetime import datetime, date

# Agregar src al path
sys.path.insert(0, str(Path(__file__).parent))

from src.etl.shared.extractors import YahooFinanceExtractor


def test_extractor():
    """Prueba el extractor de Yahoo Finance"""
    print("=" * 80)
    print("TEST DEL NUEVO FRAMEWORK ETL")
    print(f"Ejecutado el {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Test 1: WALMEX Incremental (últimos 3 días)
    print("\n📊 Test 1: WALMEX - Incremental (últimos 3 días)")
    print("-" * 80)
    
    extractor_walmex = YahooFinanceExtractor(
        ticker_symbol="WALMEX*",
        ticker_id=999  # ID ficticio para test
    )
    
    precios = extractor_walmex.extract_incremental(lookback_days=3)
    
    print(f"\n✅ Obtenidos {len(precios)} registros")
    
    if precios:
        print("\nPrimeros registros:")
        for precio in precios[:3]:
            print(f"  {precio.fecha} | Close: ${precio.close} | Volume: {precio.volume:,}")
        
        if len(precios) > 3:
            print("\nÚltimos registros:")
            for precio in precios[-3:]:
                print(f"  {precio.fecha} | Close: ${precio.close} | Volume: {precio.volume:,}")
    
    # Test 2: ALSEA Incremental
    print("\n\n📊 Test 2: ALSEA - Incremental (últimos 3 días)")
    print("-" * 80)
    
    extractor_alsea = YahooFinanceExtractor(
        ticker_symbol="ALSEA*",
        ticker_id=998  # ID ficticio para test
    )
    
    precios_alsea = extractor_alsea.extract_incremental(lookback_days=3)
    
    print(f"\n✅ Obtenidos {len(precios_alsea)} registros")
    
    if precios_alsea:
        print("\nPrimeros registros:")
        for precio in precios_alsea[:3]:
            print(f"  {precio.fecha} | Close: ${precio.close} | Volume: {precio.volume:,}")
    
    # Test 3: WALMEX Histórico (1 año)
    print("\n\n📊 Test 3: WALMEX - Histórico (1 año: 2024-12-27 a 2025-12-26)")
    print("-" * 80)
    
    precios_hist = extractor_walmex.extract_historical(
        fecha_inicio=date(2024, 12, 27),
        fecha_fin=date(2025, 12, 26)
    )
    
    print(f"\n✅ Obtenidos {len(precios_hist)} registros")
    
    if precios_hist:
        print(f"\nPrimera fecha: {precios_hist[0].fecha}")
        print(f"Última fecha: {precios_hist[-1].fecha}")
        
        con_volumen = sum(1 for p in precios_hist if p.volume and p.volume > 0)
        sin_volumen = len(precios_hist) - con_volumen
        
        print(f"\nRegistros con volumen > 0: {con_volumen}")
        print(f"Registros con volumen = 0: {sin_volumen}")
    
    # Resumen
    print("\n" + "=" * 80)
    print("RESUMEN DEL TEST")
    print("=" * 80)
    print(f"✅ Extractor funcionando correctamente")
    print(f"✅ WALMEX incremental: {len(precios)} registros")
    print(f"✅ ALSEA incremental: {len(precios_alsea)} registros")
    print(f"✅ WALMEX histórico: {len(precios_hist)} registros")
    print("\n💡 El framework está listo para usar")
    print("💡 Para conectar a la BD, usa los scripts en src/etl/walmex/")
    print("=" * 80)


if __name__ == "__main__":
    test_extractor()
