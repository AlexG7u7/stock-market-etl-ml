import { useState } from "react";
import {
  Stack, Row, Grid, H1, H2, H3, Text, Card, CardHeader, CardBody,
  Pill, Stat, Callout, Divider, BarChart, Table, useHostTheme,
} from "cursor/canvas";

// ─── Datos reales 2026-06-27  ─────────────────────────────────────────────────
// Capital: $100,000 MXN · Threshold: P > 53% · Horizon: 5 días

const META = {
  date: "2026-06-27 13:54", capital: 100_000, threshold: 0.53, horizon: 5,
  modelAuc: 0.534, trainWindow: 252,
};

interface FeatureSnap { williams_r:number; stoch_k:number; ret_10d:number; bb_pct:number; price_vs_sma20:number; rsi_14:number }

interface Sig {
  ticker: string; price: number; pUp: number; entry: number; stop: number;
  t1: number; t2: number; pctCap: number; shares: number; capitalMxn: number;
  riskPct: number; rrRatio: number; edge: number; reason: string;
  features: Partial<FeatureSnap>;
}

const SIGNALS: Sig[] = [
  {
    ticker:"ALSEA", price:44.37, pUp:0.606, entry:44.48, stop:42.46, t1:46.50, t2:48.52,
    pctCap:7.9, shares:178, capitalMxn:7898, riskPct:0.36, rrRatio:1.0, edge:1.05,
    reason:"Williams %R oversold · Stoch oversold · 10d drop −8.1% · cerca banda Bollinger baja · bajo SMA20 −7.8%",
    features:{ williams_r:-91, stoch_k:11, ret_10d:-8.1, bb_pct:7, price_vs_sma20:-7.8, rsi_14:32 },
  },
  {
    ticker:"GRUMAB", price:283.56, pUp:0.557, entry:284.27, stop:274.99, t1:293.55, t2:302.83,
    pctCap:5.8, shares:20, capitalMxn:5671, riskPct:0.19, rrRatio:1.0, edge:0.77,
    reason:"Stoch oversold · 10d drop −4.4%",
    features:{ williams_r:-74, stoch_k:14, ret_10d:-4.4, bb_pct:26, price_vs_sma20:-2.1, rsi_14:41 },
  },
  {
    ticker:"GMEXICOB", price:200.0, pUp:0.555, entry:200.50, stop:188.55, t1:212.45, t2:224.40,
    pctCap:5.7, shares:28, capitalMxn:5600, riskPct:0.34, rrRatio:1.0, edge:0.76,
    reason:"Stoch oversold · 10d drop −4.5% · bajo SMA20 −3.9%",
    features:{ williams_r:-72, stoch_k:13, ret_10d:-4.5, bb_pct:22, price_vs_sma20:-3.9, rsi_14:39 },
  },
  {
    ticker:"WALMEX", price:50.86, pUp:0.553, entry:50.99, stop:49.02, t1:52.96, t2:54.92,
    pctCap:5.6, shares:110, capitalMxn:5595, riskPct:0.22, rrRatio:1.0, edge:0.75,
    reason:"Stoch oversold",
    features:{ williams_r:-66, stoch_k:16, ret_10d:-1.8, bb_pct:31, price_vs_sma20:-1.2, rsi_14:44 },
  },
];

const SUMMARY = { nPositions:4, totalInvested:24764, pctInvested:24.8, pctAtRisk:1.09, avgPUp:0.568, avgEdge:0.83 };

