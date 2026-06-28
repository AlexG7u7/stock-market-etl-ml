import { useState } from "react";
import {
  Stack, Row, Grid, H1, H2, H3, Text, Card, CardHeader, CardBody,
  Pill, Stat, Callout, Divider, Table, useHostTheme, Code,
} from "cursor/canvas";

// ─── Capas del super modelo ───────────────────────────────────────────────────

const LAYERS = [
  {
    n: 1,
    name: "Modelos base (signals)",
    color: "neutral",
    desc: "Cada modelo emite su predicción independiente por ticker. Ya existen todos.",
    items: [
      { m: "Cross-seccional LGBM", out: "Score retorno relativo", existe: true },
      { m: "WoE + LogReg",          out: "P(subida 5d)",            existe: true },
      { m: "Ensemble (LR+LGBM+MLP)", out: "P(subida) calibrada",   existe: true },
      { m: "Meta-labeling",          out: "Confianza de la señal",  existe: true },
      { m: "Ising regime",           out: "Régimen de mercado",     existe: true },
      { m: "News sentiment",         out: "news_sent_score",        existe: true },
    ],
  },
  {
    n: 2,
    name: "Fusión (meta-stacking)",
    color: "accent",
    desc: "Combina todas las señales en UN score de convicción por ticker, ponderado por el edge histórico de cada modelo (AUC − 0.5).",
    items: [
      { m: "Pesos por AUC",        out: "w_i = max(AUC_i − 0.5, 0)", existe: false },
      { m: "Ajuste por régimen",   out: "× factor Ising (risk-on/off)", existe: false },
      { m: "Penalización news",    out: "× (1 si sent>0, 0.5 si sent<−0.3)", existe: false },
      { m: "Score de convicción",  out: "conviction ∈ [0,1] + desacuerdo", existe: false },
    ],
  },
  {
    n: 3,
    name: "Ranking masivo cross-universo",
    color: "accent",
    desc: "Ordena TODOS los tickers de los 5 universos en una sola lista maestra. Genera insights estructurados.",
    items: [
      { m: "Master ranking",       out: "Top-N global (87 tickers)", existe: false },
      { m: "Divergencias",         out: "Modelos en desacuerdo = oportunidad/riesgo", existe: false },
      { m: "Concentración sector", out: "Alerta si top-5 misma industria", existe: false },
      { m: "Correlación",          out: "Diversificación del portafolio sugerido", existe: false },
    ],
  },
  {
    n: 4,
    name: "Validación + narrativa (Gemini)",
    color: "success",
    desc: "Gemini NO genera la recomendación — recibe la decisión cuantitativa + evidencia y actúa como segunda opinión crítica. Puede confirmar, degradar o vetar.",
    items: [
      { m: "Veredicto",            out: "CONFIRMA / DEGRADA / VETA", existe: false },
      { m: "Justificación",        out: "Por qué, citando la evidencia real", existe: false },
      { m: "Narrativa ejecutiva",  out: "Tesis de inversión en prosa", existe: false },
      { m: "Red flags",            out: "Riesgos que el modelo no ve", existe: false },
    ],
  },
];

const FUSION_FORMULA = [
  { paso: "1. Normalizar", detalle: "Cada modelo → score en [0,1] comparable (percentil cross-seccional)" },
  { paso: "2. Pesar", detalle: "w_i = max(AUC_i − 0.5, 0) / Σ — el modelo con más edge pesa más" },
  { paso: "3. Fusionar", detalle: "conviction = Σ (w_i × score_i)" },
  { paso: "4. Modular régimen", detalle: "× factor Ising: risk-on amplifica, risk-off reduce sizing" },
  { paso: "5. Filtro news", detalle: "× penalización si news_sent_score < −0.3" },
  { paso: "6. Desacuerdo", detalle: "disagreement = std(scores) — alta = baja confianza" },
];

