import { useState } from "react";
import {
  Stack, Row, Grid, H1, H2, H3, Text, Card, CardHeader, CardBody,
  Pill, Stat, Callout, Divider, Table, useHostTheme,
} from "cursor/canvas";

// ─── Estado al 2026-06-27 13:58 ───────────────────────────────────────────────
// Fuente: monitor_state.json generado por monitor_intraday.py --once

interface Position {
  ticker: string; entry: number; stop: number; stopCurrent: number;
  t1: number; t2: number; price: number; priceHigh: number;
  pnlPct: number; pnlMxn: number; state: string;
  shares: number; capitalMxn: number; pctCap: number; pUp: number;
}

const POSITIONS: Position[] = [
  { ticker:"ALSEA",    entry:44.48, stop:42.46, stopCurrent:42.46, t1:46.50, t2:48.52,
    price:44.46, priceHigh:44.46, pnlPct:-0.04, pnlMxn:-4,    state:"OPEN",
    shares:178, capitalMxn:7898, pctCap:7.9, pUp:0.606 },
  { ticker:"GRUMAB",   entry:284.27, stop:274.99, stopCurrent:274.99, t1:293.55, t2:302.83,
    price:283.18, priceHigh:283.18, pnlPct:-0.38, pnlMxn:-22,  state:"OPEN",
    shares:20, capitalMxn:5671, pctCap:5.8, pUp:0.557 },
  { ticker:"GMEXICOB", entry:200.50, stop:188.55, stopCurrent:188.55, t1:212.45, t2:224.40,
    price:200.13, priceHigh:200.13, pnlPct:-0.18, pnlMxn:-10,  state:"OPEN",
    shares:28, capitalMxn:5600, pctCap:5.7, pUp:0.555 },
  { ticker:"WALMEX",   entry:50.99, stop:49.02, stopCurrent:49.02, t1:52.96, t2:54.92,
    price:50.80, priceHigh:50.80, pnlPct:-0.37, pnlMxn:-21,   state:"OPEN",
    shares:110, capitalMxn:5595, pctCap:5.6, pUp:0.553 },
];

const TOTAL_CAPITAL = 100_000;
const TOTAL_INVESTED = 24764;

// Historial de alertas (vacío — primer día)
const ALERT_LOG: { time:string; ticker:string; level:string; price:number; msg:string }[] = [];

// ─── SVG Price Bar ────────────────────────────────────────────────────────────
function PriceBar({ pos }: { pos: Position }) {
  const W = 280, H = 48;
  const lo = pos.stop   * 0.99;
  const hi = pos.t2     * 1.01;
  const toX = (p: number) => ((p - lo) / (hi - lo)) * W;

  const xEntry  = toX(pos.entry);
  const xStop   = toX(pos.stop);
  const xT1     = toX(pos.t1);
  const xT2     = toX(pos.t2);
  const xPrice  = Math.max(2, Math.min(W - 2, toX(pos.price)));

  // zona de ganancia (entry → T2) en verde suave, zona de pérdida en rojo suave
  return (
    <svg width={W} height={H} style={{ overflow:"visible" }}>
      {/* Fondo zonas */}
      <rect x={0}       y={16} width={xEntry} height={8} fill="#ef444420" rx={2}/>
      <rect x={xEntry}  y={16} width={xT2 - xEntry} height={8} fill="#22c55e20" rx={2}/>

      {/* Líneas de niveles */}
      <line x1={xStop}  y1={8} x2={xStop}  y2={40} stroke="#ef4444" strokeWidth={1.5} strokeDasharray="3,2"/>
      <line x1={xEntry} y1={8} x2={xEntry} y2={40} stroke="#f59e0b" strokeWidth={2}/>
      <line x1={xT1}    y1={8} x2={xT1}    y2={40} stroke="#86efac" strokeWidth={1.5}/>
      <line x1={xT2}    y1={8} x2={xT2}    y2={40} stroke="#22c55e" strokeWidth={2}/>

      {/* Etiquetas */}
      <text x={xStop-2}  y={7}  textAnchor="end"    fontSize={7} fill="#ef4444">SL</text>
      <text x={xEntry-2} y={7}  textAnchor="end"    fontSize={7} fill="#f59e0b">Entry</text>
      <text x={xT1+2}    y={7}  textAnchor="start"  fontSize={7} fill="#86efac">T1</text>
      <text x={xT2+2}    y={7}  textAnchor="start"  fontSize={7} fill="#22c55e">T2</text>

      {/* Precio actual */}
      <circle cx={xPrice} cy={20} r={5}
        fill={pos.pnlPct >= 0 ? "#22c55e" : "#ef4444"}
        stroke="white" strokeWidth={1}/>
      <text x={xPrice} y={38} textAnchor="middle" fontSize={8}
        fill={pos.pnlPct >= 0 ? "#22c55e" : "#ef4444"}>
        ${pos.price.toFixed(2)}
      </text>
    </svg>
  );
}