const ALL_CANDIDATES = [
  { ticker:"ALSEA",    pUp:0.606, price:44.37   },
  { ticker:"GRUMAB",  pUp:0.557, price:283.56  },
  { ticker:"GMEXICOB",pUp:0.555, price:200.0   },
  { ticker:"WALMEX",  pUp:0.553, price:50.86   },
  { ticker:"GCARSOA1",pUp:0.527, price:133.83  },
  { ticker:"PINFRA",  pUp:0.522, price:276.34  },
  { ticker:"BIMBOA",  pUp:0.508, price:57.09   },
  { ticker:"GFNORTEO",pUp:0.507, price:182.9   },
  { ticker:"GAPB",    pUp:0.491, price:441.57  },
  { ticker:"ORBIA",   pUp:0.488, price:22.2    },
  { ticker:"Q",       pUp:0.475, price:175.0   },
  { ticker:"CEMEXCPO",pUp:0.472, price:21.51   },
  { ticker:"KIMBERA", pUp:0.469, price:38.85   },
  { ticker:"MEGACPO", pUp:0.450, price:60.2    },
  { ticker:"LABB",    pUp:0.450, price:14.97   },
  { ticker:"VOLARA",  pUp:0.443, price:16.36   },
  { ticker:"OMAB",    pUp:0.429, price:245.6   },
  { ticker:"FEMSAUBD",pUp:0.427, price:225.2   },
  { ticker:"ASURB",   pUp:0.418, price:536.74  },
];

// Correlaciones entre señales seleccionadas
const CORR = [
  { from:"ALSEA",    to:"GMEXICOB", corr:0.40 },
  { from:"ALSEA",    to:"GRUMAB",   corr:0.40 },
  { from:"GRUMAB",   to:"GMEXICOB", corr:0.28 },
  { from:"GMEXICOB", to:"WALMEX",   corr:0.22 },
  { from:"ALSEA",    to:"WALMEX",   corr:0.19 },
  { from:"GRUMAB",   to:"WALMEX",   corr:0.21 },
];

// ─── Mini Price Ladder (SVG) ──────────────────────────────────────────────────
function PriceLadder({ entry, stop, t1, t2 }: { entry:number; stop:number; t1:number; t2:number }) {
  const H = 180, W = 68, pad = 16;
  const lo = stop  * 0.995;
  const hi = t2    * 1.005;
  const toY = (p: number) => pad + (1 - (p - lo) / (hi - lo)) * (H - 2*pad);

  const yEntry = toY(entry), yStop = toY(stop), yT1 = toY(t1), yT2 = toY(t2);

  const label = (y: number, text: string, val: number, color: string) => (
    <>
      <line x1={28} y1={y} x2={58} y2={y} stroke={color} strokeWidth={1.5}/>
      <text x={26} y={y+4} textAnchor="end" fontSize={8} fill={color}>{val.toFixed(2)}</text>
      <text x={60} y={y+4} fontSize={7} fill={color}>{text}</text>
    </>
  );

  return (
    <svg width={W} height={H} style={{ overflow:"visible" }}>
      <line x1={40} y1={pad} x2={40} y2={H-pad} stroke="#444" strokeWidth={1}/>
      {label(yT2,    "T2",   t2,    "#22c55e")}
      {label(yT1,    "T1",   t1,    "#86efac")}
      {label(yEntry, "→",    entry, "#f59e0b")}
      {label(yStop,  "SL",   stop,  "#ef4444")}
    </svg>
  );
}

