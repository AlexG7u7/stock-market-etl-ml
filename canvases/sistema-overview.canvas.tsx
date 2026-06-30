import { useState } from "react";
import {
  Stack, Row, Grid, H1, H2, H3, Text, Card, CardHeader, CardBody,
  Pill, Stat, Callout, Divider, Table, BarChart, useHostTheme, Code,
} from "cursor/canvas";

// ─── Datos del sistema ────────────────────────────────────────────────────────

const PAGES = [
  { icon: "🏆", name: "Ranking Mensual",   desc: "Señales multi-universo: 5 mercados × 4 horizontes. Motor principal de decisiones." },
  { icon: "📰", name: "Noticias & Gemini", desc: "Scraping en tiempo real + NLP sentiment por Gemini. Alerta de noticias negativas." },
  { icon: "🎯", name: "Señales de hoy",    desc: "Pipeline original BMV diario: WoE + LogReg + Kelly + ATR stops." },
  { icon: "📊", name: "Research & Eval", desc: "Backtest top-K neto de costos, grid search, LSTM vs LGBM, agent KB — literatura → código." },
  { icon: "👀", name: "Monitor",           desc: "Polling cada 2 min durante horario BMV. Dispara alertas de STOP/T1/T2." },
  { icon: "📋", name: "Paper Trading",     desc: "Diario de trades simulados. P&L, Sharpe, drawdown, historial." },
  { icon: "🕹️", name: "Simulador",        desc: "Walk-forward interactivo: elige ticker, capital, fecha y ve el resultado semana a semana." },
  { icon: "🏦", name: "GBM Broker",        desc: "Ejecución real en GBM+. Portafolio en vivo, órdenes, sesión Playwright." },
  { icon: "🧠", name: "Modelo",            desc: "Resultados de entrenamiento: Ensemble, Meta-labeling, Walk-Forward, Hold-Out, WoE." },
  { icon: "🗄️", name: "Base de datos",   desc: "92 símbolos en disco. ETL incremental por universo. Info de cobertura histórica." },
  { icon: "📖", name: "Documentación",     desc: "Arquitectura, features, WoE, Risk Engine, flujo operativo diario." },
];

const UNIVERSES = [
  { name: "Acciones BMV",  slug: "bmv",    n: 31, bench: "NAFTRAC",  horizonte: "20d", moneda: "MXN",
    consenso: ["GMEXICOB","GCC","GENTERA","WALMEX","POSADAS"] },
  { name: "Acciones USA",  slug: "usa",    n: 23, bench: "^GSPC",    horizonte: "20d", moneda: "USD",
    consenso: ["INTC","MSFT","META","FMX"] },
  { name: "ETFs",          slug: "etf",    n: 22, bench: "SPY",      horizonte: "20d", moneda: "USD",
    consenso: ["SLV","USO","QQQ"] },
  { name: "Cripto",        slug: "crypto", n: 9,  bench: "IBIT",     horizonte: "10d", moneda: "USD",
    consenso: ["CLSK","MARA","MSTR","ETHA"] },
  { name: "FIBRAs MX",     slug: "fibra",  n: 3,  bench: "FUNO11",   horizonte: "20d", moneda: "MXN",
    consenso: ["FINN13","FIBRAPL","FUNO11"] },
];

