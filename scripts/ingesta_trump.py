import feedparser
import pandas as pd
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def buscar_noticias_trump():
    print("🇺🇸 Iniciando ingesta de noticias de Donald Trump (Impacto en mercados)...")

    # DECISIÓN DE ARQUITECTURA:
    # Usamos Google News RSS con URLs parametrizadas en lugar de la API de X (Twitter).
    # Esto garantiza que el proceso sea 100% automatizable, sin costos de API y escalable.
    url_rss = "https://news.google.com/rss/search?q=Donald+Trump+aranceles+OR+mercados+OR+economia&hl=es-419&gl=MX&ceid=MX:es-419"

    # Parsear el feed RSS
    feed = feedparser.parse(url_rss)

    noticias = []
    for entry in feed.entries:
        noticias.append({
            "titulo": entry.title,
            "fecha": entry.published,
            "url": entry.link,
            "fuente": "Google News (Trump)",
            "texto": entry.title # Google News RSS no da el resumen completo, usamos el título como texto base
        })

    from src.data.news_medallion import ingest, build_gold
    ingest("trump", noticias, representation="rss_extract")

    if not noticias:
        print("No se encontraron noticias de Trump hoy.")
        return

    # Convertir a DataFrame de Pandas
    df = pd.DataFrame(noticias)

    # Crear la carpeta data/news si no existe (Cumpliendo con el guardado en local)
    (ROOT / "data/news").mkdir(parents=True, exist_ok=True)
    ruta_csv = ROOT / "data/news/noticias_trump.csv"

    # Guardar la tabla local
    df.to_csv(ruta_csv, index=False, encoding="utf-8")

    build_gold()

    print(f"¡Éxito! Se descargaron {len(df)} noticias de Trump.")
    print(f"Guardado en: {ruta_csv}")
    print("\nVista previa de los datos:")
    print(df.head(3))

if __name__ == "__main__":
    buscar_noticias_trump()