// ─── Card de señal ────────────────────────────────────────────────────────────
function SignalCard({ s, rank }: { s: Sig; rank: number }) {
  const featRows: [string, string, string][] = [
    ["Williams %R", (s.features.williams_r ?? 0).toFixed(0), (s.features.williams_r ?? 0) < -80 ? "🔴 Oversold" : "Neutro"],
    ["Stoch %K",    (s.features.stoch_k    ?? 0).toFixed(0), (s.features.stoch_k    ?? 0) < 20  ? "🔴 Oversold" : "Neutro"],
    ["Ret 10d",     `${(s.features.ret_10d  ?? 0).toFixed(1)}%`, (s.features.ret_10d ?? 0) < -4 ? "↓ Caída" : "Estable"],
    ["BB%",         (s.features.bb_pct     ?? 0).toFixed(0), (s.features.bb_pct     ?? 0) < 20  ? "🔴 Banda baja" : "Neutro"],
    ["vs SMA20",    `${(s.features.price_vs_sma20 ?? 0).toFixed(1)}%`, (s.features.price_vs_sma20 ?? 0) < -3 ? "↓ Bajo MA" : "Neutro"],
    ["RSI(14)",     (s.features.rsi_14     ?? 0).toFixed(0), (s.features.rsi_14     ?? 0) < 35  ? "🔴 Oversold" : "Neutro"],
  ];

  return (
    <Card style={{ flex:1, minWidth:210 }}>
      <CardHeader>
        <Row justify="between" align="center">
          <Row gap={6} align="center">
            <Text weight="bold" size="large">#{rank} {s.ticker}</Text>
            <Pill size="sm">{(s.pUp*100).toFixed(1)}%</Pill>
          </Row>
          <Text tone="secondary" size="small">${s.price.toFixed(2)}</Text>
        </Row>
      </CardHeader>
      <CardBody>
        <Row gap={10} align="start">
          <PriceLadder entry={s.entry} stop={s.stop} t1={s.t1} t2={s.t2}/>
          <Stack gap={10} style={{ flex:1 }}>
            <Grid columns={2} gap={6}>
              <Stat value={`$${s.entry.toFixed(2)}`} label="Entry"  />
              <Stat value={`$${s.stop.toFixed(2)}`}  label="Stop"   tone="danger" />
              <Stat value={`$${s.t1.toFixed(2)}`}   label="T1 (50%)" tone="success" />
              <Stat value={`$${s.t2.toFixed(2)}`}   label="T2 (100%)" tone="success" />
            </Grid>
            <Divider />
            <Grid columns={2} gap={6}>
              <Stat value={`${s.pctCap.toFixed(1)}%`}     label="Capital" />
              <Stat value={`${s.shares}`}                  label="Acciones" />
              <Stat value={`${s.riskPct.toFixed(2)}%`}    label="Riesgo cap" tone="danger" />
              <Stat value={`${s.edge.toFixed(2)}%`}        label="Edge EV" tone="success" />
            </Grid>
            <Divider />
            <Stack gap={2}>
              <Text size="small" weight="semibold">Features</Text>
              {featRows.filter(r => r[2] !== "Neutro" && r[2] !== "Estable").map(([k,v,d]) => (
                <Row key={k} justify="between">
                  <Text size="small" tone="secondary">{k}</Text>
                  <Text size="small">{v} · {d}</Text>
                </Row>
              ))}
            </Stack>
          </Stack>
        </Row>
        {s.reason && (
          <Text size="small" tone="secondary" style={{ marginTop:8 }}>
            {s.reason}
          </Text>
        )}
      </CardBody>
    </Card>
  );
}