// ─── Card de posición ─────────────────────────────────────────────────────────
function PositionCard({ pos }: { pos: Position }) {
  const stopPct  = ((pos.entry - pos.stop) / pos.entry * 100).toFixed(1);
  const t1Pct    = ((pos.t1    - pos.entry) / pos.entry * 100).toFixed(1);
  const t2Pct    = ((pos.t2    - pos.entry) / pos.entry * 100).toFixed(1);

  const stateColor = pos.state === "T2_HIT"   ? "success" :
                     pos.state === "T1_HIT"   ? "success" :
                     pos.state === "STOP_HIT" ? "danger"  : "primary";

  const pnlTone = pos.pnlPct >= 0 ? "success" as const : "danger" as const;

  return (
    <Card style={{ flex:1, minWidth:280 }}>
      <CardHeader>
        <Row justify="between" align="center">
          <Row gap={6} align="center">
            <Text weight="bold" size="large">{pos.ticker}</Text>
            <Pill size="sm">{(pos.pUp*100).toFixed(1)}%</Pill>
            <Pill size="sm" tone={stateColor as any}>{pos.state}</Pill>
          </Row>
          <Text tone={pnlTone} weight="semibold">
            {pos.pnlPct > 0 ? "+" : ""}{pos.pnlPct.toFixed(2)}%
          </Text>
        </Row>
      </CardHeader>
      <CardBody>
        <Stack gap={10}>
          {/* Barra de niveles */}
          <PriceBar pos={pos}/>

          <Grid columns={4} gap={6}>
            <Stat value={`$${pos.stop.toFixed(2)}`}  label={`SL −${stopPct}%`} tone="danger" />
            <Stat value={`$${pos.entry.toFixed(2)}`} label="Entry"    />
            <Stat value={`$${pos.t1.toFixed(2)}`}    label={`T1 +${t1Pct}%`} tone="success" />
            <Stat value={`$${pos.t2.toFixed(2)}`}    label={`T2 +${t2Pct}%`} tone="success" />
          </Grid>

          <Divider/>

          <Grid columns={3} gap={6}>
            <Stat value={`${pos.shares}`}              label="Acciones" />
            <Stat value={`$${pos.capitalMxn.toLocaleString()}`} label="Capital" />
            <Stat value={`${pos.pnlMxn > 0 ? "+" : ""}$${pos.pnlMxn.toLocaleString()}`}
                  label="PnL MXN" tone={pnlTone} />
          </Grid>

          {/* Instrucciones dinámicas según estado */}
          {pos.state === "OPEN" && (
            <Callout tone="neutral" title="Acción: mantener">
              <Text size="small">
                Stop en ${pos.stopCurrent.toFixed(2)} activo.
                Esperar a T1 (${pos.t1.toFixed(2)}) para cerrar 50% y mover stop a breakeven.
              </Text>
            </Callout>
          )}
          {pos.state === "T1_HIT" && (
            <Callout tone="success" title="T1 alcanzado — stop movido a breakeven">
              <Text size="small">
                50% vendido. Stop movido a ${pos.entry.toFixed(2)} (breakeven).
                Esperar T2 (${pos.t2.toFixed(2)}) o expiración en día 5.
              </Text>
            </Callout>
          )}
          {pos.state === "T2_HIT" && (
            <Callout tone="success" title="T2 alcanzado — posición cerrada ✅">
              <Text size="small">Trade completo. PnL: ${pos.pnlMxn.toLocaleString()} MXN.</Text>
            </Callout>
          )}
          {pos.state === "STOP_HIT" && (
            <Callout tone="danger" title="Stop activado — posición cerrada">
              <Text size="small">
                Stop en ${pos.stop.toFixed(2)} ejecutado. PnL: ${pos.pnlMxn.toLocaleString()} MXN.
              </Text>
            </Callout>
          )}
        </Stack>
      </CardBody>
    </Card>
  );
}

