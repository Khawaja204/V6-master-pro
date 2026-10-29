import type { ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { screenSymbol } from "@/lib/screen-entry";
import { candleDelta } from "@/lib/delta";
import { matchesMethod, METHODS, type MethodId } from "@/lib/lecture-methods";
import { useHtfMap } from "@/lib/htf-data";
import { Activity, ArrowDownRight, ArrowUpRight, Clock3, Wifi } from "lucide-react";
import {
  type CandleMetrics,
  type StreamStatus,
  type TopUsdtPair,
} from "@/lib/binance-top-usdt";

interface TopUsdtSignalsProps {
  pairs: TopUsdtPair[];
  status: StreamStatus;
  isLoading: boolean;
  lastTickerRefresh: string | null;
  error: string | null;
  selectedSymbol: string | null;
  onSelectPair: (symbol: string) => void;
  strategy?: "Pump" | "Normal";
  onStrategyChange?: (s: "Pump" | "Normal") => void;
}

function formatPrice(value: number | null): string {
  if (value === null) return "—";
  const fractionDigits = value >= 100 ? 2 : value >= 1 ? 4 : 6;
  return `$${value.toLocaleString("en-US", { maximumFractionDigits: fractionDigits })}`;
}

function formatPercent(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatQuoteVolume(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatDeltaPct(value: number | null): string {
  if (value === null) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function formatMetric(value: number | null, digits = 2): string {
  return value === null ? "—" : value.toFixed(digits);
}

function priceMetricCell(value: number | null): ReactNode {
  return <span className="mono text-[10px] text-slate-300">{formatPrice(value)}</span>;
}

function statusLabel(status: StreamStatus): string {
  switch (status) {
    case "connected": return "STREAM CONNECTED";
    case "connecting": return "CONNECTING";
    case "reconnecting": return "RECONNECTING";
    case "error": return "STREAM ERROR";
    case "disconnected": return "DISCONNECTED";
    default: return "LOADING";
  }
}

function metricCell(value: number | null, digits = 2): ReactNode {
  return <span className="mono text-[10px] text-slate-300">{formatMetric(value, digits)}</span>;
}

function intervalCells(metrics: CandleMetrics | null): ReactNode {
  const met = metrics?.conditionMet ?? false;
  return (
    <>
      <td className="px-3 py-3">{priceMetricCell(metrics?.ema21 ?? null)}</td>
      <td className="px-3 py-3">{priceMetricCell(metrics?.ema50 ?? null)}</td>
      <td className="px-3 py-3">{metricCell(metrics?.rsi14 ?? null)}</td>
      <td className="px-3 py-3">{metricCell(metrics?.rvol ?? null)}</td>
      <td className="px-3 py-3">
        <span className={`whitespace-nowrap rounded-md px-2 py-1 text-[9px] font-semibold ${met ? "bg-[rgba(47,207,176,.1)] teal-text" : "bg-white/[.04] text-slate-500"}`}>
          {met ? "bot condition met" : "not met"}
        </span>
      </td>
    </>
  );
}

export function TopUsdtSignals({
  pairs,
  status,
  isLoading,
  lastTickerRefresh,
  error,
  selectedSymbol,
  onSelectPair,
  strategy,
  onStrategyChange,
}: TopUsdtSignalsProps) {
  const [mode, setMode] = useState<"Pump" | "Normal">(strategy ?? "Pump");
  const [method, setMethod] = useState<MethodId | null>(null);
  const pumpNow = useMemo(() => new Set(
    pairs.filter((p) => screenSymbol(p.symbol, p.candles?.["15m"] ?? []).pump).map((p) => p.symbol),
  ), [pairs]);
  const prevPump = useRef<Set<string> | null>(null);
  const [pumpAlerts, setPumpAlerts] = useState<string[]>([]);
  const canNotify = typeof Notification !== "undefined";
  const [notifyOn, setNotifyOn] = useState<boolean>(canNotify && Notification.permission === "granted");
  useEffect(() => {
    if (prevPump.current === null) {
      if (pairs.length) prevPump.current = pumpNow;
      return;
    }
    const before = prevPump.current;
    prevPump.current = pumpNow;
    const fresh = [...pumpNow].filter((sym) => !before.has(sym)).map((sym) => sym.replace("USDT", ""));
    if (!fresh.length) return;
    const stamp = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    setPumpAlerts((prev) => [...fresh.map((c) => `${stamp} · ${c}`), ...prev].slice(0, 8));
    if (notifyOn) {
      try {
        new Notification("Pump condition met", { body: `${fresh.join(", ")} · screening only, not a signal` });
      } catch {
        // Some mobile browsers do not allow page notifications; the banner still shows it.
      }
    }
  }, [pumpNow, notifyOn, pairs.length]);
  const enableNotify = async () => {
    if (!canNotify) return;
    const result = await Notification.requestPermission();
    setNotifyOn(result === "granted");
  };
  const htfMap = useHtfMap(pairs.map((p) => p.symbol));
  const visiblePairs = useMemo(() => {
    return pairs.filter((pair) => {
      if (method) return matchesMethod(method, pair.candles?.["15m"] ?? [], pair.candles?.["1h"] ?? [], htfMap[pair.symbol]);
      const r = screenSymbol(pair.symbol, pair.candles?.["15m"] ?? []);
      return mode === "Pump" ? r.pump : r.normal;
    });
  }, [pairs, mode, method, htfMap]);
  const refreshLabel = lastTickerRefresh
    ? new Date(lastTickerRefresh).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : "waiting";

  return (
    <section className="panel min-w-0 overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[.07] px-4 py-4">
        <div>
          <div className="eyebrow">Top 20 USDT pairs · 24h quote volume</div>
          <div className="flex flex-wrap items-center gap-2 px-4 pb-3">
            {(["Pump", "Normal"] as const).map((m) => (
              <button key={m} type="button" onClick={() => setMode(m)} className={`rounded-md border px-3 py-1 text-[10px] font-semibold ${mode === m ? "border-[rgba(47,207,176,.3)] teal-text" : "border-white/[.08] text-slate-500"}`}>{m}</button>
            ))}
            <span className="mono text-[9px] text-slate-500">Screening only, not a signal</span>
            {METHODS.map((m) => (
              <button key={m.id} type="button" onClick={() => setMethod(method === m.id ? null : m.id)} className={`rounded-md border px-3 py-1 text-[10px] font-semibold ${method === m.id ? "border-[rgba(246,190,81,.4)] amber-text" : "border-white/[.08] text-slate-500"}`}>{m.label}</button>
            ))}
            {method && (
              <span className="mono text-[9px] text-[hsl(var(--primary))]">
                Matching now ({visiblePairs.length}): {visiblePairs.map((p) => p.baseAsset).join(", ") || "none"} · these rows are in the table below
              </span>
            )}
          </div>
          <p className="mt-1 text-[11px] text-slate-400">
            Binance public market data · ranking refreshes every 10 minutes · closed candles only
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span className="flex items-center gap-1.5 mono text-[9px] text-slate-500">
            <Clock3 size={12} />
            Ticker updated {refreshLabel}
          </span>
          <span className={`flex items-center gap-1.5 mono text-[9px] ${status === "connected" ? "teal-text" : "text-slate-500"}`}>
            {status === "connected" ? <Wifi size={12} /> : <Activity size={12} />}
            {statusLabel(status)}
          </span>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 border-b border-white/[.07] px-4 py-3">
        <span className="text-[10px] font-semibold text-slate-300">Pump alerts</span>
        {canNotify && !notifyOn && (
          <button type="button" onClick={enableNotify} className="rounded-md border border-white/[.08] px-2.5 py-1 text-[9px] text-slate-400 hover:text-slate-200">Enable notifications</button>
        )}
        {pumpAlerts.length ? pumpAlerts.map((a, i) => (
          <span key={`${a}-${i}`} className="mono text-[9px] teal-text">{a}</span>
        )) : (
          <span className="mono text-[9px] text-slate-600">No new Pump condition yet. Checked on every closed 15m candle.</span>
        )}
      </div>
      {error && (
        <div role="status" className="border-b border-amber-500/10 bg-amber-500/[.04] px-4 py-2 text-[10px] text-amber-200">
          Binance data is incomplete: {error}
        </div>
      )}

      <div className="mobile-scroll overflow-x-auto">
        <table className="w-full min-w-[1760px] border-collapse">
          <thead>
            <tr className="eyebrow text-left">
              <th rowSpan={2} className="px-4 py-3">#</th>
              <th rowSpan={2} className="px-3 py-3">Pair</th>
              <th rowSpan={2} className="px-3 py-3">Last price</th>
              <th rowSpan={2} className="px-3 py-3">24h</th>
              <th rowSpan={2} className="px-3 py-3">24h quote vol</th>
              <th rowSpan={2} className="px-3 py-3">15m Δ%</th>
              <th colSpan={5} className="border-l border-white/[.07] px-3 py-2 text-center">15m · closed candles</th>
              <th colSpan={5} className="border-l border-white/[.07] px-3 py-2 text-center">1h · closed candles</th>
              <th rowSpan={2} className="px-3 py-3">Chart</th>
            </tr>
            <tr className="eyebrow text-left">
              {["EMA21", "EMA50", "RSI14", "RVOL", "Condition"].map((label) => (
                <th key={`15m-${label}`} className="px-3 py-2">{label}</th>
              ))}
              {["EMA21", "EMA50", "RSI14", "RVOL", "Condition"].map((label) => (
                <th key={`1h-${label}`} className="border-l border-white/[.07] px-3 py-2">{label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visiblePairs.map((pair, index) => {
              const selected = pair.symbol === selectedSymbol;
              return (
                <tr
                  key={pair.symbol}
                  onClick={() => onSelectPair(pair.symbol)}
                  className={`cursor-pointer border-t border-white/[.045] transition-colors hover:bg-white/[.025] ${selected ? "bg-[rgba(47,207,176,.045)]" : ""} ${method ? "shadow-[inset_3px_0_0_rgba(246,190,81,.85)] bg-[rgba(246,190,81,.03)]" : ""}`}
                  data-testid={`row-top-usdt-${pair.symbol.toLowerCase()}`}
                >
                  <td className="px-4 py-3 mono text-[10px] text-slate-600">{String(index + 1).padStart(2, "0")}</td>
                  <td className="px-3 py-3">
                    <span className="font-semibold text-[11px] text-slate-200">{pair.baseAsset}</span>
                    <span className="ml-1 mono text-[9px] text-slate-600">/ USDT</span>
                  </td>
                  <td className="px-3 py-3 mono text-[10px] text-slate-300">{formatPrice(pair.lastPrice)}</td>
                  <td className={`px-3 py-3 mono text-[10px] ${pair.change24h >= 0 ? "positive" : "negative"}`}>
                    <span className="inline-flex items-center gap-1">
                      {pair.change24h >= 0 ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                      {formatPercent(pair.change24h)}
                    </span>
                  </td>
                  <td className="px-3 py-3 mono text-[10px] text-slate-400">{formatQuoteVolume(pair.quoteVolume24h)}</td>
                  <td className="px-3 py-3 mono text-[10px] text-slate-300">{formatDeltaPct(candleDelta(pair.candles["15m"]).at(-1)?.deltaPct ?? null)}</td>
                  {intervalCells(pair.metrics["15m"])}
                  {intervalCells(pair.metrics["1h"])}
                  <td className="px-3 py-3">
                    <button type="button" onClick={(e) => { e.stopPropagation(); onSelectPair(pair.symbol); }} className="rounded-md border border-white/[.08] px-2 py-1 text-[9px] font-semibold text-slate-300 hover:text-[hsl(var(--primary))]">Open chart</button>
                  </td>
                </tr>
              );
            })}
            {isLoading && visiblePairs.length === 0 && (
              <tr>
                <td colSpan={17} className="px-4 py-12 text-center text-[11px] text-slate-500">
                  Loading Binance ticker and closed-candle data…
                </td>
              </tr>
            )}
            {!isLoading && visiblePairs.length === 0 && (
              <tr>
                <td colSpan={17} className="px-4 py-12 text-center text-[11px] text-slate-500">
                  No pairs match the {mode} filter right now.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/[.07] px-4 py-3">
        <p className="mono text-[9px] text-slate-500">
          close &gt; EMA21 and close &gt; EMA50 and RSI14 &gt;= 50 and RVOL &gt;= 1.5
        </p>
        <p className="text-[10px] text-slate-500">Informational only. Not financial advice.</p>
      </div>
    </section>
  );
}
