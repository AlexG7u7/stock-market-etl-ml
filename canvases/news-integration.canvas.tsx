import { useState } from "react";
import {
  Stack, Row, Grid, H1, H2, H3, Text, Card, CardHeader, CardBody,
  Pill, Stat, Callout, Divider, Table, BarChart, useHostTheme, Code,
} from "cursor/canvas";

// ─── Datos ────────────────────────────────────────────────────────────────────

const CURRENT_FEATURES = [
  { group: "Osciladores",      n: 7,  examples: "RSI, Stoch %K, Williams %R, CCI, MFI, BB%" },
  { group: "Precio / Estructura", n: 6, examples: "vs SMA20/50, pos 52w, racha bajista" },
  { group: "Momentum",         n: 4,  examples: "ret 5d/10d/20d, pendiente SMA20" },
  { group: "Volumen",          n: 3,  examples: "vol_ratio_20, OBV slope, vol_down_up" },
  { group: "Volatilidad",      n: 5,  examples: "ATR%, BB width, HV ratio" },
  { group: "Macro",            n: 7,  examples: "USD/MXN, NAFTRAC, WTI, SP500 (definidos, conectados)" },
];

const TOP_IV_FEATURES = [
  { feature: "williams_r",     iv: 0.022, strength: "débil" },
  { feature: "stoch_k",        iv: 0.019, strength: "débil" },
  { feature: "ret_10d",        iv: 0.017, strength: "débil" },
  { feature: "bb_pct",         iv: 0.016, strength: "débil" },
  { feature: "price_vs_sma20", iv: 0.015, strength: "débil" },
  { feature: "rsi_14",         iv: 0.013, strength: "débil" },
];

const NEWS_SOURCES = [
  {
    name: "yfinance .news",
    type: "Gratuito",
    coverage: "~50 artículos recientes",
    history: "< 30 días",
    lang: "EN/ES",
    effort: "1 hora",
    notes: "Ya lo usas. JSON con headline + summary. Ideal para Tier 1.",
  },
  {
    name: "Google News RSS",
    type: "Gratuito",
    coverage: "Por ticker / keyword",
    history: "< 7 días",
    lang: "EN/ES",
    effort: "2 horas",
    notes: "Feed XML sin auth. Muy fresco, buena cobertura de BMV.",
  },
  {
    name: "GDELT Project",
    type: "Gratuito",
    coverage: "Global, desde 2015",
    history: "Histórico completo",
    lang: "Multi",
    effort: "3 días",
    notes: "Permite backfill de los 252d de training. Clave para WoE.",
  },
  {
    name: "NewsAPI",
    type: "Gratis (100/día)",
    coverage: "Histórico 1 mes",
    history: "1 mes (gratis)",
    lang: "EN/ES",
    effort: "4 horas",
    notes: "Simple REST API. Tier gratuito suficiente para prototyping.",
  },
  {
    name: "Alpha Vantage News",
    type: "$50/mes",
    coverage: "Por ticker/sector",
    history: "Completo",
    lang: "EN",
    effort: "4 horas",
    notes: "Sentimiento pre-calculado + relevance score. Llave en mano.",
  },
  {
    name: "El Financiero / Expansión RSS",
    type: "Gratuito",
    coverage: "BMV completa",
    history: "< 14 días",
    lang: "ES",
    effort: "2 horas",
    notes: "Noticias en español de empresas mexicanas. Complementa yfinance.",
  },
];