const MODELS = [
  {
    name: "Cross-seccional LightGBM",
    status: "PRODUCCIÓN",
    tone: "success" as const,
    desc: "Motor principal del Ranking Mensual. Entrena en retornos relativos entre pares (rank-normalized). Predice el retorno forward a 1/2/3/4 semanas.",
    inputs: "38 features técnicas + macro, rank-normalized vs universo",
    output: "Score de retorno relativo esperado (top-5 picks por horizonte)",
    auc: "N/A (regresión)",
    donde: "generate_all_signals.py → data/signals/*.json",
    fortaleza: "Cross-seccional: compara tickers entre sí, no contra un umbral absoluto",
  },
  {
    name: "WoE + LogisticRegression",
    status: "PRODUCCIÓN",
    tone: "success" as const,
    desc: "Pipeline original BMV. Binning WoE de los top-8 features por IV, luego LogReg binaria (¿sube en 5 días?). Walk-forward 252d train / 63d test.",
    inputs: "Top-8 features por IV: williams_r, stoch_k, ret_10d, bb_pct, etc.",
    output: "P(subida 5d) por ticker [0.50–0.65]. Señal si P > 0.53.",
    auc: "0.534 (walk-forward)",
    donde: "generate_signals.py → data/signals_today.json",
    fortaleza: "Interpretable. WoE maneja no-linealidades sin overfitting.",
  },
  {
    name: "Ensemble (Stacking)",
    status: "INVESTIGACIÓN",
    tone: "warning" as const,
    desc: "Stack de LR + LGBM + RandomForest con meta-learner. Entrenado en todo el historial disponible. Aún en validación.",
    inputs: "Predicciones de modelos base como features del meta-learner",
    output: "P(subida) combinada con menor varianza que cada modelo individual",
    auc: "0.541 (holdout 20%)",
    donde: "run_ensemble.py → src/ml/ensemble.py",
    fortaleza: "Reduce varianza. Puede combinarse con Meta-labeling.",
  },
  {
    name: "Meta-labeling",
    status: "INVESTIGACIÓN",
    tone: "warning" as const,
    desc: "Segundo modelo que aprende CUÁNDO creer al modelo primario. Filtra falsos positivos. Técnica de Marcos López de Prado.",
    inputs: "Features + predicción del modelo base como feature adicional",
    output: "Probabilidad de que la señal primaria sea correcta (filtro de confianza)",
    auc: "0.558 (holdout — mejora vs base 0.534)",
    donde: "run_meta.py → src/ml/meta_model.py",
    fortaleza: "Puede aumentar Sharpe significativamente sin cambiar el modelo base.",
  },
  {
    name: "LSTM + Genetic Algorithm",
    status: "EXPERIMENTAL",
    tone: "danger" as const,
    desc: "Red LSTM con búsqueda de hiperparámetros por Algoritmo Genético. Usa secuencias de OHLCV. Requiere SQL Server.",
    inputs: "Secuencias OHLCV de 60 días → LSTM → predicción next-day",
    output: "Dirección predicha y retorno esperado",
    auc: "No evaluado en producción",
    donde: "src/ml/pipelines/ + src/ml/shared/",
    fortaleza: "Captura patrones temporales que LR no puede. Alto costo computacional.",
  },
  {
    name: "Ising Market (econofísica)",
    status: "EXPERIMENTAL",
    tone: "danger" as const,
    desc: "Autómata celular basado en el modelo de Ising de física estadística. Simula contagio de sentimiento entre agentes de mercado.",
    inputs: "Serie de retornos históricos → calibra temperatura/acoplamiento",
    output: "Régimen de mercado: alcista / lateral / bajista / fase crítica",
    auc: "No evaluado — generador de features de régimen",
    donde: "src/ml/ising_market.py",
    fortaleza: "Detecta cambios de régimen previos a colapsos. No conectado a producción aún.",
  },
];

