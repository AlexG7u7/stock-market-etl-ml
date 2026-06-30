import { useState } from "react";
import {
  Stack, Row, Grid, H1, H2, Text, Card, CardHeader, CardBody,
  Pill, Stat, Callout, Divider, Table, BarChart, LineChart, useHostTheme,
} from "cursor/canvas";

// Fuente: data/eval/dashboard_eval.json — 2026-06-29
const META = {
  generated: "2026-06-29",
  universe: "bmv",
  testRange: "2023-03-09 → 2026-06-18",
  nPeriods: 172,
  roundTripCost: "0.60%",
};

const SUMMARY = {
  verdict: "NO_BET_LIVE",
  sharpeGross: 1.525,
  sharpeNet: -1.786,
  retNetPct: -46.67,
  benchSharpe: 0.816,
  benchRetPct: 15.81,
  auc: 0.507,
  maxDdNet: -53.1,
  winRateNet: 44.8,
};

const GRID = [
  { k: 5, score: "p_up",   weight: "equal",      sharpeNet: -1.786, sharpeGross: 1.525, retNet: -46.7 },
  { k: 3, score: "p_up",   weight: "equal",      sharpeNet: -2.310, sharpeGross: 0.628, retNet: -59.5 },
  { k: 3, score: "p_rel",  weight: "equal",      sharpeNet: -2.576, sharpeGross: 0.072, retNet: -67.3 },
  { k: 5, score: "p_rel",  weight: "conviction", sharpeNet: -2.719, sharpeGross: -0.058, retNet: -68.9 },
  { k: 3, score: "signal", weight: "equal",      sharpeNet: -3.208, sharpeGross: -0.191, retNet: -69.5 },
];

const KBS = [
  "KB-001 métricas duales", "KB-003 costos BMV", "KB-004 news features",
  "KB-010 MLS-LSTM", "KB-012 LSTM en SuperModel", "KB-041 dedup TF-IDF",
  "KB-043 decay temporal", "KB-060 stacking LR", "KB-081 backtest top-K",
];

const EQUITY_NET = [100.0, 99.8, 94.9, 90.2, 89.0, 91.6, 95.2, 96.8, 94.1, 94.3, 90.7, 91.6, 93.8, 90.2, 89.6, 89.4, 86.4, 87.3, 85.6, 83.9];
const EQUITY_BH  = [100.0, 98.8, 97.5, 98.4, 97.2, 99.0, 100.4, 99.7, 98.2, 99.3, 97.7, 98.4, 100.0, 98.7, 98.0, 98.2, 96.4, 97.3, 95.7, 94.9];