const NEW_FEATURES = [
  {
    col: "news_sent_score",
    range: "−1 a +1",
    method: "FinBERT / pysentimiento",
    woe: "Sí",
    tier: 2,
    desc: "Sentimiento promedio de noticias de los últimos 5 días hábiles. El predictor más potente.",
  },
  {
    col: "news_count_7d",
    range: "0 – 50+",
    method: "log(1 + n_artículos)",
    woe: "Sí",
    tier: 1,
    desc: "Volumen de cobertura. Spike inusual de noticias = evento corporativo.",
  },
  {
    col: "news_sent_delta",
    range: "−2 a +2",
    method: "sent_score[t] − sent_score[t−5d]",
    woe: "Sí",
    tier: 2,
    desc: "Cambio de tono. Giro negativo → venta; giro positivo → compra.",
  },
  {
    col: "news_sent_vol",
    range: "0 – 1",
    method: "std(sent_scores en 7d)",
    woe: "Sí",
    tier: 2,
    desc: "Desacuerdo entre artículos. Alta volatilidad de sentimiento = incertidumbre.",
  },
  {
    col: "earnings_days",
    range: "−60 a +60",
    method: "Calendario BMV / Yahoo",
    woe: "Sí",
    tier: 3,
    desc: "Días hasta/desde resultados trimestrales. Pre-earnings drift es conocido.",
  },
  {
    col: "sector_sent_score",
    range: "−1 a +1",
    method: "Promedio tickers del mismo sector",
    woe: "Sí",
    tier: 3,
    desc: "Efecto spillover sectorial. Noticias de BIMBOA afectan a GRUMAB.",
  },
];

const TIERS = [
  {
    tier: 1,
    name: "Quick Win",
    effort: "1 semana",
    auc_from: 0.534,
    auc_to: 0.545,
    auc_label: "0.534 → ~0.545",
    features: ["news_count_7d", "news_tone_kw (keyword-based)"],
    sources: ["yfinance .news", "El Financiero RSS"],
    model: "yf.Ticker.news + keyword scoring (subida/caída/beneficio/pérdida)",
    files: [
      "src/ml/features.py → add_news_features()",
      "scripts/generate_signals.py → llamar add_news_features()",
    ],
    risk: "Historial limitado (<30d). WoE necesita binning en datos históricos — usar features en raw sin WoE o buscar datos adicionales.",
  },
  {
    tier: 2,
    name: "FinBERT Sentiment",
    effort: "3 semanas",
    auc_from: 0.545,
    auc_to: 0.565,
    auc_label: "~0.545 → ~0.565",
    features: ["news_sent_score", "news_count_7d", "news_sent_delta", "news_sent_vol"],
    sources: ["yfinance .news", "NewsAPI", "Google News RSS"],
    model: "ProsusAI/finbert (EN) + pysentimiento (ES). Inferencia en GPU/CPU.",
    files: [
      "src/ml/news.py → nuevo módulo NLP",
      "scripts/fetch_news.py → nuevo script de descarga",
      "src/ml/features.py → NEWS_FEATURE_COLS + add_news_features()",
      "scripts/generate_signals.py → pipeline completo",
    ],
    risk: "Backfill de 252d de training es el cuello de botella. GDELT o NewsAPI histórico necesario para evitar data leakage.",
  },
  {
    tier: 3,
    name: "Full NLP + Earnings",
    effort: "6–8 semanas",
    auc_from: 0.565,
    auc_to: 0.600,
    auc_label: "~0.565 → ~0.600+",
    features: ["earnings_days", "sector_sent_score", "news_anomaly", "real-time alerts"],
    sources: ["GDELT histórico", "Alpha Vantage", "Calendario BMV"],
    model: "Ensemble: WoE+LR (técnico) + Logit sentimiento. También: alertas en tiempo real en monitor_intraday.py.",
    files: [
      "src/ml/news.py → scraper + FinBERT + sector aggregation",
      "src/ml/risk_engine.py → sentiment_override()",
      "scripts/monitor_intraday.py → news polling cada 15min",
      "scripts/generate_signals.py → ensemble scoring",
    ],
    risk: "Complejidad operacional alta. Requiere pipeline de datos separado. Priorizar Tier 2 antes de escalar.",
  },
];

const auBefore = [0.534];
const auAfter  = [0.545, 0.565, 0.600];