// ─── Principal ────────────────────────────────────────────────────────────────
export default function SignalsToday() {
  const [view, setView] = useState<"signals"|"ranking"|"risk">("signals");
  const theme = useHostTheme();

  const rankLabels  = ALL_CANDIDATES.map(c => c.ticker);
  const rankValues  = ALL_CANDIDATES.map(c => parseFloat((c.pUp * 100).toFixed(1)));

  const corrLabels  = CORR.map(c => `${c.from}–${c.to}`);
  const corrValues  = CORR.map(c => parseFloat((c.corr * 100).toFixed(0)));

  const budgetLabels  = [...SIGNALS.map(s => s.ticker), "Cash"];
  const budgetValues  = [...SIGNALS.map(s => parseFloat(s.pctCap.toFixed(1))), parseFloat((100 - SUMMARY.pctInvested).toFixed(1))];

  return (
    <Stack gap={22} style={{ padding: 24, maxWidth: 1050 }}>

      {/* Header */}
      <Stack gap={3}>
        <Row justify="between" align="center">
          <H1>Señales BMV — {META.date.split(" ")[0]}</H1>
          <Pill size="sm">Modelo AUC {META.modelAuc} · Train {META.trainWindow}d</Pill>
        </Row>
        <Text tone="secondary" size="small">
          Capital: ${META.capital.toLocaleString()} MXN · Threshold: P &gt; {(META.threshold*100).toFixed(0)}% ·
          Horizon: {META.horizon} días · Risk Engine: Kelly ¼ + ATR(14) stops
        </Text>
      </Stack>

      <Grid columns={4} gap={12}>
        <Stat value={`${SUMMARY.nPositions}`}                          label="Señales de compra" tone="success" />
        <Stat value={`${SUMMARY.pctInvested.toFixed(1)}%`}             label="Capital a invertir" />
        <Stat value={`${SUMMARY.pctAtRisk.toFixed(2)}%`}              label="Capital en riesgo máx" tone="danger" />
        <Stat value={`${(SUMMARY.avgPUp*100).toFixed(1)}%`}            label="P(subida) promedio" tone="success" />
      </Grid>

      <Divider />

      <Row gap={8}>
        <Pill active={view==="signals"} onClick={() => setView("signals")}>Señales de hoy</Pill>
        <Pill active={view==="ranking"} onClick={() => setView("ranking")}>Ranking 19 tickers</Pill>
        <Pill active={view==="risk"}    onClick={() => setView("risk")}>Riesgo & Correlación</Pill>
      </Row>

      {view === "signals" && (
        <Stack gap={16}>
          <Stack gap={3}>
            <H2>{SIGNALS.length} señales de compra para el lunes</H2>
            <Text tone="secondary" size="small">
              Entry = Open del lunes + 0.25% slippage · Stop = Entry − 1.5×ATR · T1 = Entry + 1.5×ATR (cerrar 50%) · T2 = Entry + 3×ATR (cerrar 100%)
            </Text>
          </Stack>

          <Row gap={12} wrap align="start">
            {SIGNALS.map((s, i) => <SignalCard key={s.ticker} s={s} rank={i+1}/>)}
          </Row>

          <Callout tone="warning" title="Reglas operacionales">
            <Stack gap={4}>
              <Text size="small"><Text weight="semibold" as="span">Entrada:</Text> orden limitada al precio de entry al Open del lunes. Si no se llena en los primeros 30 min, cancelar.</Text>
              <Text size="small"><Text weight="semibold" as="span">Stop loss:</Text> orden stop market inmediata al colocar la posición. No mover el stop hacia abajo.</Text>
              <Text size="small"><Text weight="semibold" as="span">T1:</Text> cerrar el 50% de la posición cuando alcance T1. Mover stop a breakeven.</Text>
              <Text size="small"><Text weight="semibold" as="span">T2:</Text> cerrar el 50% restante en T2 o al final del día {META.horizon} (viernes).</Text>
              <Text size="small"><Text weight="semibold" as="span">ALSEA</Text> es la señal más fuerte (P=60.6%, 5 razones oversold). Verificar que no haya news negativo antes de entrar.</Text>
            </Stack>
          </Callout>
        </Stack>
      )}

      {view === "ranking" && (
        <Stack gap={12}>
          <Stack gap={3}>
            <H2>P(subida 5d) — todos los 19 tickers IPC</H2>
            <Text tone="secondary" size="small">
              Modelo entrenado en los últimos 252 días. Los 4 primeros superan el umbral de P &gt; 53%.
              Los últimos (OMAB, FEMSAUBD, ASURB) son señales implícitas de evitar / posición corta.
            </Text>
          </Stack>
          <BarChart
            categories={rankLabels}
            series={[{ name: "P(subida 5d) %", data: rankValues }]}
            height={260}
            horizontal
            valueSuffix="%"
          />
          <Table
            headers={["#","Ticker","P(subida)","Precio","Señal","Razón"]}
            rows={ALL_CANDIDATES.map((c, i) => [
              i+1,
              <Text weight={i < 4 ? "semibold" : "regular"} as="span">{c.ticker}</Text>,
              <Text weight="semibold" tone={c.pUp > 0.53 ? "primary" : c.pUp < 0.46 ? "secondary" : "primary"} as="span">
                {(c.pUp*100).toFixed(1)}%
              </Text>,
              `$${c.price}`,
              c.pUp > 0.53 ? "COMPRA" : c.pUp < 0.46 ? "EVITAR" : "Neutro",
              c.pUp > 0.53 ? "Oversold" : c.pUp < 0.46 ? "Overbought / sin señal" : "—",
            ])}
            columnAlign={["center","left","right","right","center","left"]}
            rowTone={ALL_CANDIDATES.map(c =>
              c.pUp > 0.53 ? "success" as const : c.pUp < 0.46 ? "danger" as const : undefined
            )}
            striped
          />
        </Stack>
      )}

      {view === "risk" && (
        <Stack gap={14}>
          <H2>Distribución del capital y correlación</H2>
          <Grid columns={2} gap={20}>
            <Stack gap={6}>
              <H3>Allocación del capital (%)</H3>
              <BarChart
                categories={budgetLabels}
                series={[{ name: "% capital", data: budgetValues }]}
                height={190}
                horizontal
                valueSuffix="%"
              />
              <Text size="small" tone="secondary">
                75.2% del capital permanece en cash. Kelly ¼ + tope del 10% por posición produce sizing conservador pero correcto para este nivel de AUC.
              </Text>
            </Stack>

            <Stack gap={6}>
              <H3>Correlación entre señales (últimos 63d)</H3>
              <BarChart
                categories={corrLabels}
                series={[{ name: "Correlación %", data: corrValues }]}
                height={190}
                horizontal
                valueSuffix="%"
              />
              <Text size="small" tone="secondary">
                Todas las correlaciones están por debajo del umbral de 70%, por lo que no se aplicó ninguna penalización de sizing. El portafolio es diversificado: consumo (ALSEA), alimentos (GRUMAB), minería (GMEXICOB), retail (WALMEX).
              </Text>
            </Stack>
          </Grid>

          <Table
            headers={["Métrica","Valor","Umbral","Estado"]}
            rows={[
              ["% Capital invertido",   `${SUMMARY.pctInvested.toFixed(1)}%`, "< 50%",  "OK ✓"],
              ["% Capital en riesgo",   `${SUMMARY.pctAtRisk.toFixed(2)}%`,   "< 5%",   "OK ✓"],
              ["Máx correlación par",   "40%",                                "< 70%",  "OK ✓"],
              ["P(subida) promedio",    `${(SUMMARY.avgPUp*100).toFixed(1)}%`, "> 53%",  "OK ✓"],
              ["Edge promedio",         `${SUMMARY.avgEdge.toFixed(2)}%`,     "> 0%",   "OK ✓"],
              ["# posiciones abiertas", `${SUMMARY.nPositions}`,              "≤ 5",    "OK ✓"],
            ]}
            columnAlign={["left","right","right","center"]}
            rowTone={[
              "success","success","success","success","success","success",
            ]}
            striped
          />

          <Callout tone="info" title="Kelly ¼ — por qué este sizing">
            <Stack gap={4}>
              <Text size="small">
                Con P=56.8% promedio, win ratio 1.36x: Kelly completo = 17%. Kelly ¼ = 4.3–7.9% por posición.
                El Kelly cuarto es la convención estándar en trading cuantitativo para gestionar el riesgo de ruina ante estimaciones imperfectas del modelo.
              </Text>
              <Text size="small">
                Si el modelo mejora (AUC 0.60+), el Kelly aumentará automáticamente. El tope de 10% actúa como floor de seguridad adicional.
              </Text>
            </Stack>
          </Callout>
        </Stack>
      )}

    </Stack>
  );
}
