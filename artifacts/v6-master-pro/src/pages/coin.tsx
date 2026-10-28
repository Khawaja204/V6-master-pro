import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation } from "wouter";
import {
  Activity,
  ArrowLeft,
  ArrowDownRight,
  ArrowUpRight,
  Clock3,
  Search,
  Wifi,
} from "lucide-react";
import {
  calculateCoinCandleMetrics,
  fetchClosedCoinCandles,
  fetchCoinTicker,
  fetchRecentCoinTrades,
  fetchUsdtSpotPairs,
  searchUsdtSpotPairs,
  type ClosedCoinCandle,
  type CoinCandleMetrics,
  type CoinInterval,
  type CoinTicker,
  type RecentCoinTrade,
  type UsdtSpotPair,
} from "@/lib/binance-coin";

type FeedErrors = Partial<Record<"ticker" | "15m" | "1h" | "trades", string>>;

const formatPrice = (value: number | null | undefined) => {
  if (value == null || !Number.isFinite(value)) return "—";
  return `$${value.toLocaleString("en-US", {
    minimumFractionDigits: value < 1 ? 4 : 2,
    maximumFractionDigits: value < 1 ? 8 : 4,
  })}`;
};

const formatNumber = (value: number | null | undefined, digits = 2) =>
  value == null || !Number.isFinite(value) ? "—" : value.toLocaleString("en-US", { maximumFractionDigits: digits });

const formatVolume = (value: number) =>
  value.toLocaleString("en-US", { maximumFractionDigits: 4 });

const formatTime = (value: number) =>
  new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });

function MetricValue({ label, value, testId }: { label: string; value: string; testId: string }) {
  return (
    <div className="min-w-0 border-l border-white/[.06] pl-3 first:border-0 first:pl-0">
      <div className="eyebrow whitespace-nowrap">{label}</div>
      <div className="mono mt-2 truncate text-[12px] text-slate-200" data-testid={testId}>{value}</div>
    </div>
  );
}