const PIPELINE_STEPS = [
  { step: "1. fetch_news.py", what: "Descarga noticias T−1 por ticker", file: "scripts/fetch_news.py (nuevo)" },
  { step: "2. add_news_features()", what: "NLP → sent_score, count, delta", file: "src/ml/features.py (agregar)" },
  { step: "3. merge en generate_signals.py", what: "Join noticias + OHLCV por ticker", file: "scripts/generate_signals.py (modificar)" },
  { step: "4. WoE binning", what: "NEWS_FEATURE_COLS en compute_all_woe()", file: "src/ml/woe.py (sin cambios)" },
  { step: "5. LogReg predict", what: "Incluye news WoE features", file: "src/ml/… (sin cambios)" },
  { step: "6. Risk Engine", what: "Filtro adicional: sent_score < −0.3 → skip", file: "src/ml/risk_engine.py (opcional)" },
];

// ─── Component ────────────────────────────────────────────────────────────────

function TierCard({ t }: { t: typeof TIERS[0] }) {
  const theme = useHostTheme();
  const border = t.tier === 2
    ? `1px solid ${theme.colors.border.accent}`
    : `1px solid ${theme.colors.border.default}`;
  return (
    <Card style={{ flex: 1, minWidth: 280, border }}>
      <CardHeader>
        <Row justify="between" align="center">
          <Row gap={8} align="center">
            <Text weight="bold" size="large">Tier {t.tier} — {t.name}</Text>
            {t.tier === 2 && <Pill size="sm" tone="accent">Recomendado</Pill>}
          </Row>
          <Text tone="secondary" size="small">{t.effort}</Text>
        </Row>
      </CardHeader>
      <CardBody>
        <Stack gap={12}>
          <Grid columns={2} gap={8}>
            <Stat value={t.auc_label} label="AUC esperado" tone="success" />
            <Stat value={t.features.length.toString()} label="Features nuevas" />
          </Grid>
          <Divider />
          <Stack gap={4}>
            <Text size="small" weight="semibold">Fuentes</Text>
            {t.sources.map(s => (
              <Row key={s} gap={6} align="center">
                <Text size="small" tone="secondary">·</Text>
                <Text size="small">{s}</Text>
              </Row>
            ))}
          </Stack>
          <Stack gap={4}>
            <Text size="small" weight="semibold">Modelo</Text>
            <Text size="small" tone="secondary">{t.model}</Text>
          </Stack>
          <Stack gap={4}>
            <Text size="small" weight="semibold">Archivos a modificar</Text>
            {t.files.map(f => (
              <Text key={f} size="small" tone="secondary">· {f}</Text>
            ))}
          </Stack>
          <Callout tone={t.tier === 1 ? "info" : t.tier === 2 ? "warning" : "danger"} title="Riesgo principal">
            <Text size="small">{t.risk}</Text>
          </Callout>
        </Stack>
      </CardBody>
    </Card>
  );
}

