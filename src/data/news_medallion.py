"""Local news lake: immutable captures, normalized observations and auditable features."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import fcntl
import json
import os
import re
import uuid

import pandas as pd

DEFAULT_ROOT = Path(__file__).resolve().parents[2] / 'data' / 'news'
SILVER_COLUMNS = ['article_id', 'batch_id', 'bronze_path', 'source', 'ticker',
                  'topic', 'title', 'text', 'text_kind', 'url', 'published_at',
                  'fetched_at', 'available_at', 'sentiment', 'relevance_score']
GOLD_COLUMNS = ['date', 'ticker', 'topic', 'as_of', 'window_days', 'scoring_method',
                'publication_date_missing', 'article_ids', 'batch_ids',
                'news_sent_score', 'news_count_7d', 'news_sent_delta', 'news_sent_vol',
                'news_relevance_avg', 'news_esg_score', 'n_articles', 'sources']


def utc(value=None):
    if value is None:
        return pd.Timestamp(datetime.now(timezone.utc))
    ts = pd.to_datetime(value, utc=True, errors='coerce')
    if pd.isna(ts):
        raise ValueError(f'Invalid timestamp: {value!r}')
    return ts


def timestamp(value):
    if value is None or value == '' or value == 0:
        return pd.NaT
    if isinstance(value, (int, float)):
        return pd.to_datetime(value, unit='s', utc=True, errors='coerce')
    return pd.to_datetime(value, utc=True, errors='coerce')


def atomic_frame(frame, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        frame.to_parquet(tmp, index=False)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


@contextmanager
def lock(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.medallion.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def capture(source, payload, *, root=DEFAULT_ROOT, fetched_at=None,
            representation='normalized_extract', origin=None):
    """Append a capture. Never put request headers, tokens or credential URLs here."""
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', source):
        raise ValueError('Invalid source name')
    root = Path(root)
    fetched = utc(fetched_at)
    batch = uuid.uuid4().hex
    relative = Path('bronze') / source / fetched.strftime('%Y-%m-%d') / (batch + '.json')
    envelope = dict(schema_version=1, batch_id=batch, source=source,
                    fetched_at=fetched.isoformat(), representation=representation,
                    origin=origin, payload=payload)
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as handle:
        json.dump(envelope, handle, ensure_ascii=False, default=str)
    return path


def _snapshot_records(payload, tickers):
    from src.ml.news_sources import get_entity_aliases
    records = list(payload.get('noticias') or [])
    for items in (payload.get('cables') or {}).values():
        if isinstance(items, list):
            records.extend(items)
    for raw in records:
        title = raw.get('n') or raw.get('t') or ''
        text = raw.get('c') or ''
        matches = [ticker for ticker in tickers if any(
            re.search(r'(?<!\w)' + re.escape(alias) + r'(?!\w)', title + ' ' + text, re.I)
            for alias in get_entity_aliases(ticker) if alias)]
        for ticker in matches or ['']:
            yield dict(title=title, summary=text, url=raw.get('f', ''), ticker=ticker,
                       topic='' if ticker else 'market', published_at=None)


def normalize(path, *, root=DEFAULT_ROOT, tickers=()):
    """Materialize one bronze batch into silver; safe to replay the same batch."""
    root, path = Path(root), Path(path)
    env = json.loads(path.read_text(encoding='utf-8'))
    payload = env['payload']
    if env['source'] == 'databursatil' and isinstance(payload, dict) and 'noticias' in payload:
        records = _snapshot_records(payload, tickers)
    else:
        records = payload if isinstance(payload, list) else payload.get('articles', [])
    rows = []
    for raw in records:
        title = str(raw.get('title') or raw.get('titulo') or '').strip()
        if not title:
            continue
        source = str(raw.get('source') or env['source'])
        url = str(raw.get('url') or '')
        identity = json.dumps([source, url or ' '.join(title.casefold().split())], ensure_ascii=False)
        published = timestamp(raw.get('published_at', raw.get('published_dt', raw.get('published_ts', raw.get('fecha')))))
        # DataBursátil's connector can synthesize timestamps; do not treat those as publication evidence.
        if source == 'databursatil':
            published = pd.NaT
        fetched = utc(env['fetched_at'])
        text = str(raw.get('summary') or raw.get('texto') or '')
        rows.append(dict(article_id=sha256(identity.encode()).hexdigest(),
                         batch_id=env['batch_id'], bronze_path=str(path.relative_to(root)),
                         source=source, ticker=str(raw.get('ticker') or ''),
                         topic=str(raw.get('topic') or ('trump' if env['source'] == 'trump' else '')),
                         title=title, text=text or title,
                         text_kind='headline' if not text or text == title else 'excerpt',
                         url=url, published_at=published, fetched_at=fetched,
                         available_at=max(published, fetched) if pd.notna(published) else fetched,
                         sentiment=float(raw.get('sentiment') or 0),
                         relevance_score=float(raw.get('relevance_score', 1.0))))
    frame = pd.DataFrame(rows, columns=SILVER_COLUMNS)
    for col in ['published_at', 'fetched_at', 'available_at']:
        frame[col] = pd.to_datetime(frame[col], utc=True)
    frame = frame.drop_duplicates(['article_id', 'ticker', 'topic', 'batch_id'])
    target = root / 'silver' / 'articles.parquet'
    with lock(root):
        old = pd.read_parquet(target) if target.exists() else frame.iloc[:0]
        combined = pd.concat([old[old.batch_id != env['batch_id']], frame], ignore_index=True)
        atomic_frame(combined, target)
    return frame


def ingest(source, payload, *, root=DEFAULT_ROOT, fetched_at=None,
           representation='normalized_extract', origin=None, tickers=()):
    path = capture(source, payload, root=root, fetched_at=fetched_at,
                   representation=representation, origin=origin)
    normalize(path, root=root, tickers=tickers)
    return path


def build_gold(*, root=DEFAULT_ROOT, as_of=None, days_back=7):
    """Compute ticker/topic features from evidence available at the cutoff."""
    from src.ml.news import Article, _compute_features_from_articles, _score_keywords
    if days_back < 1:
        raise ValueError('days_back must be positive')
    root = Path(root)
    cutoff = utc(as_of)
    with lock(root):
        path = root / 'silver' / 'articles.parquet'
        data = pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=SILVER_COLUMNS)
        if not data.empty:
            data = data[data.available_at <= cutoff].copy()
            data['event_at'] = data.published_at.fillna(data.fetched_at)
            data = data[(data.event_at <= cutoff) & (data.event_at >= cutoff - pd.Timedelta(days=days_back * 2))]
            data = data.sort_values('fetched_at').drop_duplicates(['article_id', 'ticker', 'topic'], keep='last')
        rows = []
        for (ticker, topic), group in data.groupby(['ticker', 'topic']):
            arts = [Article(ticker=ticker, title=r.title, summary=r.text, url=r.url,
                            published_ts=int(r.event_at.timestamp()), source=r.source,
                            sentiment=_score_keywords(r.title + ' ' + r.text),
                            relevance_score=r.relevance_score) for r in group.itertuples()]
            feat = _compute_features_from_articles(arts, days_back=days_back, as_of=cutoff.to_pydatetime())
            rows.append(dict(date=cutoff.normalize(), ticker=ticker, topic=topic,
                             as_of=cutoff, window_days=days_back, scoring_method='keywords',
                             publication_date_missing=int(group.published_at.isna().sum()),
                             article_ids=json.dumps(sorted(group.article_id.unique().tolist())),
                             batch_ids=json.dumps(sorted(group.batch_id.unique().tolist())), **feat))
        frame = pd.DataFrame(rows, columns=GOLD_COLUMNS)
        for col in ['date', 'as_of']:
            frame[col] = pd.to_datetime(frame[col], utc=True)
        target = root / 'gold' / 'daily_features.parquet'
        old = pd.read_parquet(target) if target.exists() else pd.DataFrame()
        # Replace this calculation date, including a now-empty result, without leaving stale rows.
        if not old.empty:
            old = old[old.date != cutoff.normalize()]
        combined = frame.copy() if old.empty else old.copy() if frame.empty else pd.concat([old, frame], ignore_index=True)
        atomic_frame(combined, target)
        latest = root / 'gold' / 'latest.json'
        tmp = latest.with_suffix('.json.tmp')
        tmp.write_text(frame.to_json(orient='records', date_format='iso', force_ascii=False), encoding='utf-8')
        os.replace(tmp, latest)
    return frame
