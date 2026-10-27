import type { ReactNode } from "react";
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
              <button key={m} type="button" onClick={() => onStrategyChange?.(m)} className={`rounded-md border px-3 py-1 text-[10px] font-semibold ${(strategy ?? "Pump") === m ? "border-[rgba(47,207,176,.3)] teal-text" : "border-white/[.08] text-slate-500"}`}>{m}</button>
            ))}
            <span className="mono text-[9px] text-slate-500">Screening only, not a signal</span>
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

      {error && (
        <div role="status" className="border-b border-amber-500/10 bg-amber-500/[.04] px-4 py-2 text-[10px] text-amber-200">
          Binance data is incomplete: {error}
        </div>
      )}

      <div className="mobile-scroll overflow-x-auto">
        <table className="w-full min-w-[1640px] border-collapse">
          <thead>
            <tr className="eyebrow text-left">
              <th rowSpan={2} className="px-4 py-3">#</th>
              <th rowSpan={2} className="px-3 py-3">Pair</th>
              <th rowSpan={2} className="px-3 py-3">Last price</th>
              <th rowSpan={2} className="px-3 py-3">24h</th>
              <th rowSpan={2} className="px-3 py-3">24h quote vol</th>
              <th colSpan={5} className="border-l border-white/[.07] px-3 py-2 text-center">15m · closed candles</th>
              <th colSpan={5} className="border-l border-white/[.07] px-3 py-2 text-center">1h · closed candles</th>
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
            {pairs.map((pair, index) => {
              const selected = pair.symbol === selectedSymbol;
              return (
                <tr
                  key={pair.symbol}
                  onClick={() => onSelectPair(pair.symbol)}
                  className={`cursor-pointer border-t border-white/[.045] transition-colors hover:bg-white/[.025] ${selected ? "bg-[rgba(47,207,176,.045)]" : ""}`}
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
                  {intervalCells(pair.metrics["15m"])}
                  {intervalCells(pair.metrics["1h"])}
                </tr>
              );
            })}
            {isLoading && pairs.length === 0 && (
              <tr>
                <td colSpan={15} className="px-4 py-12 text-center text-[11px] text-slate-500">
                  Loading Binance ticker and closed-candle data…
                </td>
              </tr>
            )}
            {!isLoading && pairs.length === 0 && (
              <tr>
                <td colSpan={15} className="px-4 py-12 text-center text-[11px] text-slate-500">
                  No eligible USDT pairs are available.
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
