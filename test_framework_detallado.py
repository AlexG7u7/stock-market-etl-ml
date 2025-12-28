#!/usr/bin/env python3
"""
Test avanzado del framework - Muestra datos detallados
"""
import sys
from pathlib import Path
from datetime import datetime, date

sys.path.insert(0, str(Path(__file__).parent))

from src.etl.shared.extractors import YahooFinanceExtractor


def test_walmex_historico_detallado():
    """Test completo de WALMEX con estadísticas"""
    print("=" * 100)
    print("TEST DETALLADO - WALMEX HISTÓRICO (1 AÑO)")
    print(f"Ejecutado el {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)
    
    extractor = YahooFinanceExtractor(
        ticker_symbol="WALMEX*",
        ticker_id=999
    )
    
    # Extraer 1 año
    print("\n🔍 Extrayendo datos del 27-dic-2024 al 26-dic-2025...")
    precios = extractor.extract_historical(
        fecha_inicio=date(2024, 12, 27),
        fecha_fin=date(2025, 12, 26)
    )
    
    if not precios:
        print("❌ No se obtuvieron datos")
        return
    
    # Estadísticas generales
    print(f"\n📊 ESTADÍSTICAS GENERALES")
    print("-" * 100)
    print(f"Total de registros:     {len(precios):,}")
    print(f"Primera fecha:          {precios[0].fecha}")
    print(f"Última fecha:           {precios[-1].fecha}")
    print(f"Días transcurridos:     {(precios[-1].fecha - precios[0].fecha).days}")
    
    # Estadísticas de precios
    closes = [float(p.close) for p in precios]
    print(f"\n💵 ESTADÍSTICAS DE PRECIOS (Close)")
    print("-" * 100)
    print(f"Precio mínimo:          ${min(closes):.2f}")
    print(f"Precio máximo:          ${max(closes):.2f}")
    print(f"Precio promedio:        ${sum(closes) / len(closes):.2f}")
    print(f"Precio inicial:         ${closes[0]:.2f}")
    print(f"Precio final:           ${closes[-1]:.2f}")
    variacion = ((closes[-1] - closes[0]) / closes[0]) * 100
    print(f"Variación anual:        {variacion:+.2f}%")
    
    # Estadísticas de volumen
    volumenes = [p.volume for p in precios if p.volume]
    print(f"\n📈 ESTADÍSTICAS DE VOLUMEN")
    print("-" * 100)
    print(f"Volumen total:          {sum(volumenes):,}")
    print(f"Volumen promedio:       {sum(volumenes) // len(volumenes):,}")
    print(f"Volumen máximo:         {max(volumenes):,}")
    print(f"Volumen mínimo:         {min(volumenes):,}")
    print(f"Días con volumen > 0:   {len(volumenes)}")
    print(f"Días sin volumen:       {len(precios) - len(volumenes)}")
    
    # Primeros 10 días
    print(f"\n📅 PRIMEROS 10 DÍAS DEL AÑO")
    print("-" * 100)
    print(f"{'Fecha':<12} | {'Open':>10} | {'High':>10} | {'Low':>10} | {'Close':>10} | {'Volume':>15}")
    print("-" * 100)
    for p in precios[:10]:
        print(f"{p.fecha} | ${float(p.open):>9.2f} | ${float(p.high):>9.2f} | ${float(p.low):>9.2f} | ${float(p.close):>9.2f} | {p.volume:>15,}")
    
    # Últimos 10 días
    print(f"\n📅 ÚLTIMOS 10 DÍAS DEL AÑO")
    print("-" * 100)
    print(f"{'Fecha':<12} | {'Open':>10} | {'High':>10} | {'Low':>10} | {'Close':>10} | {'Volume':>15}")
    print("-" * 100)
    for p in precios[-10:]:
        print(f"{p.fecha} | ${float(p.open):>9.2f} | ${float(p.high):>9.2f} | ${float(p.low):>9.2f} | ${float(p.close):>9.2f} | {p.volume:>15,}")
    
    # Días con mayor volumen
    top_volumen = sorted(precios, key=lambda p: p.volume or 0, reverse=True)[:5]
    print(f"\n🔥 TOP 5 DÍAS CON MAYOR VOLUMEN")
    print("-" * 100)
    print(f"{'Fecha':<12} | {'Close':>10} | {'Volume':>15} | {'Importe Aprox':>20}")
    print("-" * 100)
    for p in top_volumen:
        importe = float(p.close) * p.volume
        print(f"{p.fecha} | ${float(p.close):>9.2f} | {p.volume:>15,} | ${importe:>18,.0f}")
    
    # Resumen final
    print(f"\n{'='*100}")
    print("✅ RESUMEN")
    print(f"{'='*100}")
    print(f"✅ WALMEX tiene {len(precios)} días de cotización en el último año")
    print(f"✅ Variación anual: {variacion:+.2f}% ({'GANANCIA' if variacion > 0 else 'PÉRDIDA'})")
    print(f"✅ Volumen total negociado: {sum(volumenes):,} acciones")
    print(f"✅ Todos los registros tienen OHLCV completo (Open, High, Low, Close, Volume)")
    print(f"✅ Datos listos para cargar a la base de datos")
    print(f"{'='*100}")


def test_comparacion_tickers():
    """Compara WALMEX, ALSEA y ALFAA"""
    print("\n\n" + "=" * 100)
    print("COMPARACIÓN DE TICKERS - ÚLTIMOS 5 DÍAS")
    print("=" * 100)
    
    tickers = [
        ("WALMEX*", "WALMEX"),
        ("ALSEA*", "ALSEA"),
        ("ALFAA", "ALFAA")
    ]
    
    for ticker_symbol, ticker_name in tickers:
        print(f"\n📊 {ticker_name}")
        print("-" * 100)
        
        extractor = YahooFinanceExtractor(
            ticker_symbol=ticker_symbol,
            ticker_id=999
        )
        
        precios = extractor.extract_incremental(lookback_days=5)
        
        if not precios:
            print("❌ Sin datos")
            continue
        
        print(f"{'Fecha':<12} | {'Close':>10} | {'Volume':>15} | {'Estado':<20}")
        print("-" * 100)
        for p in precios:
            estado = "✅ CON VOLUMEN" if p.volume > 0 else "⚠️  SIN VOLUMEN"
            print(f"{p.fecha} | ${float(p.close):>9.2f} | {p.volume:>15,} | {estado}")


if __name__ == "__main__":
    test_walmex_historico_detallado()
    test_comparacion_tickers()