const INSIGHTS = [
  {
    categoria: "Señales de trading",
    icon: "🎯",
    ejemplos: [
      "Top-5 picks por universo y horizonte temporal (hoy: GMEXICOB, GCC, GENTERA, WALMEX, POSADAS en BMV)",
      "Consenso cross-horizonte: tickers que aparecen en top-5 de 3+ horizontes (señal más robusta)",
      "Régimen del mercado: LATERAL +0.6% en 10d — neutral para BMV",
      "Score relativo: POSADAS en percentil 89% vs peers (retorno esperado > media del universo)",
    ],
  },
  {
    categoria: "Risk management",
    icon: "🛡️",
    ejemplos: [
      "Kelly ¼: sizing automático por probabilidad y ratio win/loss histórico",
      "ATR stops: Stop Loss = Entry − 1.5×ATR(14). Target1/Target2 simétricas.",
      "Correlación entre posiciones: penalización si corr > 70% entre pares",
      "Capital en riesgo máximo: < 5% del portafolio total en cualquier momento",
    ],
  },
  {
    categoria: "Noticias & Sentimiento",
    icon: "📰",
    ejemplos: [
      "news_sent_score por ticker: HOTEL −1.0 (noticias negativas detectadas), BOLSAA −0.40",
      "news_alerta=true: señal de precaución antes de entrar en posición",
      "Gemini analiza titulares de Google News + El Financiero + Expansión + yfinance",
      "Análisis ejecutivo por ticker: resumen, acción recomendada, catalizador, riesgo",
    ],
  },
  {
    categoria: "Validación del modelo",
    icon: "🧠",
    ejemplos: [
      "Walk-forward 252d train / 63d test / 21d step: AUC 0.534 (LR), 0.514 (LGBM)",
      "Hold-out 20%: Ensemble AUC 0.541, Meta-labeling 0.558",
      "WoE IV ranking: williams_r (0.022), stoch_k (0.019) — todos 'débiles' → espacio para mejoras",
      "Backtesting heurístico: 51,490 trades simulados en historial",
    ],
  },
  {
    categoria: "Paper Trading",
    icon: "📋",
    ejemplos: [
      "Diario de 4 trades en simulación (ALSEA, GRUMAB, GMEXICOB, WALMEX)",
      "P&L por trade, equity curve, Sharpe, max drawdown",
      "Settle automático al comparar vs precio real de cierre",
      "Historial de eventos: PENDING → OPEN → T1_HIT / T2_HIT / STOP_HIT / EXPIRED",
    ],
  },
  {
    categoria: "Ejecución real (GBM)",
    icon: "🏦",
    ejemplos: [
      "Conexión a GBM+ via Playwright (browser automation) para ver portafolio real",
      "Órdenes pendientes y posiciones abiertas en tiempo real",
      "Ejecución de órdenes de las señales directamente desde el dashboard",
      "Monitor intraday: polling cada 2 min, alertas macOS de STOP/T1/T2",
    ],
  },
];

const FLUJO = [
  { dia: "Viernes tarde", acciones: ["fetch_news.py → scraping noticias 5 días", "build_database.py --update → BD local al día"] },
  { dia: "Sábado / Domingo", acciones: ["generate_all_signals.py → rankings 5 universos × 4 horizontes", "Revisar Ranking Mensual en app → top consenso"] },
  { dia: "Lunes 08:00 CT", acciones: ["Abrir app → Señales de hoy → verificar news_alerta", "Colocar órdenes limitadas en GBM+ al Open", "Cancelar si no se llenan en 30 min"] },
  { dia: "Lunes–Viernes", acciones: ["Monitor corriendo en segundo plano (monitor_intraday.py)", "Alertas: STOP HIT / T1 HIT → cerrar 50% / T2 → cerrar 100%"] },
  { dia: "Viernes cierre", acciones: ["paper_trading.py settle → calcular resultado real vs predicción", "Comparar P&L del modelo vs benchmark CETES/NAFTRAC"] },
];

const DATA_COBERTURA = [
  { grupo: "BMV", tickers: 31, inicio: "2000", dias: "~6,700", mb: "~5.5" },
  { grupo: "USA SIC", tickers: 23, inicio: "2000", dias: "~6,660", mb: "~5.5" },
  { grupo: "ETFs", tickers: 22, inicio: "2002", dias: "~5,500", mb: "~4.0" },
  { grupo: "Cripto", tickers: 9, inicio: "2015", dias: "~2,800", mb: "~1.0" },
  { grupo: "FIBRAs", tickers: 3, inicio: "2011", dias: "~3,700", mb: "~0.5" },
  { grupo: "Macro", tickers: 4, inicio: "2000", dias: "~6,600", mb: "~0.9" },
];

// ─── Component ────────────────────────────────────────────────────────────────