// ─── Principal ────────────────────────────────────────────────────────────────
export default function MonitorDashboard() {
  const [view, setView] = useState<"positions"|"alerts"|"commands">("positions");
  const theme = useHostTheme();

  const totalPnl  = POSITIONS.reduce((s, p) => s + p.pnlMxn, 0);
  const openCount = POSITIONS.filter(p => p.state === "OPEN" || p.state === "T1_HIT").length;

  const alertTypes = [
    { level:"STOP_HIT",  icon:"🔴", color:"danger",  desc:"Precio ≤ stop actual",              accion:"Cerrar 100% — pérdida limitada",            sound:"Sosumi"  },
    { level:"T1_HIT",    icon:"🟡", color:"success", desc:"Precio ≥ T1",                        accion:"Cerrar 50%, mover stop a breakeven",        sound:"Ping"    },
    { level:"T2_HIT",    icon:"🟢", color:"success", desc:"Precio ≥ T2",                        accion:"Cerrar 100% restante — ganancia completa",  sound:"Hero"    },
    { level:"PULLBACK",  icon:"⚠️", color:"warning", desc:"Posición T1-hit revierte a entry",   accion:"Vigilar stop de breakeven",                sound:"Bottle"  },
    { level:"EXPIRED",   icon:"⏰", color:"secondary",desc:"5 días transcurridos",              accion:"Cerrar manualmente a precio de mercado",    sound:"default" },
  ];

  const commands = [
    { cmd:"python scripts/generate_signals.py --capital 100000", desc:"Generar señales del próximo lunes (correr viernes nocturno)" },
    { cmd:"python scripts/monitor_intraday.py",                   desc:"Iniciar monitor continuo (cada 5 min, durante horario BMV)" },
    { cmd:"python scripts/monitor_intraday.py --interval 2",      desc:"Monitor cada 2 min (más responsivo)" },
    { cmd:"python scripts/monitor_intraday.py --once",            desc:"Un ciclo y salir (para debug / testing)" },
    { cmd:"python scripts/monitor_intraday.py --reset",           desc:"Resetear estado guardado y recargar señales" },
    { cmd:"python scripts/run_woe.py",                            desc:"Re-correr análisis WoE con datos frescos" },
    { cmd:"python scripts/run_model.py",                          desc:"Re-entrenar y validar modelo con historial completo" },
  ];

  return (
    <Stack gap={22} style={{ padding:24, maxWidth:1050 }}>

      {/* Header */}
      <Stack gap={3}>
        <Row justify="between" align="center">
          <H1>Monitor Intraday BMV</H1>
          <Row gap={6}>
            <Pill size="sm" tone={openCount > 0 ? "success" : "secondary"}>
              {openCount} posiciones activas
            </Pill>
            <Pill size="sm">2026-06-27 13:58 CST</Pill>
          </Row>
        </Row>
        <Text tone="secondary" size="small">
          Polling cada 5 min · Notificaciones macOS · Horario: 8:30–15:00 CT ·
          Horizon: 5 días (vence viernes 2026-07-03)
        </Text>
      </Stack>

      <Grid columns={4} gap={12}>
        <Stat value={`${openCount}`}    label="Posiciones abiertas" />
        <Stat value={`$${TOTAL_INVESTED.toLocaleString()}`} label="Capital invertido" />
        <Stat value={totalPnl > 0 ? `+$${totalPnl}` : `$${totalPnl}`}
              label="PnL actual MXN" tone={totalPnl >= 0 ? "success" : "danger"} />
        <Stat value={`${((TOTAL_CAPITAL - TOTAL_INVESTED)/TOTAL_CAPITAL*100).toFixed(1)}%`}
              label="Cash disponible" />
      </Grid>

      <Divider />

      <Row gap={8}>
        <Pill active={view==="positions"} onClick={() => setView("positions")}>Posiciones</Pill>
        <Pill active={view==="alerts"}    onClick={() => setView("alerts")}>Tipos de alerta</Pill>
        <Pill active={view==="commands"}  onClick={() => setView("commands")}>Comandos</Pill>
      </Row>

      {view === "positions" && (
        <Stack gap={16}>
          <Stack gap={3}>
            <H2>Estado actual — {POSITIONS.length} posiciones</H2>
            <Text tone="secondary" size="small">
              Datos de cierre 2026-06-26. El monitor actualiza los precios cada 5 min con datos intraday de Yahoo Finance.
              El punto de color en cada barra es el precio actual.
            </Text>
          </Stack>

          <Row gap={12} wrap align="start">
            {POSITIONS.map(p => <PositionCard key={p.ticker} pos={p}/>)}
          </Row>

          <Callout tone="info" title="Estado del portafolio — día 1">
            <Stack gap={4}>
              <Text size="small">
                Todas las posiciones abrieron ligeramente por debajo de la entrada (diferencial bid-ask + apertura).
                Este comportamiento es normal. Las señales se basan en mean reversion a <Text weight="semibold" as="span">5 días</Text>,
                no en el movimiento del primer día.
              </Text>
              <Text size="small">
                <Text weight="semibold" as="span">ALSEA</Text> es la posición de mayor convicción (P=60.6%): está 7.8% bajo su SMA20 y en zona oversold extrema en Williams %R y Stochastic.
                La media de posiciones similares históricamente revierte en 2–4 días.
              </Text>
            </Stack>
          </Callout>
        </Stack>
      )}

      {view === "alerts" && (
        <Stack gap={12}>
          <H2>Sistema de alertas automáticas</H2>
          <Text tone="secondary" size="small">
            El monitor evalúa cada posición en cada ciclo y envía notificaciones nativas de macOS.
            Las alertas también se guardan en data/monitor_log.jsonl.
          </Text>

          <Table
            headers={["Nivel","Condición","Acción requerida","Sonido macOS"]}
            rows={alertTypes.map(a => [
              <Row gap={4} align="center"><Text>{a.icon}</Text><Text weight="semibold">{a.level}</Text></Row>,
              a.desc,
              a.accion,
              <Text tone="secondary" size="small">{a.sound}</Text>,
            ])}
            columnAlign={["left","left","left","center"]}
            rowTone={alertTypes.map(a => a.level === "STOP_HIT" ? "danger" as const : a.level.includes("HIT") ? "success" as const : undefined)}
            striped
          />

          <H3 style={{ marginTop:8 }}>Lógica de stops progresivos</H3>
          <Table
            headers={["Evento","Stop antes","Stop después","Unidades"]}
            rows={[
              ["Inicio",     "Entry − 1.5×ATR",  "Entry − 1.5×ATR", "100% (todas)"],
              ["T1 alcanzado","Entry − 1.5×ATR", "Entry (breakeven)", "50% restantes"],
              ["T2 alcanzado","Entry (BE)",       "Posición cerrada", "0% — trade completo"],
              ["STOP_HIT",   "Nivel actual",      "Posición cerrada", "0% — pérdida limitada"],
            ]}
            columnAlign={["left","left","left","left"]}
            striped
          />

          {ALERT_LOG.length === 0 ? (
            <Callout tone="neutral" title="Sin alertas aún — primer día">
              <Text size="small">
                El log de alertas (data/monitor_log.jsonl) está vacío. Las posiciones están abiertas y dentro de rango normal.
              </Text>
            </Callout>
          ) : (
            <Table
              headers={["Hora","Ticker","Nivel","Precio","Mensaje"]}
              rows={ALERT_LOG.map(a => [
                a.time.slice(11, 19),
                a.ticker,
                a.level,
                `$${a.price.toFixed(2)}`,
                a.msg,
              ])}
              columnAlign={["center","center","center","right","left"]}
              striped
            />
          )}
        </Stack>
      )}

      {view === "commands" && (
        <Stack gap={12}>
          <H2>Comandos del pipeline completo</H2>
          <Text tone="secondary" size="small">
            Todos los scripts están en la carpeta scripts/. Activar el venv antes: source venv/bin/activate
          </Text>

          <Table
            headers={["Comando","Descripción"]}
            rows={commands.map(c => [
              <Text size="small" style={{ fontFamily:"monospace" }}>{c.cmd}</Text>,
              <Text size="small">{c.desc}</Text>,
            ])}
            columnAlign={["left","left"]}
            striped
          />

          <Callout tone="success" title="Pipeline completo — flujo semanal recomendado">
            <Stack gap={4}>
              <Text size="small"><Text weight="semibold" as="span">Viernes 21:00:</Text> correr generate_signals.py → revisar signals-today canvas.</Text>
              <Text size="small"><Text weight="semibold" as="span">Lunes 8:25:</Text> colocar órdenes límite en GBM según entry prices. Correr monitor_intraday.py.</Text>
              <Text size="small"><Text weight="semibold" as="span">Lunes–Viernes:</Text> el monitor corre en background. Notificaciones macOS si se toca stop o target.</Text>
              <Text size="small"><Text weight="semibold" as="span">Viernes (cierre):</Text> cerrar cualquier posición abierta que no haya expirado. Re-ejecutar generate_signals.py para la siguiente semana.</Text>
            </Stack>
          </Callout>

          <Callout tone="info" title="Estructura de archivos generados">
            <Stack gap={2}>
              {[
                ["data/signals_today.json",    "Señales del modelo con sizing"],
                ["data/monitor_state.json",    "Estado actual de cada posición (se actualiza en cada ciclo)"],
                ["data/monitor_log.jsonl",     "Historial completo de alertas"],
                ["data/woe_results.json",      "Análisis WoE + IV por feature"],
                ["data/model_results.json",    "Walk-forward AUC por fold"],
                ["data/model_predictions.csv", "13,167 predicciones out-of-sample"],
                ["data/backtest_results.json", "Backtest heurístico (referencia histórica)"],
              ].map(([f, d]) => (
                <Row key={f} justify="between" gap={8}>
                  <Text size="small" style={{ fontFamily:"monospace" }}>{f}</Text>
                  <Text size="small" tone="secondary">{d}</Text>
                </Row>
              ))}
            </Stack>
          </Callout>
        </Stack>
      )}

    </Stack>
  );
}