function CandlePanel({
  interval,
  candles,
  metrics,
  error,
}: {
  interval: CoinInterval;
  candles: ClosedCoinCandle[] | null;
  metrics: CoinCandleMetrics | null;
  error?: string;
}) {
  const latest = candles?.at(-1);
  const recentCandles = candles?.slice(-6).reverse() ?? [];
  const condition = metrics?.conditionMet;
  return (
    <section className="panel min-w-0 overflow-hidden" data-testid={`panel-coin-${interval}`}>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[.07] px-4 py-4">
        <div>
          <div className="eyebrow">{interval} · closed candle</div>
          <p className="mt-1 text-[11px] text-slate-500">Latest completed interval · Binance spot</p>
          {latest && <div className="mt-1 mono text-[9px] text-slate-600" data-testid={`text-${interval}-candle-time`}>Closed {formatTime(latest.closeTime)}</div>}
        </div>
        <span
          className={`rounded-md px-2.5 py-1 mono text-[10px] ${
            condition === undefined
              ? "bg-white/[.04] text-slate-500"
              : condition
                ? "bg-[rgba(47,207,176,.1)] teal-text"
                : "bg-white/[.04] text-slate-400"
          }`}
          data-testid={`status-condition-${interval}`}
        >
          {condition === undefined ? "—" : condition ? "condition met" : "not met"}
        </span>
      </div>

      {error && (
        <div className="border-b border-amber-500/10 bg-amber-500/[.04] px-4 py-2 text-[10px] text-amber-200" role="status" data-testid={`status-error-${interval}`}>
          Candle data unavailable: {error}
        </div>
      )}
      {!candles && !error ? (
        <div className="space-y-3 p-4" data-testid={`loading-candles-${interval}`} aria-label={`Loading ${interval} candle data`}>
          <div className="skeleton h-4 w-40" />
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {[0, 1, 2, 3].map((item) => <div key={item} className="skeleton h-8" />)}
          </div>
        </div>
      ) : !latest ? (
        <div className="px-4 py-8 text-center text-[11px] text-slate-500" data-testid={`empty-candles-${interval}`}>
          No closed candle data is available for this interval.
        </div>
      ) : (
        <div className="p-4" data-testid={`content-candles-${interval}`}>
          <div className="grid grid-cols-2 gap-x-5 gap-y-4 sm:grid-cols-4">
            <MetricValue label="Open" value={formatPrice(latest.open)} testId={`value-${interval}-open`} />
            <MetricValue label="High" value={formatPrice(latest.high)} testId={`value-${interval}-high`} />
            <MetricValue label="Low" value={formatPrice(latest.low)} testId={`value-${interval}-low`} />
            <MetricValue label="Close" value={formatPrice(latest.close)} testId={`value-${interval}-close`} />
          </div>
          <div className="mt-5 grid grid-cols-2 gap-x-5 gap-y-4 border-t border-white/[.06] pt-4 sm:grid-cols-5">
            <MetricValue label="Volume" value={formatVolume(latest.volume)} testId={`value-${interval}-volume`} />
            <MetricValue label="EMA21" value={formatPrice(metrics?.ema21)} testId={`value-${interval}-ema21`} />
            <MetricValue label="EMA50" value={formatPrice(metrics?.ema50)} testId={`value-${interval}-ema50`} />
            <MetricValue label="RSI14" value={formatNumber(metrics?.rsi14)} testId={`value-${interval}-rsi14`} />
            <MetricValue label="RVOL" value={formatNumber(metrics?.rvol)} testId={`value-${interval}-rvol`} />
          </div>
          <div className="mt-5 border-t border-white/[.06] pt-4" data-testid={`list-${interval}-closed-candles`}>
            <div className="eyebrow mb-2">Recent closed candles</div>
            <div className="mobile-scroll overflow-x-auto">
              <table className="w-full min-w-[640px] border-collapse text-left">
                <thead>
                  <tr className="eyebrow">
                    <th className="px-2 py-2 font-semibold">Closed</th>
                    <th className="px-2 py-2 font-semibold">Open</th>
                    <th className="px-2 py-2 font-semibold">High</th>
                    <th className="px-2 py-2 font-semibold">Low</th>
                    <th className="px-2 py-2 font-semibold">Close</th>
                    <th className="px-2 py-2 text-right font-semibold">Volume</th>
                  </tr>
                </thead>
                <tbody>
                  {recentCandles.map((candle) => (
                    <tr key={candle.openTime} className="border-t border-white/[.045]" data-testid={`row-${interval}-candle-${candle.openTime}`}>
                      <td className="px-2 py-2 mono text-[9px] text-slate-500">{formatTime(candle.closeTime)}</td>
                      <td className="px-2 py-2 mono text-[9px] text-slate-300">{formatPrice(candle.open)}</td>
                      <td className="px-2 py-2 mono text-[9px] text-slate-300">{formatPrice(candle.high)}</td>
                      <td className="px-2 py-2 mono text-[9px] text-slate-300">{formatPrice(candle.low)}</td>
                      <td className="px-2 py-2 mono text-[9px] text-slate-200">{formatPrice(candle.close)}</td>
                      <td className="px-2 py-2 text-right mono text-[9px] text-slate-400">{formatVolume(candle.volume)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div className="mt-4 border-t border-white/[.06] pt-3 mono text-[9px] leading-relaxed text-slate-600">
            Condition: close &gt; EMA21 and close &gt; EMA50 and RSI14 &gt;= 50 and RVOL &gt;= 1.5
          </div>
        </div>
      )}
    </section>
  );
}

export default function CoinPage() {
  const [pairs, setPairs] = useState<UsdtSpotPair[]>([]);
  const [pairsLoading, setPairsLoading] = useState(true);
  const [pairsError, setPairsError] = useState<string | null>(null);
  const [pairLoadAttempt, setPairLoadAttempt] = useState(0);
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [selected, setSelected] = useState<UsdtSpotPair | null>(null);
  const [, setLocation] = useLocation();
  const [ticker, setTicker] = useState<CoinTicker | null>(null);
  const [candles15m, setCandles15m] = useState<ClosedCoinCandle[] | null>(null);
  const [candles1h, setCandles1h] = useState<ClosedCoinCandle[] | null>(null);
  const [trades, setTrades] = useState<RecentCoinTrade[] | null>(null);
  const [feedErrors, setFeedErrors] = useState<FeedErrors>({});
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const searchRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchUsdtSpotPairs(controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) {
          setPairs(result);
          setPairsError(null);
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setPairsError(error instanceof Error ? error.message : "Unable to load eligible pairs.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setPairsLoading(false);
      });
    return () => controller.abort();
  }, [pairLoadAttempt]);

  const results = useMemo(() => searchUsdtSpotPairs(pairs, query), [pairs, query]);
  const metrics15m = useMemo(() => candles15m ? calculateCoinCandleMetrics(candles15m) : null, [candles15m]);
  const metrics1h = useMemo(() => candles1h ? calculateCoinCandleMetrics(candles1h) : null, [candles1h]);

  useEffect(() => {
    if (!selected) {
      setTicker(null);
      setCandles15m(null);
      setCandles1h(null);
      setTrades(null);
      setFeedErrors({});
      setLastUpdated(null);
      return;
    }

    setTicker(null);
    setCandles15m(null);
    setCandles1h(null);
    setTrades(null);
    setFeedErrors({});
    setLastUpdated(null);
    setRefreshing(true);
    let controller: AbortController | null = null;
    const load = async () => {
      controller?.abort();
      const current = new AbortController();
      controller = current;
      setRefreshing(true);
      const requests = await Promise.allSettled([
        fetchCoinTicker(selected.symbol, current.signal),
        fetchClosedCoinCandles(selected.symbol, "15m", current.signal),
        fetchClosedCoinCandles(selected.symbol, "1h", current.signal),
        fetchRecentCoinTrades(selected.symbol, current.signal),
      ]);
      if (current.signal.aborted) return;
      const nextErrors: FeedErrors = {};
      if (requests[0].status === "fulfilled") setTicker(requests[0].value);
      else nextErrors.ticker = requests[0].reason instanceof Error ? requests[0].reason.message : "Request failed";
      if (requests[1].status === "fulfilled") setCandles15m(requests[1].value);
      else nextErrors["15m"] = requests[1].reason instanceof Error ? requests[1].reason.message : "Request failed";
      if (requests[2].status === "fulfilled") setCandles1h(requests[2].value);
      else nextErrors["1h"] = requests[2].reason instanceof Error ? requests[2].reason.message : "Request failed";
      if (requests[3].status === "fulfilled") setTrades(requests[3].value);
      else nextErrors.trades = requests[3].reason instanceof Error ? requests[3].reason.message : "Request failed";
      setFeedErrors(nextErrors);
      setLastUpdated(Date.now());
      setRefreshing(false);
    };

    void load();
    const timer = window.setInterval(() => void load(), 45_000);
    return () => {
      window.clearInterval(timer);
      controller?.abort();
    };
  }, [selected]);

  const choosePair = (pair: UsdtSpotPair) => {
    setSelected(pair);
    setQuery(pair.baseAsset);
    setLocation("/?symbol=" + encodeURIComponent(pair.symbol));
    setSearchOpen(false);
    searchRef.current?.blur();
  };

  const partialErrorCount = Object.keys(feedErrors).length;
  const updatedLabel = lastUpdated
    ? new Date(lastUpdated).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : "Waiting";

  return (
    <main className="terminal-shell min-h-dvh">
      <div className="relative z-10 mx-auto max-w-[1320px] px-4 pb-10 pt-5 sm:px-6 lg:px-8">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-white/[.07] pb-5">
          <div className="flex items-center gap-4">
            <Link
              href="/"
              data-testid="link-back-scanner"
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-white/[.08] text-slate-400 transition-colors hover:border-white/[.16] hover:text-slate-100"
              aria-label="Back to Top 20 scanner"
            >
              <ArrowLeft size={16} />
            </Link>
            <div>
              <div className="eyebrow">V6 Master Pro / Spot reference</div>
              <h1 className="display-font mt-1 text-[18px] font-bold tracking-tight text-slate-100">Coin detail</h1>
            </div>
          </div>
          <div className="flex items-center gap-2 rounded-full border border-white/[.08] bg-white/[.025] px-3 py-2">
            {selected && !refreshing ? <Wifi size={13} className="teal-text" /> : <Activity size={13} className="text-slate-500" />}
            <span className="mono text-[9px] text-slate-400" data-testid="status-coin-refresh">
              {selected ? refreshing ? "UPDATING" : partialErrorCount ? "PARTIAL DATA" : "BINANCE SPOT" : "PAIR NOT SELECTED"}
            </span>
          </div>
        </header>

        <section className="mt-6 panel relative z-20 overflow-visible" data-testid="section-coin-search">
          <div className="flex flex-wrap items-end justify-between gap-4 border-b border-white/[.07] px-4 py-4 sm:px-5">
            <div>
              <div className="eyebrow">Instrument lookup</div>
              <p className="mt-1 text-[11px] text-slate-500">Search eligible Binance USDT spot pairs</p>
            </div>
            <div className="relative w-full sm:w-[340px]">
              <label htmlFor="coin-search" className="sr-only">Search eligible USDT spot pairs</label>
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                id="coin-search"
                ref={searchRef}
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                  setSelected(null);
                  setSearchOpen(true);
                }}
                onFocus={() => setSearchOpen(true)}
                onKeyDown={(event) => {
                  if (event.key === "Escape") setSearchOpen(false);
                  if (event.key === "Enter" && results[0]) choosePair(results[0]);
                }}
                placeholder="Search symbol or asset"
                autoComplete="off"
                data-testid="input-coin-search"
                className="h-10 w-full rounded-lg border border-white/[.09] bg-black/20 pl-10 pr-3 mono text-[11px] text-slate-200 outline-none placeholder:text-slate-600 focus:border-[rgba(47,207,176,.5)]"
              />
              {searchOpen && query.trim() && (
                <div className="absolute left-0 right-0 top-[calc(100%+7px)] z-30 overflow-hidden rounded-lg border border-white/[.1] bg-[hsl(var(--popover))] shadow-2xl" data-testid="list-coin-search-results">
                  {results.length ? results.map((pair) => (
                    <button
                      key={pair.symbol}
                      type="button"
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => choosePair(pair)}
                      data-testid={`option-coin-${pair.symbol.toLowerCase()}`}
                      className="flex w-full items-center justify-between border-b border-white/[.05] px-3.5 py-3 text-left last:border-0 hover:bg-white/[.04]"
                    >
                      <span className="font-semibold text-[11px] text-slate-200">{pair.baseAsset}<span className="ml-1.5 mono text-[9px] text-slate-600">/ USDT</span></span>
                      <span className="mono text-[9px] text-slate-600">{pair.symbol}</span>
                    </button>
                  )) : (
                    <div className="px-3.5 py-3 text-[10px] text-slate-500" data-testid="empty-coin-search-results">
                      {pairsLoading ? "Loading eligible pairs…" : "No eligible USDT spot pair matches."}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
          {pairsError && (
            <div role="alert" className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-[10px] text-amber-200" data-testid="status-pairs-error">
              <span>Pair directory unavailable: {pairsError}</span>
              <button
                type="button"
                onClick={() => {
                  setPairsLoading(true);
                  setPairsError(null);
                  setPairLoadAttempt((attempt) => attempt + 1);
                }}
                data-testid="button-retry-pair-directory"
                className="rounded-md border border-white/[.1] px-2.5 py-1.5 text-[9px] font-semibold text-slate-300 transition-colors hover:bg-white/[.05]"
              >
                Retry
              </button>
            </div>
          )}
          {pairsLoading && (
            <div className="flex items-center gap-2 px-5 py-3 text-[10px] text-slate-500" data-testid="status-pairs-loading">
              <span className="skeleton h-2 w-2 rounded-full" /> Loading Binance spot pair directory
            </div>
          )}
        </section>

        {!selected ? (
          <section className="panel mt-5 flex min-h-[240px] flex-col items-center justify-center px-6 py-12 text-center" data-testid="empty-coin-selection">
            <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl border border-white/[.08] bg-white/[.025] text-slate-500"><Search size={18} /></div>
            <h2 className="text-[14px] font-semibold text-slate-200">Select a spot pair</h2>
            <p className="mt-2 max-w-sm text-[11px] leading-relaxed text-slate-500">
              Search the live Binance directory to inspect last price, closed-candle metrics, and recent trades.
            </p>
            <span className="mt-5 mono text-[9px] tracking-[.12em] text-slate-600">USDT QUOTED · SPOT MARKET</span>
          </section>
        ) : (
          <>
            <section className="panel mt-5 overflow-hidden" data-testid="section-coin-overview">
              <div className="flex flex-wrap items-end justify-between gap-5 px-4 py-5 sm:px-6">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="h-1.5 w-1.5 rounded-full bg-[hsl(var(--primary))]" />
                    <span className="eyebrow">Binance spot · USDT</span>
                  </div>
                  <h2 className="display-font mt-2 text-[23px] font-extrabold tracking-tight text-slate-100 sm:text-[28px]" data-testid="text-coin-symbol">
                    {selected.baseAsset}<span className="ml-2 text-[13px] font-medium text-slate-500">/ USDT</span>
                  </h2>
                  <div className="mt-1 mono text-[9px] text-slate-600" data-testid="text-coin-market-symbol">{selected.symbol}</div>
                </div>
                <div className="flex flex-wrap items-end gap-x-9 gap-y-3">
                  <div>
                    <div className="eyebrow">Last price</div>
                    <div className="mono mt-2 text-[22px] font-medium tracking-tight text-slate-100 sm:text-[26px]" data-testid="value-coin-last-price">
                      {ticker ? formatPrice(ticker.lastPrice) : "—"}
                    </div>
                  </div>
                  <div className="pb-1">
                    <div className="eyebrow">24h change</div>
                    {ticker ? (
                      <div className={`mono mt-2 inline-flex items-center gap-1 text-[13px] ${ticker.change24h >= 0 ? "positive" : "negative"}`} data-testid="value-coin-change-24h">
                        {ticker.change24h >= 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                        {ticker.change24h >= 0 ? "+" : ""}{ticker.change24h.toFixed(2)}%
                      </div>
                    ) : (
                      <div className="mono mt-2 text-[13px] text-slate-500" data-testid="value-coin-change-24h">—</div>
                    )}
                  </div>
                  <div className="pb-1">
                    <div className="eyebrow">Updated</div>
                    <div className="mt-2 inline-flex items-center gap-1.5 mono text-[10px] text-slate-500" data-testid="value-coin-updated">
                      <Clock3 size={12} /> {updatedLabel}
                    </div>
                  </div>
                </div>
              </div>
              {feedErrors.ticker && (
                <div className="border-t border-amber-500/10 bg-amber-500/[.04] px-5 py-2.5 text-[10px] text-amber-200" role="status" data-testid="status-ticker-error">
                  Last-price data unavailable: {feedErrors.ticker}
                </div>
              )}
              {!ticker && !feedErrors.ticker && (
                <div className="border-t border-white/[.05] px-5 py-2.5 mono text-[9px] text-slate-600" data-testid="status-ticker-loading">
                  Fetching market ticker…
                </div>
              )}
            </section>

            <div className="mt-5 grid gap-4 xl:grid-cols-2">
              <CandlePanel interval="15m" candles={candles15m} metrics={metrics15m} error={feedErrors["15m"]} />
              <CandlePanel interval="1h" candles={candles1h} metrics={metrics1h} error={feedErrors["1h"]} />
            </div>

            <section className="panel mt-5 overflow-hidden" data-testid="section-coin-recent-trades">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[.07] px-4 py-4">
                <div>
                  <div className="eyebrow">Recent trades</div>
                  <p className="mt-1 text-[11px] text-slate-500">Latest public spot prints · {selected.symbol}</p>
                </div>
                <span className="mono text-[9px] text-slate-600" data-testid="text-trades-count">
                  {trades ? `${trades.length} records` : "—"}
                </span>
              </div>
              {feedErrors.trades && (
                <div role="status" className="border-b border-amber-500/10 bg-amber-500/[.04] px-4 py-2 text-[10px] text-amber-200" data-testid="status-trades-error">
                  Recent trade data unavailable: {feedErrors.trades}
                </div>
              )}
              {!trades && !feedErrors.trades ? (
                <div className="space-y-2 px-4 py-4" data-testid="loading-coin-trades">
                  {[0, 1, 2].map((item) => <div key={item} className="skeleton h-7 w-full" />)}
                </div>
              ) : trades?.length ? (
                <div className="mobile-scroll overflow-x-auto">
                  <table className="w-full min-w-[560px] border-collapse text-left">
                    <thead><tr className="eyebrow">
                      <th className="px-4 py-3 font-semibold">Time</th>
                      <th className="px-3 py-3 font-semibold">Price</th>
                      <th className="px-3 py-3 font-semibold">Quantity</th>
                      <th className="px-4 py-3 text-right font-semibold">Quote value</th>
                    </tr></thead>
                    <tbody>
                      {trades.map((trade) => (
                        <TradeRow key={trade.id} trade={trade} />
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : !feedErrors.trades ? (
                <div className="px-4 py-8 text-center text-[11px] text-slate-500" data-testid="empty-coin-trades">No recent trades returned for this pair.</div>
              ) : (
                <div className="px-4 py-7 text-center text-[11px] text-slate-500" data-testid="empty-coin-trades">Trade data is temporarily unavailable.</div>
              )}
            </section>
          </>
        )}

        <footer className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-white/[.06] pt-4">
          <span className="mono text-[9px] text-slate-600">Public Binance data · closed candles only · refresh every 45 seconds</span>
          <span className="text-[10px] text-slate-500">Informational only. Not financial advice.</span>
        </footer>
      </div>
    </main>
  );
}

function TradeRow({ trade }: { trade: RecentCoinTrade }) {
  return (
    <tr className="border-t border-white/[.045] hover:bg-white/[.02]" data-testid={`row-coin-trade-${trade.id}`}>
      <td className="px-4 py-2.5 mono text-[10px] text-slate-500">{formatTime(trade.time)}</td>
      <td className="px-3 py-2.5 mono text-[10px] text-slate-200">{formatPrice(trade.price)}</td>
      <td className="px-3 py-2.5 mono text-[10px] text-slate-300">{formatVolume(trade.quantity)}</td>
      <td className="px-4 py-2.5 text-right mono text-[10px] text-slate-400">{formatPrice(trade.price * trade.quantity)}</td>
    </tr>
  );
}