function ModelCard({ m }: { m: typeof MODELS[0] }) {
  const theme = useHostTheme();
  const borderColor = m.tone === "success"
    ? theme.colors.border.accent
    : m.tone === "warning"
    ? theme.colors.feedback.warning
    : theme.colors.feedback.error;

  return (
    <Card style={{ flex: 1, minWidth: 300, borderLeft: `3px solid ${borderColor}` }}>
      <CardHeader>
        <Row justify="between" align="center">
          <Text weight="bold">{m.name}</Text>
          <Pill size="sm" tone={m.tone}>{m.status}</Pill>
        </Row>
      </CardHeader>
      <CardBody>
        <Stack gap={8}>
          <Text size="small" tone="secondary">{m.desc}</Text>
          <Divider />
          <Stack gap={3}>
            <Row justify="between">
              <Text size="small" tone="secondary">AUC / métrica</Text>
              <Text size="small" weight="semibold">{m.auc}</Text>
            </Row>
            <Row justify="between">
              <Text size="small" tone="secondary">Archivo</Text>
              <Code as="span">{m.donde.split("→")[0].trim()}</Code>
            </Row>
          </Stack>
          <Text size="small" tone="secondary">
            <Text weight="semibold" size="small" as="span">Fortaleza: </Text>
            {m.fortaleza}
          </Text>
        </Stack>
      </CardBody>
    </Card>
  );
}

