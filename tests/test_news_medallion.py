from pathlib import Path
import json
import pandas as pd

from src.data.news_medallion import ingest, normalize, build_gold
from scripts.build_news_medallion import migrate


def article(**updates):
    return dict(title='Walmex reporta crecimiento', ticker='WALMEX',
                url='https://example.com/1', published_at='2026-10-20T10:00Z', **updates)


def test_captures_are_immutable_and_replay_is_idempotent(tmp_path):
    a = ingest('google_news', [article(), article()], root=tmp_path, fetched_at='2026-10-20T12:00Z')
    original = a.read_bytes()
    b = ingest('google_news', [article()], root=tmp_path, fetched_at='2026-10-20T13:00Z')
    assert a != b and a.read_bytes() == original
    normalize(a, root=tmp_path)
    silver = pd.read_parquet(tmp_path / 'silver/articles.parquet')
    assert len(silver) == 2  # One observation per capture, duplicates removed within each capture.
    assert silver.article_id.nunique() == 1
    gold = build_gold(root=tmp_path, as_of='2026-10-20T14:00Z')
    assert gold.iloc[0].n_articles == 1
    assert len(json.loads(gold.iloc[0].article_ids)) == 1
    assert set(json.loads(gold.iloc[0].batch_ids)) <= set(silver.batch_id)
    assert all((tmp_path / relative).exists() for relative in silver.bronze_path)


def test_cutoff_excludes_late_discovery_and_future_publication(tmp_path):
    ingest('gdelt', [article()], root=tmp_path, fetched_at='2026-10-22T12:00Z')
    assert build_gold(root=tmp_path, as_of='2026-10-21T12:00Z').empty
    assert len(build_gold(root=tmp_path, as_of='2026-10-22T13:00Z')) == 1
    ingest('gdelt', [dict(article(), url='https://example.com/future', published_at='2026-11-01T12:00Z')],
           root=tmp_path, fetched_at='2026-10-22T12:00Z')
    assert build_gold(root=tmp_path, as_of='2026-10-22T13:00Z').iloc[0].n_articles == 1


def test_trump_stays_thematic_without_tickers(tmp_path):
    ingest('trump', [{'titulo': 'Trump anuncia aranceles', 'texto': 'Trump anuncia aranceles',
                      'fecha': 'Tue, 20 Oct 2026 10:00:00 GMT', 'url': 'https://example.com/trump'}],
           root=tmp_path, fetched_at='2026-10-20T12:00Z')
    silver = pd.read_parquet(tmp_path / 'silver/articles.parquet')
    assert silver.iloc[0].ticker == '' and silver.iloc[0].topic == 'trump'
    assert silver.iloc[0].text_kind == 'headline'
    result = build_gold(root=tmp_path, as_of='2026-10-20T13:00Z')
    assert result.iloc[0].topic == 'trump' and result.iloc[0].n_articles == 1


def test_databursatil_does_not_invent_publication_dates(tmp_path):
    ingest('databursatil', {'noticias': [{'n': 'Walmex crece', 'f': 'https://example.com/w'}],
                           'cables': {'top': [{'t': 'Mercado general', 'f': 'https://example.com/m'}]}},
           tickers=['WALMEX'], root=tmp_path, fetched_at='2026-10-20T12:00Z')
    silver = pd.read_parquet(tmp_path / 'silver/articles.parquet')
    assert silver.published_at.isna().all()
    assert set(silver.ticker) == {'', 'WALMEX'}
    result = build_gold(root=tmp_path, as_of='2026-10-20T13:00Z')
    assert result.publication_date_missing.sum() == 2


def test_migration_preserves_legacy_files_and_can_repeat(tmp_path):
    csv = tmp_path / 'noticias_trump.csv'
    csv.write_text('titulo,fecha,url,fuente,texto\nTrump,,,Google News (Trump),Trump\n')
    before = csv.read_bytes()
    assert migrate(tmp_path) == ['noticias_trump.csv']
    assert migrate(tmp_path) == []
    assert csv.read_bytes() == before
    assert len(pd.read_parquet(tmp_path / 'silver/articles.parquet')) == 1


def test_rebuild_keeps_other_days_and_replaces_same_day(tmp_path):
    ingest('gdelt', [article()], root=tmp_path, fetched_at='2026-10-20T12:00Z')
    build_gold(root=tmp_path, as_of='2026-10-20T13:00Z')
    build_gold(root=tmp_path, as_of='2026-10-21T13:00Z')
    build_gold(root=tmp_path, as_of='2026-10-21T14:00Z')
    gold = pd.read_parquet(tmp_path / 'gold/daily_features.parquet')
    assert len(gold) == 2
    assert not gold.duplicated(['date', 'ticker', 'topic']).any()


def test_scraping_captures_before_deduplication(tmp_path, monkeypatch):
    import src.data.news_medallion as lake
    import src.ml.news as news
    original_ingest = lake.ingest
    monkeypatch.setattr(lake, 'ingest', lambda source, payload: original_ingest(source, payload, root=tmp_path))
    monkeypatch.delenv('ALPHA_VANTAGE_API_KEY', raising=False)
    item = news.Article('TEST', 'A headline', '', 'https://example.com/1', 0, 'yfinance')
    monkeypatch.setattr(news, 'fetch_yfinance', lambda *args: [item, item])
    monkeypatch.setattr(news, 'fetch_google_news_rss', lambda *args, **kwargs: [])
    assert len(news._scrape_articles('TEST', 'TEST')) == 1
    bronze = list((tmp_path / 'bronze').glob('*/*/*.json'))
    assert len(json.loads(bronze[0].read_text())['payload']) == 2
    assert len(pd.read_parquet(tmp_path / 'silver/articles.parquet')) == 1


def test_trump_ingestion_keeps_csv_and_populates_lake(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import scripts.ingesta_trump as trump
    import src.data.news_medallion as lake
    (tmp_path / 'data/news').mkdir(parents=True)
    original_ingest, original_build = lake.ingest, lake.build_gold
    root = tmp_path / 'data/news'
    monkeypatch.setattr(trump, 'ROOT', tmp_path)
    monkeypatch.setattr(trump.feedparser, 'parse', lambda _: SimpleNamespace(entries=[
        SimpleNamespace(title='Trump aranceles', published='Tue, 20 Oct 2026 10:00:00 GMT', link='https://example.com/trump')]))
    monkeypatch.setattr(lake, 'ingest', lambda source, payload, **kw: original_ingest(source, payload, root=root, **kw))
    monkeypatch.setattr(lake, 'build_gold', lambda: original_build(root=root))
    trump.buscar_noticias_trump()
    assert (root / 'noticias_trump.csv').exists()
    assert (root / 'silver/articles.parquet').exists()
    assert (root / 'gold/daily_features.parquet').exists()


def test_empty_gold_keeps_schema(tmp_path):
    from src.data.news_medallion import GOLD_COLUMNS
    result = build_gold(root=tmp_path, as_of='2026-10-20T12:00Z')
    stored = pd.read_parquet(tmp_path / 'gold/daily_features.parquet')
    assert list(result.columns) == list(stored.columns) == GOLD_COLUMNS
    assert json.loads((tmp_path / 'gold/latest.json').read_text()) == []
