import { useState } from "react";
import {
  Stack, Row, Grid, H1, H2, H3, Text, Card, CardHeader, CardBody,
  Pill, Stat, Callout, Divider, BarChart, LineChart, Table,
  useHostTheme,
} from "cursor/canvas";

// ─── Estado inicial del paper trading — 2026-06-27 ───────────────────────────
// Semana 1: 4 posiciones PENDING (entran el lunes 2026-06-30)

interface WeekTrade {
  week: number; ticker: string; signalDate: string; entryDate: string | null;
  pUp: number; entry: number; stop: number; t1: number; t2: number;
  status: string; pnlMxn: number; pnlPct: number; capital: number; shares: number;
  events: { date:string; type:string; price:number; pnlMxn:number }[];
}

// Trades de la primera semana (PENDING)
const TRADES: WeekTrade[] = [
  { week:1, ticker:"ALSEA",    signalDate:"2026-06-27", entryDate:null,
    pUp:0.606, entry:44.48, stop:42.46, t1:46.50, t2:48.52,
    status:"PENDING", pnlMxn:0, pnlPct:0, capital:7898, shares:178, events:[] },
  { week:1, ticker:"GRUMAB",   signalDate:"2026-06-27", entryDate:null,
    pUp:0.557, entry:284.27, stop:274.99, t1:293.55, t2:302.83,
    status:"PENDING", pnlMxn:0, pnlPct:0, capital:5671, shares:20, events:[] },
  { week:1, ticker:"GMEXICOB", signalDate:"2026-06-27", entryDate:null,
    pUp:0.555, entry:200.50, stop:188.55, t1:212.45, t2:224.40,
    status:"PENDING", pnlMxn:0, pnlPct:0, capital:5600, shares:28, events:[] },
  { week:1, ticker:"WALMEX",   signalDate:"2026-06-27", entryDate:null,
    pUp:0.553, entry:50.99, stop:49.02, t1:52.96, t2:54.92,
    status:"PENDING", pnlMxn:0, pnlPct:0, capital:5595, shares:110, events:[] },
];

const INITIAL_CAPITAL = 100_000;

// ─── Ejemplo simulado de cómo se vería después de 4 semanas ──────────────────
// (datos hipotéticos para mostrar la estructura — se reemplazarán con datos reales)
const EXAMPLE_HISTORY: WeekTrade[] = [
  { week:0, ticker:"EJEMPLO A", signalDate:"—", entryDate:"Semana 1",
    pUp:0.582, entry:100, stop:97, t1:104.5, t2:109,
    status:"T1_HIT", pnlMxn:225, pnlPct:4.1, capital:5500, shares:50,
    events:[
      {date:"Lunes",type:"ENTRY",price:100,pnlMxn:0},
      {date:"Miércoles",type:"T1",price:104.5,pnlMxn:225},
    ]},
  { week:0, ticker:"EJEMPLO B", signalDate:"—", entryDate:"Semana 1",
    pUp:0.561, entry:200, stop:193, t1:207, t2:214,
    status:"STOP_HIT", pnlMxn:-140, pnlPct:-2.5, capital:5600, shares:20,
    events:[
      {date:"Lunes",type:"ENTRY",price:200,pnlMxn:0},
      {date:"Jueves",type:"STOP",price:193,pnlMxn:-140},
    ]},
];

const STATS_EXAMPLE = {
  nClosed:0, nWins:0, nLosses:0, nT2:0, nStops:0, nExpired:0,
  winRate:0, totalPnl:0, totalRet:0, profitFactor:0, sharpe:0, maxDrawdown:0,
  equityFinal: INITIAL_CAPITAL,
};

// Curva de equity "vacía" hasta ahora — se irá llenando
const EQUITY_START = [{ date:"2026-06-27", equity:100000, pnl:0 }];

// ─── Comandos del flujo semanal ───────────────────────────────────────────────
const WORKFLOW = [
  { day:"Viernes 21:00", cmd:"python scripts/generate_signals.py --capital 100000", note:"Genera señales del modelo" },
  { day:"Viernes 21:01", cmd:"python scripts/paper_trading.py init", note:"Registra las señales en el journal" },
  { day:"Viernes 21:02", cmd:"python scripts/paper_trading.py status", note:"Confirma las 4-5 posiciones PENDING" },
  { day:"Lunes  8:25",   cmd:"[GBM] Órdenes límite de compra + stop market", note:"Manual en la app de GBM" },
  { day:"Lunes  8:30",   cmd:"python scripts/monitor_intraday.py", note:"Inicia el monitor de alertas" },
  { day:"Viernes 15:01", cmd:"python scripts/paper_trading.py settle", note:"Cierra la semana con OHLC reales" },
  { day:"Viernes 15:02", cmd:"python scripts/paper_trading.py report", note:"Revisa el scorecard acumulado" },
];