export default function ResearchEval() {
  const [tab, setTab] = useState<"backtest" | "grid" | "stack">("backtest");
  const theme = useHostTheme();

  const gridLabels = GRID.map(g => `K${g.k} ${g.score}`);
  const gridSharpeNet = GRID.map(g => g.sharpeNet);
  const gridSharpeGross = GRID.map(g => g.sharpeGross);

  return (
    <Stack gap={22} style={{ padding: 24, maxWidth: 1050 }}>
      <Stack gap={4}>
        <Row justify="between" align="center">
          <H1>Research & Eval — Literatura → Código</H1>
          <Pill size="sm">{META.universe.toUpperCase()}</Pill>
        </Row>
        <Text tone="secondary" size="small">
          Backtest top-K Ghosh 2022 · costos BMV {META.roundTripCost} RT · {META.nPeriods} rebalance · {META.testRange}
        </Text>
      </Stack>

      <Callout
        tone="warning"
        title={`Veredicto: ${SUMMARY.verdict}`}
      >
        <Text size="small">
          Sharpe bruto {SUMMARY.sharpeGross.toFixed(2)} pero neto {SUMMARY.sharpeNet.toFixed(2)} tras costos.
          NAFTRAC B&amp;H: Sharpe {SUMMARY.benchSharpe.toFixed(2)}, retorno +{SUMMARY.benchRetPct}%.
          Paper trading only hasta tunear K/umbrales.
        </Text>
      </Callout>

      <Grid columns={5} gap={10}>
        <Stat value={SUMMARY.sharpeGross.toFixed(2)} label="Sharpe bruto" tone="success" />
        <Stat value={SUMMARY.sharpeNet.toFixed(2)} label="Sharpe neto" tone="danger" />
        <Stat value={`${SUMMARY.retNetPct}%`} label="Retorno neto" tone="danger" />
        <Stat value={SUMMARY.auc.toFixed(3)} label="AUC OOS" />
        <Stat value={META.roundTripCost} label="Costo round-trip" />
      </Grid>

      <Divider />

      <Row gap={8}>
        <Pill active={tab === "backtest"} onClick={() => setTab("backtest")}>Backtest vs NAFTRAC</Pill>
        <Pill active={tab === "grid"} onClick={() => setTab("grid")}>Grid search</Pill>
        <Pill active={tab === "stack"} onClick={() => setTab("stack")}>Stack implementado</Pill>
      </Row>

      {tab === "backtest" && (
        <Stack gap={14}>
          <LineChart
            categories={EQUITY_NET.map((_, i) => `T${i}`)}
            series={[
              { name: "Top-K neto (idx)", data: EQUITY_NET },
              { name: "NAFTRAC B&H (idx)", data: EQUITY_BH },
            ]}
            height={240}
            yMin={40}
            yMax={120}
          />
          <Text tone="secondary" size="small">
            Curva indexada (últimos 20 períodos). Fuente: scripts/backtest_topk.py · data/eval/dashboard_eval.json
          </Text>
          <Grid columns={2} gap={16}>
            <Card>
              <CardHeader>Estrategia top-5 (neto)</CardHeader>
              <CardBody>
                <Grid columns={2} gap={8}>
                  <Stat value={`${SUMMARY.maxDdNet}%`} label="Max drawdown" />
                  <Stat value={`${SUMMARY.winRateNet}%`} label="Win rate neto" />
                </Grid>
              </CardBody>
            </Card>
            <Card>
              <CardHeader>Benchmark NAFTRAC</CardHeader>
              <CardBody>
                <Grid columns={2} gap={8}>
                  <Stat value={SUMMARY.benchSharpe.toFixed(2)} label="Sharpe" tone="success" />
                  <Stat value={`+${SUMMARY.benchRetPct}%`} label="Retorno total" tone="success" />
                </Grid>
              </CardBody>
            </Card>
          </Grid>
        </Stack>
      )}

      {tab === "grid" && (
        <Stack gap={12}>
          <H2>Grid search — Sharpe neto por variante</H2>
          <BarChart
            categories={gridLabels}
            series={[
              { name: "Sharpe neto", data: gridSharpeNet },
              { name: "Sharpe bruto", data: gridSharpeGross },
            ]}
            height={220}
          />
          <Table
            headers={["K", "Score", "Weight", "Sharpe neto", "Sharpe bruto", "Ret neto %"]}
            rows={GRID.map(g => [
              g.k, g.score, g.weight,
              g.sharpeNet.toFixed(2), g.sharpeGross.toFixed(2), `${g.retNet}%`,
            ])}
            columnAlign={["center", "center", "center", "right", "right", "right"]}
            striped
          />
        </Stack>
      )}

      {tab === "stack" && (
        <Stack gap={12}>
          <H2>Pipeline implementado (5 agentes · Jun 2026)</H2>
          <Table
            headers={["Capa", "Módulo", "Ticket"]}
            rows={[
              ["Backtest + costos", "backtester.py, backtest_topk.py", "KB-001, KB-003, KB-081"],
              ["News dedup + decay", "news.py, NEWS_FEATURE_COLS", "KB-004, KB-041, KB-043"],
              ["LSTM clasificación", "lstm_seq.py → super_model.py", "KB-010–013"],
              ["Stacking LR", "SuperModel(use_stacking=True)", "KB-060"],
              ["Agent KB → Gemini", "knowledge_loader.py", "LR-001..012"],
            ]}
            striped
          />
          <Row gap={6} wrap>
            {KBS.map(k => <Pill key={k} size="sm">{k}</Pill>)}
          </Row>
          <Callout tone="info" title="App Streamlit">
            <Text size="small">
              Nueva página 📊 Research &amp; Eval en app.py. Botón «Correr evaluaciones» ejecuta
              scripts/run_all_evaluations.py y lee data/eval/dashboard_eval.json.
            </Text>
          </Callout>
        </Stack>
      )}
    </Stack>
  );
}