const GEMINI_CONTRACT = {
  input: [
    "Ticker + universo + precio actual",
    "Score de convicción del super modelo + ranking",
    "Predicción de CADA modelo base (transparencia)",
    "Régimen Ising + sentiment news + titulares reales",
    "Métricas de riesgo (ATR, correlación, sizing Kelly)",
  ],
  output: [
    "veredicto: CONFIRMA | DEGRADA | VETA",
    "confianza_gemini: 0–100",
    "tesis: narrativa de inversión (2-3 frases)",
    "evidencia_a_favor: [puntos citando los datos]",
    "red_flags: [riesgos que los modelos no capturan]",
    "accion_final: COMPRA FUERTE | COMPRA | ESPERA | EVITA",
  ],
};

const INSIGHTS_MASIVOS = [
  { tipo: "Consenso fuerte", ej: "POSADAS: 5/6 modelos lo rankean top-10, régimen risk-on, news +0.2 → CONVICCIÓN ALTA" },
  { tipo: "Divergencia", ej: "TSLA: LGBM dice top-3 pero Meta-labeling lo veta (baja confianza) → revisar manualmente" },
  { tipo: "Régimen", ej: "Cripto en risk-off (Ising temp alta) → reducir sizing 50% en todo el universo" },
  { tipo: "Rotación", ej: "Capital sugiere salir de ETFs defensivos (XLP) hacia growth (QQQ) por cambio de momentum" },
  { tipo: "Veto por news", ej: "HOTEL: score técnico alto pero news_sent −1.0 → super modelo lo baja del ranking" },
  { tipo: "Cross-universo", ej: "Mejor risk/reward global hoy: MARA (cripto) > cualquier pick de BMV ajustado por vol" },
];

const FILES = [
  { file: "src/ml/super_model.py", tipo: "NUEVO", desc: "Clase SuperModel: orquesta capas 1-3, fusión, ranking masivo" },
  { file: "src/ml/gemini_validator.py", tipo: "NUEVO", desc: "Capa 4: Gemini como validador crítico (contrato estructurado)" },
  { file: "scripts/run_super_model.py", tipo: "NUEVO", desc: "CLI: corre todo el pipeline → data/super_signals.json" },
  { file: "src/ml/ensemble.py", tipo: "REUSA", desc: "Modelo base — ya existe" },
  { file: "src/ml/meta_model.py", tipo: "REUSA", desc: "Confianza — ya existe" },
  { file: "src/ml/ising_market.py", tipo: "REUSA", desc: "Régimen — extraer extract_regime_features()" },
  { file: "src/ml/news.py", tipo: "REUSA", desc: "Sentiment — ya construido hoy" },
  { file: "src/api/gemini_analyst.py", tipo: "REUSA", desc: "Cliente Gemini — ya existe" },
  { file: "app.py", tipo: "EDITA", desc: "Nueva página: 🦾 Super Modelo" },
];

// ─── Component ────────────────────────────────────────────────────────────────

function LayerBlock({ layer }: { layer: typeof LAYERS[0] }) {
  const theme = useHostTheme();
  const accent =
    layer.color === "success" ? theme.colors.feedback.success :
    layer.color === "accent"  ? theme.colors.border.accent :
    theme.colors.border.default;

  return (
    <Card style={{ borderLeft: `3px solid ${accent}` }}>
      <CardHeader>
        <Row gap={10} align="center">
          <Stat value={`L${layer.n}`} label="" />
          <Stack gap={1}>
            <Text weight="bold">{layer.name}</Text>
            <Text size="small" tone="secondary">{layer.desc}</Text>
          </Stack>
        </Row>
      </CardHeader>
      <CardBody>
        <Grid columns={2} gap={8}>
          {layer.items.map(it => (
            <Row key={it.m} justify="between" align="center"
                 style={{ padding: "4px 0" }}>
              <Stack gap={0}>
                <Text size="small" weight="semibold">{it.m}</Text>
                <Text size="small" tone="secondary">{it.out}</Text>
              </Stack>
              <Pill size="sm" tone={it.existe ? "success" : "warning"}>
                {it.existe ? "existe" : "nuevo"}
              </Pill>
            </Row>
          ))}
        </Grid>
      </CardBody>
    </Card>
  );
}