export default function NewsIntegration() {
  const [tab, setTab] = useState<"diagnostico" | "fuentes" | "features" | "arquitectura" | "roadmap">("diagnostico");

  return (
    <Stack gap={22} style={{ padding: 24, maxWidth: 1100 }}>

      {/* Header */}
      <Stack gap={4}>
        <Row justify="between" align="center">
          <H1>Mejora del Modelo BMV con Noticias</H1>
          <Pill size="sm">AUC actual: 0.534</Pill>
        </Row>
        <Text tone="secondary" size="small">
          Análisis de integración de señales de texto/NLP al pipeline WoE + LogisticRegression · BMV 19 tickers
        </Text>
      </Stack>

      <Grid columns={4} gap={12}>
        <Stat value="0.534" label="AUC actual (LogReg)" />
        <Stat value="32" label="Features actuales (técnicas)" />
        <Stat value="0" label="Features de noticias" tone="danger" />
        <Stat value="~0.60" label="AUC objetivo (Tier 3)" tone="success" />
      </Grid>

      <Divider />

      <Row gap={8} wrap>
        <Pill active={tab==="diagnostico"}   onClick={() => setTab("diagnostico")}>Diagnóstico</Pill>
        <Pill active={tab==="fuentes"}       onClick={() => setTab("fuentes")}>Fuentes de datos</Pill>
        <Pill active={tab==="features"}      onClick={() => setTab("features")}>Features & WoE</Pill>
        <Pill active={tab==="arquitectura"}  onClick={() => setTab("arquitectura")}>Arquitectura</Pill>
        <Pill active={tab==="roadmap"}       onClick={() => setTab("roadmap")}>Roadmap 3 tiers</Pill>
      </Row>

      {/* ── TAB: Diagnóstico ─────────────────────────────────────────────────── */}
      {tab === "diagnostico" && (
        <Stack gap={18}>
          <Stack gap={4}>
            <H2>¿Por qué el modelo está en AUC 0.534?</H2>
            <Text tone="secondary" size="small">
              El modelo usa exclusivamente features técnicas. El mercado mexicano tiene alta sensibilidad a eventos de
              noticias (política fiscal, resultados trimestrales, tipo de cambio USD/MXN). Esas señales no están en el OHLCV.
            </Text>
          </Stack>

          <Grid columns={2} gap={20}>
            <Stack gap={10}>
              <H3>Features actuales por grupo</H3>
              <Table
                headers={["Grupo", "N", "Ejemplos"]}
                rows={CURRENT_FEATURES.map(f => [
                  f.group,
                  f.n.toString(),
                  <Text size="small" tone="secondary" as="span">{f.examples}</Text>,
                ])}
                columnAlign={["left", "center", "left"]}
                striped
              />
            </Stack>

            <Stack gap={10}>
              <H3>Top 6 features por IV (WoE analysis)</H3>
              <Table
                headers={["Feature", "IV", "Fuerza"]}
                rows={TOP_IV_FEATURES.map(f => [
                  <Code as="span">{f.feature}</Code>,
                  f.iv.toFixed(3),
                  <Text size="small" tone="secondary" as="span">{f.strength}</Text>,
                ])}
                columnAlign={["left", "right", "center"]}
                striped
              />
              <Text size="small" tone="secondary">
                Todos los IV son &lt; 0.02 (umbral "débil"). La información en los precios ya está
                capturada por el mercado — necesitamos señales adelantadas.
              </Text>
            </Stack>
          </Grid>

          <Callout tone="warning" title="El gap de alpha">
            <Stack gap={6}>
              <Text size="small">
                <Text weight="semibold" as="span">Macro features definidas pero sin conectar:</Text> {" "}
                USD/MXN, NAFTRAC, WTI y SP500 están en <Code as="span">features.py</Code> pero{" "}
                <Code as="span">generate_signals.py</Code> no llama a{" "}
                <Code as="span">add_macro_features()</Code>. Primer fix inmediato.
              </Text>
              <Text size="small">
                <Text weight="semibold" as="span">Noticias ausentes:</Text> {" "}
                Earnings sorpresas, cambios regulatorios, noticias de competidores, política monetaria de Banxico —
                todos afectan el precio de apertura del lunes pero no están en ningún feature actual.
              </Text>
              <Text size="small">
                <Text weight="semibold" as="span">Señal idiosincrática del ticker:</Text> {" "}
                <Code as="span">rel_str5</Code> (ticker vs NAFTRAC) captura algo, pero no discrimina si la
                divergencia es ruido o hay un catalizador real de noticias.
              </Text>
            </Stack>
          </Callout>

          <Stack gap={6}>
            <H3>Fix inmediato: conectar macro features (sin noticias)</H3>
            <Text size="small" tone="secondary">
              Antes de integrar noticias, este cambio de 10 minutos puede mejorar el AUC ligeramente:
            </Text>
            <Card>
              <CardBody>
                <Code>
{`# scripts/generate_signals.py — agregar después de compute_features():
macro = store.get("USDMXN=X")   # ya descarga yfinance
naftrac = store.get("NAFTRACISHRS.MX")
wti = store.get("CL=F")
sp500 = store.get("^GSPC")

for ticker in BMV_TICKERS:
    feat_df = compute_features(df_ticker)
    feat_df = add_macro_features(feat_df, macro, naftrac, wti, sp500)
    # ... continuar pipeline`}
                </Code>
              </CardBody>
            </Card>
          </Stack>
        </Stack>
      )}

      {/* ── TAB: Fuentes ─────────────────────────────────────────────────────── */}
      {tab === "fuentes" && (
        <Stack gap={18}>
          <Stack gap={4}>
            <H2>Fuentes de noticias disponibles</H2>
            <Text tone="secondary" size="small">
              El mayor reto no es el modelo NLP, sino obtener <Text weight="semibold" as="span">252 días históricos</Text> de
              noticias para entrenar el WoE. Prioriza fuentes con historial suficiente.
            </Text>
          </Stack>

          <Table
            headers={["Fuente", "Tipo", "Cobertura histórica", "Idioma", "Esfuerzo impl.", "Notas"]}
            rows={NEWS_SOURCES.map(s => [
              <Text weight="semibold" size="small" as="span">{s.name}</Text>,
              <Pill size="sm" tone={s.type === "Gratuito" ? "success" : s.type.startsWith("Gratis") ? "warning" : "danger"}>
                {s.type}
              </Pill>,
              s.history,
              s.lang,
              s.effort,
              <Text size="small" tone="secondary" as="span">{s.notes}</Text>,
            ])}
            columnAlign={["left","center","center","center","center","left"]}
            striped
          />

          <Grid columns={2} gap={20}>
            <Callout tone="success" title="Ruta recomendada para historial">
              <Stack gap={4}>
                <Text size="small">
                  <Text weight="semibold" as="span">GDELT Project</Text> (gdeltproject.org) tiene noticias desde 2015
                  con cobertura global y es gratuito. Permite construir el dataset histórico de 252d necesario para WoE.
                </Text>
                <Text size="small">
                  API: <Code as="span">https://api.gdeltproject.org/api/v2/doc/doc?query=ALSEA+BMV&format=json</Code>
                </Text>
                <Text size="small" tone="secondary">
                  Cuidado: los artículos están principalmente en inglés. Usar FinBERT (EN) como modelo principal.
                </Text>
              </Stack>
            </Callout>

            <Callout tone="info" title="Para producción (señales del lunes)">
              <Stack gap={4}>
                <Text size="small">
                  Combinar <Text weight="semibold" as="span">yfinance .news</Text> +{" "}
                  <Text weight="semibold" as="span">Google News RSS</Text> en el script{" "}
                  <Code as="span">fetch_news.py</Code> que corre el viernes/sábado.
                </Text>
                <Text size="small">
                  Window: noticias de los últimos 5 días hábiles (L–V).
                  Guardar en <Code as="span">data/news/TICKER_YYYY-MM-DD.json</Code>.
                </Text>
              </Stack>
            </Callout>
          </Grid>

          <Stack gap={6}>
            <H3>Snippet: descarga con yfinance (ya disponible)</H3>
            <Card>
              <CardBody>
                <Code>
{`import yfinance as yf

def fetch_yf_news(ticker: str, max_items: int = 20) -> list[dict]:
    """Descarga noticias recientes de Yahoo Finance."""
    t = yf.Ticker(ticker + ".MX")
    items = t.news or []
    return [
        {
            "title":     item.get("title", ""),
            "summary":   item.get("summary", ""),
            "published": item.get("providerPublishTime", 0),
            "source":    item.get("publisher", ""),
        }
        for item in items[:max_items]
    ]

# Uso: fetch_yf_news("ALSEA")  →  lista de dicts con title+summary`}
                </Code>
              </CardBody>
            </Card>
          </Stack>
        </Stack>
      )}

      {/* ── TAB: Features & WoE ──────────────────────────────────────────────── */}
      {tab === "features" && (
        <Stack gap={18}>
          <Stack gap={4}>
            <H2>Nuevas features y compatibilidad con WoE</H2>
            <Text tone="secondary" size="small">
              Todas las features de noticias son numéricas continuas → compatibles con el binning WoE actual.
              Solo hay que agregarlas a <Code as="span">NEWS_FEATURE_COLS</Code> en <Code as="span">features.py</Code>.
            </Text>
          </Stack>

          <Table
            headers={["Feature", "Rango", "Método NLP", "WoE-able", "Tier", "Descripción"]}
            rows={NEW_FEATURES.map(f => [
              <Code as="span">{f.col}</Code>,
              f.range,
              <Text size="small" tone="secondary" as="span">{f.method}</Text>,
              <Pill size="sm" tone="success">{f.woe}</Pill>,
              <Pill size="sm" tone={f.tier === 1 ? "success" : f.tier === 2 ? "warning" : "danger"}>
                T{f.tier}
              </Pill>,
              <Text size="small" tone="secondary" as="span">{f.desc}</Text>,
            ])}
            columnAlign={["left","center","left","center","center","left"]}
            striped
          />

          <Grid columns={2} gap={20}>
            <Stack gap={8}>
              <H3>Modelo NLP por idioma</H3>
              <Card>
                <CardBody>
                  <Stack gap={10}>
                    <Stack gap={3}>
                      <Text weight="semibold" size="small">Inglés (mayoría del corpus)</Text>
                      <Code>
{`# pip install transformers torch
from transformers import pipeline

finbert = pipeline(
    "text-classification",
    model="ProsusAI/finbert",
    return_all_scores=True,
)

def score_en(text: str) -> float:
    """Retorna score entre -1 (neg) y +1 (pos)."""
    scores = finbert(text[:512])[0]
    d = {s["label"]: s["score"] for s in scores}
    return d["positive"] - d["negative"]`}
                      </Code>
                    </Stack>
                    <Divider />
                    <Stack gap={3}>
                      <Text weight="semibold" size="small">Español (El Financiero, Expansión)</Text>
                      <Code>
{`# pip install pysentimiento
from pysentimiento import create_analyzer

analyzer = create_analyzer(
    task="sentiment",
    lang="es",
)

def score_es(text: str) -> float:
    result = analyzer.predict(text)
    # NEG=-1, NEU=0, POS=1
    mapping = {"NEG": -1, "NEU": 0, "POS": 1}
    return mapping.get(result.output, 0)`}
                      </Code>
                    </Stack>
                  </Stack>
                </CardBody>
              </Card>
            </Stack>

            <Stack gap={8}>
              <H3>add_news_features() — estructura</H3>
              <Card>
                <CardBody>
                  <Code>
{`# src/ml/features.py — agregar al final

NEWS_FEATURE_COLS = [
    "news_sent_score",   # promedio sent 5d
    "news_count_7d",     # log(1 + n_artículos)
    "news_sent_delta",   # cambio vs semana anterior
    "news_sent_vol",     # std de sentimientos 7d
]

def add_news_features(
    features_df: pd.DataFrame,
    news_df: pd.DataFrame,     # cols: date, ticker, sent_score
) -> pd.DataFrame:
    """
    Hace join de features técnicas con news features.
    news_df debe estar calculado ANTES del training window
    para evitar look-ahead bias.
    """
    rolled = (
        news_df.groupby("ticker")
        .apply(lambda g: g.set_index("date")["sent_score"]
               .rolling("5D").agg(["mean","count","std"]))
        .rename(columns={
            "mean":  "news_sent_score",
            "count": "news_count_7d",
            "std":   "news_sent_vol",
        })
    )
    rolled["news_sent_delta"] = (
        rolled["news_sent_score"]
        - rolled["news_sent_score"].shift(5)
    )
    rolled["news_count_7d"] = np.log1p(rolled["news_count_7d"])
    return features_df.join(rolled, how="left").fillna(0)`}
                  </Code>
                </CardBody>
              </Card>
            </Stack>
          </Grid>

          <Callout tone="info" title="Regla anti-leakage crítica">
            <Text size="small">
              Las noticias deben tener timestamp anterior a la apertura del mercado del día de predicción.
              En <Code as="span">generate_signals.py</Code>, filtrar <Code as="span">news_df</Code> por{" "}
              <Code as="span">published_ts &lt; today 08:30 CT</Code> antes de calcular features.
              El modelo predice sobre la apertura del <Text weight="semibold" as="span">próximo lunes</Text>,
              por lo que noticias del viernes/sábado son válidas.
            </Text>
          </Callout>
        </Stack>
      )}

      {/* ── TAB: Arquitectura ────────────────────────────────────────────────── */}
      {tab === "arquitectura" && (
        <Stack gap={18}>
          <Stack gap={4}>
            <H2>Pipeline con noticias integrado</H2>
            <Text tone="secondary" size="small">
              El pipeline agrega un paso de descarga + NLP antes del training/inference actual. El resto del
              pipeline (WoE, LogReg, Risk Engine) no cambia.
            </Text>
          </Stack>

          <Table
            headers={["Paso", "Qué hace", "Archivo"]}
            rows={PIPELINE_STEPS.map(s => [
              <Text weight="semibold" size="small" as="span">{s.step}</Text>,
              s.what,
              <Code as="span">{s.file}</Code>,
            ])}
            columnAlign={["left","left","left"]}
            striped
          />

          <Grid columns={2} gap={20}>
            <Stack gap={8}>
              <H3>Flujo de datos actualizado</H3>
              <Card>
                <CardBody>
                  <Stack gap={6}>
                    {[
                      ["yfinance OHLCV", "19 tickers BMV + 4 macro"],
                      ["yfinance .news + RSS", "noticias T−5d por ticker"],
                      ["compute_features()", "32 features técnicas actuales"],
                      ["add_macro_features()", "7 features macro (conectar)"],
                      ["add_news_features()", "4 features NLP (nuevo)"],
                      ["compute_all_woe()", "43 features → WoE transform"],
                      ["LogisticRegression", "predict p_up por ticker"],
                      ["risk_engine", "Kelly + ATR + sent_override"],
                      ["signals_today.json", "señales finales"],
                    ].map(([step, desc], i) => (
                      <Row key={i} gap={10} align="center">
                        <Text size="small" tone="secondary" style={{ minWidth: 20 }}>{i + 1}.</Text>
                        <Stack gap={1} style={{ flex: 1 }}>
                          <Text size="small" weight="semibold">{step}</Text>
                          <Text size="small" tone="secondary">{desc}</Text>
                        </Stack>
                      </Row>
                    ))}
                  </Stack>
                </CardBody>
              </Card>
            </Stack>

            <Stack gap={8}>
              <H3>Filtro de sentimiento en Risk Engine</H3>
              <Card>
                <CardBody>
                  <Stack gap={6}>
                    <Text size="small" tone="secondary">
                      Opcional: usar el sentimiento como filtro binario sobre señales técnicas,
                      sin necesidad de re-entrenar el modelo:
                    </Text>
                    <Code>
{`# src/ml/risk_engine.py — agregar a build_signal()

def build_signal(
    ticker, p_up, features_row, price_data,
    news_sent_score: float = 0.0,   # nuevo
) -> Signal | None:

    # Filtro hard: noticias muy negativas cancelan señal
    if news_sent_score < -0.4:
        return None  # "Verificar news negativo antes de entrar"

    # Reducción de sizing si sentimiento negativo suave
    sent_multiplier = 1.0
    if news_sent_score < -0.1:
        sent_multiplier = 0.5   # mitad del Kelly

    # ... resto del pipeline sin cambios
    size = kelly_fraction(...) * sent_multiplier
    return Signal(...)`}
                    </Code>
                    <Text size="small" tone="secondary">
                      Esto replica manualmente la nota en la señal ALSEA:
                      "Verificar que no haya news negativo antes de entrar" — pero de forma automática.
                    </Text>
                  </Stack>
                </CardBody>
              </Card>

              <Card>
                <CardBody>
                  <Stack gap={4}>
                    <Text weight="semibold" size="small">Monitor intraday (Tier 3)</Text>
                    <Text size="small" tone="secondary">
                      <Code as="span">monitor_intraday.py</Code> ya corre polling cada 2 min.
                      Agregar polling de noticias cada 15 min con alerta si{" "}
                      <Code as="span">news_sent_score &lt; −0.5</Code> → notificación "CERRAR POSICIÓN / revisar news".
                    </Text>
                  </Stack>
                </CardBody>
              </Card>
            </Stack>
          </Grid>
        </Stack>
      )}

      {/* ── TAB: Roadmap ─────────────────────────────────────────────────────── */}
      {tab === "roadmap" && (
        <Stack gap={18}>
          <Stack gap={4}>
            <H2>Roadmap de implementación — 3 tiers</H2>
            <Text tone="secondary" size="small">
              Cada tier es independiente y entregable. El AUC estimado es conservador; el impacto real depende
              de la calidad del historial de noticias disponible para entrenamiento.
            </Text>
          </Stack>

          <Row gap={16} align="start" wrap>
            {TIERS.map(t => <TierCard key={t.tier} t={t} />)}
          </Row>

          <Stack gap={6}>
            <H3>AUC esperado por tier</H3>
            <BarChart
              categories={["Actual (técnico)", "Tier 1 (keyword)", "Tier 2 (FinBERT)", "Tier 3 (full)"]}
              series={[{ name: "AUC", data: [0.534, 0.545, 0.565, 0.600] }]}
              height={180}
              horizontal={false}
              valueSuffix=""
            />
            <Text size="small" tone="secondary">
              Fuente: benchmarks literatura (NLP + equity prediction BMV/Latam). Rango conservador.
              Con datos de calidad AUC 0.62–0.65 es alcanzable para stocks individuales con alta cobertura mediática.
            </Text>
          </Stack>

          <Callout tone="success" title="Primer paso concreto esta semana">
            <Stack gap={4}>
              <Text size="small">
                <Text weight="semibold" as="span">1.</Text> Conectar macro features (10 min) — editar{" "}
                <Code as="span">generate_signals.py</Code> para llamar <Code as="span">add_macro_features()</Code>.
              </Text>
              <Text size="small">
                <Text weight="semibold" as="span">2.</Text> Crear <Code as="span">scripts/fetch_news.py</Code> usando{" "}
                <Code as="span">yf.Ticker.news</Code> + keyword scoring básico (COMPRA/VENTA keywords en español e inglés).
              </Text>
              <Text size="small">
                <Text weight="semibold" as="span">3.</Text> Agregar <Code as="span">news_count_7d</Code> y{" "}
                <Code as="span">news_tone_kw</Code> como features en <Code as="span">features.py</Code> y correr{" "}
                <Code as="span">run_model.py</Code> para verificar si el AUC mejora en walk-forward.
              </Text>
              <Text size="small">
                <Text weight="semibold" as="span">4.</Text> Solo si Tier 1 muestra mejora en AUC → invertir en GDELT backfill + FinBERT (Tier 2).
              </Text>
            </Stack>
          </Callout>

          <Callout tone="warning" title="El mayor riesgo: look-ahead bias en noticias">
            <Text size="small">
              En el walk-forward validation, las noticias del fold de test NO deben estar disponibles en el training.
              La fecha de publicación de cada artículo debe ser estrictamente anterior a la fecha de predicción.
              Validar esto antes de reportar cualquier mejora de AUC — es la fuente más común de overfitting en NLP+finance.
            </Text>
          </Callout>
        </Stack>
      )}

    </Stack>
  );
}