// ─── Reglas de ejecución ──────────────────────────────────────────────────────
const RULES = [
  { rule:"Entrada",  detail:"Orden LÍMITE al precio de entry al Open del lunes. Si no se ejecuta en 30 min, cancelar.", icon:"→" },
  { rule:"Stop",     detail:"Orden STOP MARKET inmediata al colocar la posición. NUNCA mover el stop hacia abajo.",   icon:"✗" },
  { rule:"T1 (+1R)", detail:"Cerrar 50% de la posición. Mover stop a breakeven (= precio de entrada).",              icon:"◑" },
  { rule:"T2 (+2R)", detail:"Cerrar el 50% restante. Trade completo.",                                               icon:"✓" },
  { rule:"Expiración","detail":"Si al cierre del viernes la posición sigue abierta, cerrar a precio de mercado.",    icon:"○" },
  { rule:"Semanas perdedoras","detail":"Si el mes tiene más de 3 stops: pausar una semana y revisar el modelo.",     icon:"⚠" },
];

// ─── Estado visual de una posición ───────────────────────────────────────────
function StatusBadge({ status }: { status: string }) {
  const tone = status === "T2_HIT"   ? "success" :
               status === "T1_HIT"   ? "success" :
               status === "STOP_HIT" ? "danger"  :
               status === "EXPIRED"  ? "secondary" :
               status === "OPEN"     ? "primary" : "warning";
  const label = status === "PENDING" ? "PENDIENTE" :
                status === "T2_HIT"  ? "✅ T2" :
                status === "T1_HIT"  ? "◑ T1" :
                status === "STOP_HIT"? "✗ STOP" :
                status === "EXPIRED" ? "⏰ EXPIRADO" : status;
  return <Pill size="sm" tone={tone as any}>{label}</Pill>;
}