export default function SuperModelo() {
  const [tab, setTab] = useState<"arquitectura"|"fusion"|"gemini"|"insights"|"plan">("arquitectura");

  return (
    <Stack gap={22} style={{ padding: 24, maxWidth: 1080 }}>

      <Stack gap={4}>
        <Row justify="between" align="center">
          <H1>Super Modelo — Meta-Orquestador</H1>
          <Pill size="sm">Diseño propuesto</Pill>
        </Row>
        <Text tone="secondary" size="small">
          Fusiona los 6 modelos en una decisión masiva cross-universo, validada y narrada por Gemini como segunda opinión crítica.
        </Text>
      </Stack>

      <Grid columns={4} gap={12}>
        <Stat value="6" label="Modelos fusionados" tone="success" />
        <Stat value="87" label="Tickers rankeados a la vez" />
        <Stat value="4" label="Capas (3 cuant + 1 Gemini)" />
        <Stat value="~80%" label="Piezas ya en el repo" tone="success" />
      </Grid>

      <Divider />

      <Row gap={8} wrap>
        <Pill active={tab==="arquitectura"} onClick={() => setTab("arquitectura")}>Arquitectura</Pill>
        <Pill active={tab==="fusion"}       onClick={() => setTab("fusion")}>Fusión de modelos</Pill>
        <Pill active={tab==="gemini"}       onClick={() => setTab("gemini")}>Gemini validador</Pill>
        <Pill active={tab==="insights"}     onClick={() => setTab("insights")}>Insights masivos</Pill>
        <Pill active={tab==="plan"}         onClick={() => setTab("plan")}>Plan de build</Pill>
      </Row>

      {/* ── ARQUITECTURA ─────────────────────────────────────────────────────── */}
      {tab === "arquitectura" && (
        <Stack gap={16}>
          <H2>4 capas — de señales crudas a tesis validada</H2>
          <Stack gap={12}>
            {LAYERS.map(l => <LayerBlock key={l.n} layer={l} />)}
          </Stack>

          <Callout tone="info" title="Principio de diseño clave">
            <Text size="small">
              El flujo es estrictamente <Text weight="semibold" as="span">cuantitativo primero, IA después</Text>.
              Los modelos deciden; Gemini valida y explica. Esto evita que el LLM "invente" recomendaciones —
              solo puede confirmar, degradar o vetar lo que el modelo ya calculó, citando evidencia real.
            </Text>
          </Callout>
        </Stack>
      )}

      {/* ── FUSIÓN ───────────────────────────────────────────────────────────── */}
      {tab === "fusion" && (
        <Stack gap={16}>
          <Stack gap={4}>
            <H2>Cómo se fusionan los 6 modelos</H2>
            <Text tone="secondary" size="small">
              No es un promedio simple. Cada modelo pesa proporcional a su edge histórico, y el resultado se modula por régimen y noticias.
            </Text>
          </Stack>

          <Table
            headers={["Paso", "Qué hace"]}
            rows={FUSION_FORMULA.map(f => [
              <Text weight="semibold" size="small" as="span">{f.paso}</Text>,
              <Text size="small" tone="secondary" as="span">{f.detalle}</Text>,
            ])}
            columnAlign={["left","left"]}
            striped
          />

          <Card>
            <CardBody>
              <Code>
{`# src/ml/super_model.py  (núcleo de la fusión)

def fuse(self, ticker_signals: dict) -> dict:
    # ticker_signals = {"lgbm": 0.71, "woe_lr": 0.58,
    #                   "ensemble": 0.62, "meta": 0.55, ...}
    weights = {m: max(self.auc[m] - 0.5, 0) for m in ticker_signals}
    total   = sum(weights.values()) or 1.0

    conviction = sum(ticker_signals[m] * weights[m] / total
                     for m in ticker_signals)

    # Modular por régimen Ising
    conviction *= self.regime_factor      # risk-on > 1, risk-off < 1

    # Penalizar noticias negativas
    if self.news_sent < -0.3:
        conviction *= 0.5

    disagreement = float(np.std(list(ticker_signals.values())))

    return {
        "conviction":   round(conviction, 3),
        "disagreement": round(disagreement, 3),
        "signals":      ticker_signals,   # transparencia total
    }`}
              </Code>
            </CardBody>
          </Card>

          <Callout tone="warning" title="El desacuerdo es información">
            <Text size="small">
              Cuando los modelos coinciden (bajo <Code as="span">disagreement</Code>), la señal es fuerte.
              Cuando divergen mucho, el super modelo lo marca como "revisar" en vez de operar a ciegas —
              y es justo ahí donde Gemini aporta más valor como desempate cualitativo.
            </Text>
          </Callout>
        </Stack>
      )}

      {/* ── GEMINI ───────────────────────────────────────────────────────────── */}
      {tab === "gemini" && (
        <Stack gap={16}>
          <Stack gap={4}>
            <H2>Gemini como validador crítico, no como oráculo</H2>
            <Text tone="secondary" size="small">
              Recibe la recomendación del modelo + toda la evidencia, y debe justificarla o desafiarla.
              Contrato de entrada/salida estricto para que sea auditable y no alucine.
            </Text>
          </Stack>

          <Grid columns={2} gap={20}>
            <Card>
              <CardHeader><Text weight="bold">Entrada a Gemini</Text></CardHeader>
              <CardBody>
                <Stack gap={5}>
                  {GEMINI_CONTRACT.input.map((i, idx) => (
                    <Row key={idx} gap={8} align="start">
                      <Text size="small" tone="secondary">{idx+1}.</Text>
                      <Text size="small">{i}</Text>
                    </Row>
                  ))}
                </Stack>
              </CardBody>
            </Card>

            <Card>
              <CardHeader><Text weight="bold">Salida estructurada (JSON)</Text></CardHeader>
              <CardBody>
                <Stack gap={5}>
                  {GEMINI_CONTRACT.output.map((o, idx) => (
                    <Row key={idx} gap={8} align="start">
                      <Text size="small" tone="secondary">·</Text>
                      <Code as="span">{o}</Code>
                    </Row>
                  ))}
                </Stack>
              </CardBody>
            </Card>
          </Grid>

          <Card>
            <CardBody>
              <Code>
{`# src/ml/gemini_validator.py

PROMPT = '''Eres el comité de riesgo. El modelo cuantitativo recomienda
{accion} sobre {ticker} (convicción {conviction}, ranking #{rank} de 87).

Predicción de cada modelo:
{signals_breakdown}

Régimen de mercado: {regime}
Sentimiento de noticias: {news_sent} — titulares:
{headlines}
Riesgo: ATR {atr}%, correlación con cartera {corr}%

Tu trabajo NO es predecir. Es VALIDAR la recomendación del modelo.
- Si la evidencia la respalda → CONFIRMA
- Si hay señales mixtas → DEGRADA y explica
- Si ves un riesgo grave que el modelo no captura → VETA

Responde SOLO JSON:
{{"veredicto": "CONFIRMA|DEGRADA|VETA",
  "confianza_gemini": 0-100,
  "tesis": "...", "evidencia_a_favor": [...],
  "red_flags": [...], "accion_final": "..."}}'''`}
              </Code>
            </CardBody>
          </Card>

          <Callout tone="success" title="Por qué este enfoque es robusto">
            <Stack gap={4}>
              <Text size="small">
                <Text weight="semibold" as="span">Anti-alucinación:</Text> Gemini solo ve datos reales y debe citarlos. No puede inventar un precio o una noticia.
              </Text>
              <Text size="small">
                <Text weight="semibold" as="span">Auditable:</Text> el veredicto queda registrado junto a la decisión del modelo. Puedes medir si Gemini agrega valor (¿sus vetos evitaron pérdidas?).
              </Text>
              <Text size="small">
                <Text weight="semibold" as="span">El modelo manda:</Text> si Gemini falla o no hay API, el super modelo sigue funcionando con la decisión cuantitativa.
              </Text>
            </Stack>
          </Callout>
        </Stack>
      )}

      {/* ── INSIGHTS ─────────────────────────────────────────────────────────── */}
      {tab === "insights" && (
        <Stack gap={16}>
          <Stack gap={4}>
            <H2>Insights que genera "de forma masiva"</H2>
            <Text tone="secondary" size="small">
              Al rankear los 87 tickers juntos, emergen patrones que ningún universo aislado puede ver.
            </Text>
          </Stack>

          <Stack gap={10}>
            {INSIGHTS_MASIVOS.map((ins, i) => (
              <Card key={i}>
                <CardBody>
                  <Row gap={12} align="start">
                    <Pill size="sm" tone="accent">{ins.tipo}</Pill>
                    <Text size="small" style={{ flex: 1 }}>{ins.ej}</Text>
                  </Row>
                </CardBody>
              </Card>
            ))}
          </Stack>

          <Callout tone="info" title="Salida final del super modelo">
            <Text size="small">
              Un solo archivo <Code as="span">data/super_signals.json</Code> con: ranking maestro de 87 tickers,
              score de convicción + desacuerdo por cada uno, veredicto Gemini, tesis narrada, y un portafolio
              sugerido diversificado cross-universo con sizing por Kelly ajustado a régimen.
            </Text>
          </Callout>
        </Stack>
      )}

      {/* ── PLAN ─────────────────────────────────────────────────────────────── */}
      {tab === "plan" && (
        <Stack gap={16}>
          <Stack gap={4}>
            <H2>Plan de implementación</H2>
            <Text tone="secondary" size="small">
              3 archivos nuevos, reusa 5 existentes, 1 edición al app. Estimado: 1 sesión de trabajo.
            </Text>
          </Stack>

          <Table
            headers={["Archivo", "Tipo", "Rol"]}
            rows={FILES.map(f => [
              <Code as="span">{f.file}</Code>,
              <Pill size="sm" tone={f.tipo === "NUEVO" ? "warning" : f.tipo === "EDITA" ? "accent" : "success"}>
                {f.tipo}
              </Pill>,
              <Text size="small" tone="secondary" as="span">{f.desc}</Text>,
            ])}
            columnAlign={["left","center","left"]}
            striped
          />

          <Grid columns={3} gap={12}>
            <Card>
              <CardHeader><Text weight="bold" size="small">Fase 1 — Fusión</Text></CardHeader>
              <CardBody>
                <Stack gap={4}>
                  <Text size="small">SuperModel que carga los modelos base y fusiona scores con pesos por AUC.</Text>
                  <Text size="small" tone="secondary">Salida: convicción + desacuerdo por ticker.</Text>
                </Stack>
              </CardBody>
            </Card>
            <Card>
              <CardHeader><Text weight="bold" size="small">Fase 2 — Ranking masivo</Text></CardHeader>
              <CardBody>
                <Stack gap={4}>
                  <Text size="small">Cross-universo: 87 tickers en una lista. Insights de divergencia, régimen, sector.</Text>
                  <Text size="small" tone="secondary">Salida: super_signals.json</Text>
                </Stack>
              </CardBody>
            </Card>
            <Card>
              <CardHeader><Text weight="bold" size="small">Fase 3 — Gemini</Text></CardHeader>
              <CardBody>
                <Stack gap={4}>
                  <Text size="small">Validador con contrato estricto. Veredicto + tesis para top-N.</Text>
                  <Text size="small" tone="secondary">Salida: enriquece super_signals.json</Text>
                </Stack>
              </CardBody>
            </Card>
          </Grid>

          <Callout tone="warning" title="Decisiones que necesito de ti antes de construir">
            <Stack gap={4}>
              <Text size="small"><Text weight="semibold" as="span">1. Alcance del ranking:</Text> ¿un solo ranking maestro de los 87 tickers, o mantener separación por universo con un meta-score?</Text>
              <Text size="small"><Text weight="semibold" as="span">2. Rol de Gemini:</Text> ¿validador de solo el top-N (barato, ~10 tickers) o de todo lo que pase un umbral de convicción?</Text>
              <Text size="small"><Text weight="semibold" as="span">3. LSTM/Ising:</Text> ¿los incluyo desde ya o arranco con los 4 modelos tabulares (más rápido y probado) y los sumo después?</Text>
            </Stack>
          </Callout>
        </Stack>
      )}

    </Stack>
  );
}