export default function SistemaOverview() {
  const [tab, setTab] = useState<"panorama"|"modelos"|"universos"|"insights"|"flujo"|"datos">("panorama");

  return (
    <Stack gap={22} style={{ padding: 24, maxWidth: 1100 }}>

      <Stack gap={4}>
        <Row justify="between" align="center">
          <H1>Sistema de Trading BMV — Panorama Completo</H1>
          <Pill size="sm">Jun 28, 2026</Pill>
        </Row>
        <Text tone="secondary" size="small">
          Dashboard Streamlit · 10 páginas · 5 universos · 6 modelos · 92 símbolos · Gemini NLP · GBM broker integration
        </Text>
      </Stack>

      <Grid columns={5} gap={10}>
        <Stat value="10"   label="Páginas del app" />
        <Stat value="5"    label="Universos de activos" />
        <Stat value="92"   label="Símbolos en BD" />
        <Stat value="6"    label="Modelos (2 en prod)" />
        <Stat value="17.2 MB" label="Datos históricos" />
      </Grid>

      <Divider />

      <Row gap={8} wrap>
        <Pill active={tab==="panorama"}  onClick={() => setTab("panorama")}>App & páginas</Pill>
        <Pill active={tab==="modelos"}   onClick={() => setTab("modelos")}>Modelos ML</Pill>
        <Pill active={tab==="universos"} onClick={() => setTab("universos")}>Universos & señales</Pill>
        <Pill active={tab==="insights"}  onClick={() => setTab("insights")}>Insights generados</Pill>
        <Pill active={tab==="flujo"}     onClick={() => setTab("flujo")}>Flujo operativo</Pill>
        <Pill active={tab==="datos"}     onClick={() => setTab("datos")}>Base de datos</Pill>
      </Row>

      {/* ── PANORAMA ─────────────────────────────────────────────────────────── */}
      {tab === "panorama" && (
        <Stack gap={18}>
          <Stack gap={4}>
            <H2>Dashboard Streamlit — 10 páginas</H2>
            <Text tone="secondary" size="small">
              Un solo archivo <Code as="span">app.py</Code> (2,894 líneas) con toda la UI.
              Sidebar de navegación, cache de 60s, botón de actualización global.
            </Text>
          </Stack>

          <Table
            headers={["Página", "Qué hace"]}
            rows={PAGES.map(p => [
              <Row gap={8} align="center">
                <Text size="small">{p.icon}</Text>
                <Text size="small" weight="semibold">{p.name}</Text>
              </Row>,
              <Text size="small" tone="secondary" as="span">{p.desc}</Text>,
            ])}
            columnAlign={["left","left"]}
            striped
          />

          <Grid columns={2} gap={20}>
            <Callout tone="success" title="Página principal: Ranking Mensual">
              <Stack gap={4}>
                <Text size="small">
                  El corazón del sistema. Muestra 5 universos × 4 horizontes temporales.
                  Para cada universo:
                </Text>
                <Stack gap={2}>
                  {["Régimen del mercado (alcista/lateral/bajista) con descripción",
                    "Consenso: tickers en top-5 de 3+ horizontes = señal más robusta",
                    "Tabs por horizonte: 1s / 2s / 3s / 4s semanas",
                    "Picks con análisis Gemini: resumen, acción, catalizador, riesgo",
                    "Ranking completo con colores (verde=top5, rojo=evitar)",
                    "Plan de acción: cuánto invertir, precio entry, cuándo rebalancear",
                  ].map(t => (
                    <Row key={t} gap={6}>
                      <Text size="small" tone="secondary">·</Text>
                      <Text size="small">{t}</Text>
                    </Row>
                  ))}
                </Stack>
              </Stack>
            </Callout>

            <Callout tone="info" title="Cómo se conecta todo">
              <Stack gap={4}>
                <Text size="small">
                  El app <Text weight="semibold" as="span">no calcula nada en tiempo real</Text> — lee
                  archivos JSON pre-computados en <Code as="span">data/signals/</Code>.
                </Text>
                <Text size="small">
                  Los scripts corren de forma independiente (manual o programado) y
                  el dashboard los muestra. El botón "Generar señales" dentro de la app
                  lanza <Code as="span">generate_all_signals.py</Code> como subprocess.
                </Text>
                <Text size="small">
                  Excepción: la página de Noticias sí hace scraping en tiempo real cuando
                  el usuario la abre, llamando a <Code as="span">gemini_analyst.analyze_ticker()</Code>.
                </Text>
              </Stack>
            </Callout>
          </Grid>
        </Stack>
      )}

      {/* ── MODELOS ──────────────────────────────────────────────────────────── */}
      {tab === "modelos" && (
        <Stack gap={18}>
          <Stack gap={4}>
            <H2>6 modelos — 2 en producción, 4 en investigación</H2>
            <Text tone="secondary" size="small">
              La barra verde izquierda = producción · naranja = investigación/validación · roja = experimental.
            </Text>
          </Stack>

          <Stack gap={12}>
            {MODELS.map(m => <ModelCard key={m.name} m={m} />)}
          </Stack>

          <Callout tone="warning" title="Estado actual del AUC">
            <Stack gap={4}>
              <Text size="small">
                El AUC del modelo base (WoE+LR) es <Text weight="semibold" as="span">0.534</Text> — apenas
                sobre azar (0.50). Esto significa que el modelo predice bien en ~53.4% de las operaciones.
                Con Kelly ¼ esto es rentable si el ratio win/loss es favorable, pero el margen es pequeño.
              </Text>
              <Text size="small">
                La ruta de mejora prioritaria:
                <Text weight="semibold" as="span"> 1)</Text> conectar macro features (ya definidas, no cableadas),
                <Text weight="semibold" as="span"> 2)</Text> integrar news sentiment (recién construido),
                <Text weight="semibold" as="span"> 3)</Text> activar Meta-labeling (AUC 0.558 en holdout).
                Objetivo: AUC ≥ 0.58.
              </Text>
            </Stack>
          </Callout>
        </Stack>
      )}

      {/* ── UNIVERSOS ────────────────────────────────────────────────────────── */}
      {tab === "universos" && (
        <Stack gap={18}>
          <H2>5 universos — señales vigentes hoy (28 Jun 2026)</H2>
          <Stack gap={14}>
            {UNIVERSES.map(u => (
              <Card key={u.slug}>
                <CardHeader>
                  <Row justify="between" align="center">
                    <Text weight="bold">{u.name}</Text>
                    <Row gap={8}>
                      <Pill size="sm">{u.moneda}</Pill>
                      <Pill size="sm">Horizonte: {u.horizonte}</Pill>
                      <Pill size="sm">{u.n} tickers</Pill>
                    </Row>
                  </Row>
                </CardHeader>
                <CardBody>
                  <Stack gap={8}>
                    <Stack gap={3}>
                      <Text size="small" weight="semibold">Consenso ≥3 horizontes (señal más fuerte)</Text>
                      <Row gap={8} wrap>
                        {u.consenso.map(t => (
                          <Pill key={t} size="sm" tone="success">{t}</Pill>
                        ))}
                      </Row>
                    </Stack>
                  </Stack>
                </CardBody>
              </Card>
            ))}
          </Stack>

          <Callout tone="info" title="Cómo leer el consenso">
            <Text size="small">
              Un ticker en consenso de 4 horizontes significa que el modelo lo pone en top-5
              para las próximas 1, 2, 3 y 4 semanas. Es la señal más robusta — el modelo coincide
              en múltiples ventanas de tiempo. Hoy: <Text weight="semibold" as="span">POSADAS</Text> y{" "}
              <Text weight="semibold" as="span">WALMEX</Text> aparecen en todos los horizontes de BMV.
            </Text>
          </Callout>
        </Stack>
      )}

      {/* ── INSIGHTS ─────────────────────────────────────────────────────────── */}
      {tab === "insights" && (
        <Stack gap={18}>
          <Stack gap={4}>
            <H2>Insights que genera el sistema</H2>
            <Text tone="secondary" size="small">
              Seis categorías de insights accionables. Algunos son automáticos, otros requieren revisar el dashboard.
            </Text>
          </Stack>

          <Stack gap={14}>
            {INSIGHTS.map(cat => (
              <Stack key={cat.categoria} gap={6}>
                <Row gap={8} align="center">
                  <Text size="large">{cat.icon}</Text>
                  <H3>{cat.categoria}</H3>
                </Row>
                <Stack gap={4}>
                  {cat.ejemplos.map((ej, i) => (
                    <Row key={i} gap={10} align="start">
                      <Text size="small" tone="secondary" style={{ minWidth: 16 }}>·</Text>
                      <Text size="small">{ej}</Text>
                    </Row>
                  ))}
                </Stack>
                <Divider />
              </Stack>
            ))}
          </Stack>
        </Stack>
      )}

      {/* ── FLUJO ────────────────────────────────────────────────────────────── */}
      {tab === "flujo" && (
        <Stack gap={18}>
          <Stack gap={4}>
            <H2>Flujo operativo semanal</H2>
            <Text tone="secondary" size="small">
              El sistema está diseñado para trading semanal en la BMV. Los scripts se corren manualmente
              (o se pueden programar con cron). El app es solo visualización.
            </Text>
          </Stack>

          <Stack gap={10}>
            {FLUJO.map((f, i) => (
              <Row key={i} gap={16} align="start">
                <Text weight="bold" size="small" style={{ minWidth: 160 }}>{f.dia}</Text>
                <Stack gap={3} style={{ flex: 1 }}>
                  {f.acciones.map((a, j) => (
                    <Row key={j} gap={8} align="center">
                      <Text size="small" tone="secondary">→</Text>
                      <Text size="small">{a}</Text>
                    </Row>
                  ))}
                </Stack>
              </Row>
            ))}
          </Stack>

          <Divider />

          <Grid columns={2} gap={20}>
            <Callout tone="success" title="Scripts de producción (correr cada semana)">
              <Stack gap={3}>
                {[
                  ["scripts/fetch_news.py", "Scraping noticias 5 universos"],
                  ["scripts/build_database.py --update", "BD local al día"],
                  ["scripts/generate_all_signals.py", "Rankings + señales"],
                ].map(([cmd, desc]) => (
                  <Stack key={cmd} gap={1}>
                    <Code as="span">{cmd}</Code>
                    <Text size="small" tone="secondary">{desc}</Text>
                  </Stack>
                ))}
              </Stack>
            </Callout>

            <Callout tone="info" title="Scripts de investigación (correr cuando se quiera)">
              <Stack gap={3}>
                {[
                  ["scripts/run_model.py", "Walk-forward WoE+LR vs LGBM"],
                  ["scripts/run_ensemble.py", "Stacking LR+LGBM+RF"],
                  ["scripts/run_meta.py", "Meta-labeling sobre ensemble"],
                  ["scripts/run_woe.py", "Análisis IV de features"],
                ].map(([cmd, desc]) => (
                  <Stack key={cmd} gap={1}>
                    <Code as="span">{cmd}</Code>
                    <Text size="small" tone="secondary">{desc}</Text>
                  </Stack>
                ))}
              </Stack>
            </Callout>
          </Grid>
        </Stack>
      )}

      {/* ── DATOS ────────────────────────────────────────────────────────────── */}
      {tab === "datos" && (
        <Stack gap={18}>
          <Stack gap={4}>
            <H2>Base de datos local — 90 parquets, 17.2 MB</H2>
            <Text tone="secondary" size="small">
              Todo el historial en <Code as="span">data/market/*.parquet</Code> (Snappy comprimido).
              Actualización incremental: solo descarga días nuevos.
            </Text>
          </Stack>

          <Table
            headers={["Grupo", "Tickers", "Desde", "Días aprox.", "MB aprox.", "Estado"]}
            rows={DATA_COBERTURA.map(d => [
              <Text weight="semibold" size="small" as="span">{d.grupo}</Text>,
              d.tickers,
              d.inicio,
              d.dias,
              d.mb,
              <Pill size="sm" tone="success">OK</Pill>,
            ])}
            columnAlign={["left","center","center","right","right","center"]}
            striped
          />

          <Grid columns={2} gap={20}>
            <Stack gap={8}>
              <H3>Estructura de cada parquet</H3>
              <Card>
                <CardBody>
                  <Code>
{`# Columnas: Date (index), Open, High, Low, Close, Volume
# Frecuencia: diaria
# Compresión: Snappy
# Ejemplo:
import pandas as pd
df = pd.read_parquet("data/market/ALSEA.MX.parquet")
# df.shape → (6,076, 5)
# df.index[0] → 2000-01-18
# df.index[-1] → 2026-06-26`}
                  </Code>
                </CardBody>
              </Card>
            </Stack>

            <Stack gap={8}>
              <H3>Fuentes de datos activas</H3>
              <Stack gap={6}>
                {[
                  { src: "Yahoo Finance (yfinance)", uso: "OHLCV histórico + noticias por ticker", costo: "Gratis" },
                  { src: "Google News RSS", uso: "Noticias en tiempo real por empresa", costo: "Gratis" },
                  { src: "El Financiero RSS", uso: "Noticias BMV en español", costo: "Gratis" },
                  { src: "GDELT Project", uso: "Historial noticias desde 2015", costo: "Gratis" },
                  { src: "Gemini 2.5-flash", uso: "NLP sentiment + análisis ejecutivo picks", costo: "~$0.01/día" },
                  { src: "DataBursátil API", uso: "Datos adicionales BMV (token en .env)", costo: "Suscripción" },
                ].map(s => (
                  <Row key={s.src} justify="between" align="start">
                    <Stack gap={1} style={{ flex: 1 }}>
                      <Text size="small" weight="semibold">{s.src}</Text>
                      <Text size="small" tone="secondary">{s.uso}</Text>
                    </Stack>
                    <Pill size="sm" tone={s.costo === "Gratis" ? "success" : "warning"}>
                      {s.costo}
                    </Pill>
                  </Row>
                ))}
              </Stack>
            </Stack>
          </Grid>

          <Callout tone="info" title="Próximos datos a integrar">
            <Stack gap={3}>
              <Text size="small"><Text weight="semibold" as="span">Noticias históricas (GDELT):</Text> para backfill de 252 días de training con news_sent_score. Actualmente las news features solo tienen datos del último mes.</Text>
              <Text size="small"><Text weight="semibold" as="span">Fundamentales:</Text> <Code as="span">scripts/fetch_fundamentals.py</Code> ya existe. P/E, EV/EBITDA, ROE por ticker — pendiente de integrar al modelo.</Text>
              <Text size="small"><Text weight="semibold" as="span">Datos intraday:</Text> <Code as="span">scripts/fetch_intraday.py</Code> existe. Barras de 2 min para el monitor. Sin integración al modelo de señales aún.</Text>
            </Stack>
          </Callout>
        </Stack>
      )}

    </Stack>
  );
}