// ─── Principal ────────────────────────────────────────────────────────────────
export default function PaperTrading() {
  const [view, setView] = useState<"live"|"history"|"how"|"rules">("live");
  const theme = useHostTheme();

  return (
    <Stack gap={22} style={{ padding:24, maxWidth:1060 }}>

      {/* Header */}
      <Stack gap={3}>
        <Row justify="between" align="center">
          <H1>Paper Trading BMV</H1>
          <Row gap={6}>
            <Pill size="sm" tone="warning">Semana 1</Pill>
            <Pill size="sm">Capital: $100,000 MXN</Pill>
          </Row>
        </Row>
        <Text tone="secondary" size="small">
          Simulación sin dinero real · Modelo WoE + Logistic (AUC 0.534) ·
          Horizon: 5 días · Risk Engine: Kelly ¼ + ATR stops
        </Text>
      </Stack>

      {/* Stats */}
      <Grid columns={5} gap={12}>
        <Stat value="$100,000" label="Capital inicial" />
        <Stat value="4"        label="Posiciones semana 1" tone="primary" />
        <Stat value="0"        label="Trades cerrados" tone="secondary" />
        <Stat value="—"        label="Win rate histórico" tone="secondary" />
        <Stat value="$0"       label="PnL acumulado" />
      </Grid>

      <Divider />

      <Row gap={8}>
        <Pill active={view==="live"}    onClick={() => setView("live")}>Semana actual</Pill>
        <Pill active={view==="history"} onClick={() => setView("history")}>Historial</Pill>
        <Pill active={view==="how"}     onClick={() => setView("how")}>Flujo semanal</Pill>
        <Pill active={view==="rules"}   onClick={() => setView("rules")}>Reglas</Pill>
      </Row>

      {view === "live" && (
        <Stack gap={14}>
          <Stack gap={3}>
            <H2>Semana 1 — 2026-06-27 → 2026-07-03</H2>
            <Text tone="secondary" size="small">
              4 posiciones PENDING — entran al Open del lunes 2026-06-30.
              Correr <Text style={{fontFamily:"monospace"}} as="span">settle</Text> el viernes para cerrar con datos reales.
            </Text>
          </Stack>

          <Callout tone="info" title="Pendiente: colocar órdenes el lunes 8:25 AM">
            <Stack gap={4}>
              <Text size="small">Antes de que abra el mercado (8:30 AM hora CDMX), coloca en GBM:</Text>
              {TRADES.map(t => (
                <Text key={t.ticker} size="small" style={{fontFamily:"monospace"}}>
                  {t.ticker}: LÍMITE compra ${t.entry.toFixed(2)} · STOP ${t.stop.toFixed(2)} · {t.shares} acciones
                </Text>
              ))}
            </Stack>
          </Callout>

          <Table
            headers={["Ticker","P(↑5d)","Señal","Entry","Stop","T1","T2","Capital","Estado"]}
            rows={TRADES.map(t => [
              <Text weight="bold" as="span">{t.ticker}</Text>,
              <Text weight="semibold" tone="success" as="span">{(t.pUp*100).toFixed(1)}%</Text>,
              t.signalDate,
              `$${t.entry.toFixed(2)}`,
              <Text tone="danger" as="span">${t.stop.toFixed(2)}</Text>,
              <Text tone="success" as="span">${t.t1.toFixed(2)}</Text>,
              <Text tone="success" as="span">${t.t2.toFixed(2)}</Text>,
              `$${t.capital.toLocaleString()}`,
              <StatusBadge status={t.status} />,
            ])}
            columnAlign={["left","right","center","right","right","right","right","right","center"]}
            striped
          />

          <Grid columns={3} gap={16}>
            <Card>
              <CardHeader>Risk/Reward de la semana</CardHeader>
              <CardBody>
                <Stack gap={8}>
                  <Stat value="$24,764" label="Capital en juego (24.8%)" />
                  <Stat value="$270"    label="Pérdida máxima si todos los stops" tone="danger" />
                  <Stat value="$1,030"  label="Ganancia estimada si todos T1" tone="success" />
                  <Text size="small" tone="secondary">
                    Ratio esperado: ~3.8:1 (ganancias / pérdidas). El risk engine funciona aunque el modelo sea imperfecto.
                  </Text>
                </Stack>
              </CardBody>
            </Card>

            <Card>
              <CardHeader>Razones de las señales</CardHeader>
              <CardBody>
                <Stack gap={6}>
                  {[
                    { t:"ALSEA",    r:"Williams %R oversold, Stoch <20, 10d −8.1%, bajo BB baja, bajo SMA20 −7.8%" },
                    { t:"GRUMAB",   r:"Stoch <20, 10d −4.4%" },
                    { t:"GMEXICOB", r:"Stoch <20, 10d −4.5%, bajo SMA20 −3.9%" },
                    { t:"WALMEX",   r:"Stoch <20" },
                  ].map(x => (
                    <Stack key={x.t} gap={1}>
                      <Text weight="semibold" size="small">{x.t}</Text>
                      <Text tone="secondary" size="small">{x.r}</Text>
                    </Stack>
                  ))}
                </Stack>
              </CardBody>
            </Card>

            <Card>
              <CardHeader>Qué hacer al final de la semana</CardHeader>
              <CardBody>
                <Stack gap={6}>
                  <Text size="small" weight="semibold">Viernes 15:00 (cierre BMV):</Text>
                  <Text size="small" style={{fontFamily:"monospace"}}>
                    python scripts/paper_trading.py settle
                  </Text>
                  <Text size="small" tone="secondary">
                    Descarga los OHLC reales de los 5 días y simula la ejecución exacta de cada posición.
                  </Text>
                  <Text size="small" style={{fontFamily:"monospace"}}>
                    python scripts/paper_trading.py report
                  </Text>
                  <Text size="small" tone="secondary">
                    Muestra el scorecard acumulado con win rate, Sharpe y calibración del modelo.
                  </Text>
                </Stack>
              </CardBody>
            </Card>
          </Grid>
        </Stack>
      )}

      {view === "history" && (
        <Stack gap={12}>
          <H2>Historial de trades cerrados</H2>

          <Callout tone="neutral" title="Sin trades cerrados todavía">
            <Text size="small">
              El historial se llenará automáticamente cuando corras <Text style={{fontFamily:"monospace"}} as="span">python scripts/paper_trading.py settle</Text> al final de cada semana.
              Aquí aparecerán el resultado real de cada trade con eventos detallados.
            </Text>
          </Callout>

          <H3>Así se verá después de la primera semana:</H3>
          <Table
            headers={["#","Ticker","Entrada","Estado","P(↑5d)","PnL MXN","PnL%","¿Modelo acertó?"]}
            rows={EXAMPLE_HISTORY.map((t,i) => [
              i+1,
              <Text weight="bold" as="span">{t.ticker}</Text>,
              t.entryDate,
              <StatusBadge status={t.status}/>,
              `${(t.pUp*100).toFixed(0)}%`,
              <Text tone={t.pnlMxn > 0 ? "success" : "danger"} weight="semibold" as="span">
                {t.pnlMxn > 0 ? "+" : ""}${t.pnlMxn.toLocaleString()}
              </Text>,
              <Text tone={t.pnlPct > 0 ? "success" : "danger"} as="span">
                {t.pnlPct > 0 ? "+" : ""}{t.pnlPct.toFixed(1)}%
              </Text>,
              t.pnlMxn > 0 ? "✅ Sí" : "❌ No",
            ])}
            columnAlign={["center","left","center","center","right","right","right","center"]}
            rowTone={EXAMPLE_HISTORY.map(t => t.pnlMxn > 0 ? "success" as const : "danger" as const)}
            striped
          />
          <Text size="small" tone="tertiary">* Datos hipotéticos para ilustrar el formato.</Text>
        </Stack>
      )}

      {view === "how" && (
        <Stack gap={12}>
          <H2>Flujo semanal — 7 pasos</H2>
          <Text tone="secondary" size="small">
            El pipeline completo de viernes a viernes. Cada semana tarda menos de 5 minutos en gestionar.
          </Text>

          <Table
            headers={["Cuándo","Comando / Acción","Descripción"]}
            rows={WORKFLOW.map(w => [
              <Text weight="semibold" size="small" as="span">{w.day}</Text>,
              <Text size="small" style={{fontFamily:"monospace"}} as="span">{w.cmd}</Text>,
              <Text size="small" tone="secondary" as="span">{w.note}</Text>,
            ])}
            columnAlign={["left","left","left"]}
            rowTone={WORKFLOW.map((_, i) =>
              i === 3 ? "warning" as const : undefined  // GBM manual = amarillo
            )}
            striped
          />

          <Grid columns={2} gap={16}>
            <Callout tone="info" title="Qué mide el paper trading">
              <Stack gap={4}>
                <Text size="small">
                  <Text weight="semibold" as="span">Win rate real:</Text> ¿el modelo predice correctamente cuándo sube?
                  El modelo espera ~52%. Después de 10 semanas tendremos evidencia estadística.
                </Text>
                <Text size="small">
                  <Text weight="semibold" as="span">Calibración:</Text> cuando el modelo dice P=60%, ¿el precio sube el 60% de las veces?
                </Text>
                <Text size="small">
                  <Text weight="semibold" as="span">Sharpe real:</Text> objetivo mínimo 0.5 para considerar el modelo operacional.
                  Si después de 3 meses el Sharpe es &lt; 0, revisar el modelo.
                </Text>
              </Stack>
            </Callout>

            <Callout tone="warning" title="Cuándo pasar a dinero real">
              <Stack gap={4}>
                <Text size="small">Criterios mínimos para transición:</Text>
                <Text size="small">✓ Al menos 20 trades cerrados</Text>
                <Text size="small">✓ Win rate ≥ 50% (significativo)</Text>
                <Text size="small">✓ Sharpe ≥ 0.5</Text>
                <Text size="small">✓ Max drawdown &lt; 5%</Text>
                <Text size="small">✓ Calibración dentro de ±5pp</Text>
                <Text size="small">
                  Con 4 señales/semana: <Text weight="semibold" as="span">~5 semanas</Text> para tener evidencia suficiente.
                </Text>
              </Stack>
            </Callout>
          </Grid>
        </Stack>
      )}

      {view === "rules" && (
        <Stack gap={12}>
          <H2>Reglas del paper trading</H2>
          <Text tone="secondary" size="small">
            Seguir las mismas reglas que seguirías con dinero real. El paper trading solo sirve si es honesto.
          </Text>

          <Table
            headers={["Regla","Detalle"]}
            rows={RULES.map(r => [
              <Row gap={6} align="center">
                <Text size="large">{r.icon}</Text>
                <Text weight="semibold">{r.rule}</Text>
              </Row>,
              <Text size="small">{r.detail}</Text>,
            ])}
            columnAlign={["left","left"]}
            striped
          />

          <Callout tone="danger" title="Las 3 reglas que más importan">
            <Stack gap={4}>
              <Text size="small">
                <Text weight="semibold" as="span">1. No mover el stop hacia abajo.</Text>
                <Text as="span"> Si el stop se activa, se activa. Registrar la pérdida y seguir.</Text>
              </Text>
              <Text size="small">
                <Text weight="semibold" as="span">2. Solo entrar al Open del lunes.</Text>
                <Text as="span"> Si por alguna razón el precio saltó mucho el lunes, no perseguir — cancelar esa señal.</Text>
              </Text>
              <Text size="small">
                <Text weight="semibold" as="span">3. Cerrar todo al viernes.</Text>
                <Text as="span"> El modelo predice a 5 días. Extender por "feeling" invalida la estadística.</Text>
              </Text>
            </Stack>
          </Callout>
        </Stack>
      )}

    </Stack>
  );
}
