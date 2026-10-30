import pandas as pd
import os
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# Importamos el motor del profesor
from src.ml.news import (
    Article,
    _score_keywords,
    apply_dedup_and_decay,
    _scrape_articles,
    _compute_features_from_articles
)

def integrar_noticias():
    print("🧠 Iniciando integración de Sentimiento y TF-IDF...")
    
    # 1. Cargar noticias de Trump desde tu CSV
    ruta_csv = "data/news/noticias_trump.csv"
    if not os.path.exists(ruta_csv):
        print("❌ No se encontró noticias_trump.csv")
        return
        
    df_trump = pd.read_csv(ruta_csv)
    
    # 2. Convertir el CSV a objetos Article (lo que espera el profesor)
    articulos_trump = []
    for _, row in df_trump.iterrows():
        try:
            # Convertir la fecha del RSS a timestamp
            dt = parsedate_to_datetime(row['fecha'])
            ts = int(dt.timestamp())
        except:
            ts = int(datetime.now(timezone.utc).timestamp())
            
        articulos_trump.append(Article(
            ticker="WALMEX", # Asignamos las noticias de Trump a WALMEX para este ejemplo
            title=str(row['titulo']),
            summary=str(row['texto']),
            url=str(row['url']),
            published_ts=ts,
            source="Trump_RSS"
        ))
        
    print(f"📥 Artículos de Trump cargados: {len(articulos_trump)}")

    # 3. Descargar las noticias normales de WALMEX usando el scraper del profe
    print("🕷️ Descargando noticias generales de WALMEX (esto puede tardar)...")
    articulos_walmex = _scrape_articles("WALMEX", "WALMEX.MX")
    print(f"📥 Artículos generales de WALMEX: {len(articulos_walmex)}")
    
    # 4. Juntar ambas listas
    todos_los_articulos = articulos_walmex + articulos_trump
    print(f"📚 Total de artículos a procesar: {len(todos_los_articulos)}")
    
    # 5. Calcular Sentimiento (usando la función del profe)
    for art in todos_los_articulos:
        # Aplicamos la función de keywords del profe
        art.sentiment = _score_keywords(art.text())
        
    # 6. Aplicar Deduplicación (TF-IDF) y Decaimiento Temporal
    print("🧹 Aplicando Deduplicación (TF-IDF) y Decaimiento Temporal...")
    apply_dedup_and_decay(todos_los_articulos)
    
    # 7. Calcular las Features finales (Capa Golden)
    features = _compute_features_from_articles(todos_los_articulos)
    
    print("\n✅ ¡Integración Exitosa! Resultados de la Capa Golden para WALMEX:")
    print(f"Sentimiento final: {features['news_sent_score']}")
    print(f"Total de artículos procesados: {features['n_articles']}")
    print(f"Fuentes utilizadas: {features['sources']}")
    
    # Guardar el resultado para tu Pull Request
    import json
    os.makedirs("data/golden", exist_ok=True)
    with open("data/golden/walmex_integrado.json", "w", encoding="utf-8") as f:
        json.dump(features, f, indent=4, ensure_ascii=False)
    print("📁 Guardado en: data/golden/walmex_integrado.json")

if __name__ == "__main__":
    integrar_noticias()