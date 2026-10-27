import { useEffect, useMemo, useRef, useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Bell,
  Bot,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Crosshair,
  Grid2X2,
  LayoutDashboard,
  LineChart,
  ListFilter,
  MoreHorizontal,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Star,
  Target,
  TrendingUp,
  Users,
  Wifi,
  X,
  Zap,
} from 'lucide-react';
import {
  CandlestickSeries,
  ColorType,
  LineSeries,
  LineStyle,
  createChart,
  type Time,
} from 'lightweight-charts';
import { detectFvg } from "@/lib/ocs-fvg";
import { createSeriesMarkers } from "lightweight-charts";

import {
  useGetMarketCandles,
  useGetMarketSnapshot,
  useGetWatchlist,
  useHealthCheck,
  useListExecutionLogs,
  useListStrategies,
  useToggleWatchlist,
} from '@workspace/api-client-react';
import type { Coin, ExecutionLog, MarketCandle, Strategy, VsaCheck } from '@workspace/api-client-react';
import { ErrorBoundary } from '@/components/error-boundary';
import { TopUsdtSignals } from '@/components/top-usdt-signals';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import CoinPage from '@/pages/coin';
import NotFound from '@/pages/not-found';
import { Link, Route, Switch, Router as WouterRouter, useLocation } from 'wouter';
import {
  useTopUsdtPairs,
  type KlineInterval,
  type StreamStatus,
  type TopUsdtPair,
} from '@/lib/binance-top-usdt';
import '../src/index.css';

const queryClient = new QueryClient();

const formatUsd = (value: number) => {
  if (value >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(2)}B`;
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1000) return `$${(value / 1000).toFixed(1)}K`;
  if (value < 1) return `$${value.toFixed(4)}`;
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
};

const formatPrice = (value: number) =>
  value < 1 ? `$${value.toFixed(4)}` : `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;

const formatSupply = (value: number) => {
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)}B`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
};

const timeAgo = (timestamp: string) => {
  const parsed = new Date(timestamp).getTime();
  if (Number.isNaN(parsed)) return timestamp;
  const mins = Math.max(1, Math.round((Date.now() - parsed) / 60000));
  return mins < 60 ? `${mins}m ago` : `${Math.round(mins / 60)}h ago`;
};

function calculateRsi(candles: MarketCandle[], period = 14) {
  if (candles.length <= period) return [];
  let averageGain = 0;
  let averageLoss = 0;
  for (let index = 1; index <= period; index += 1) {
    const change = candles[index].close - candles[index - 1].close;
    averageGain += Math.max(change, 0);
    averageLoss += Math.max(-change, 0);
  }
  averageGain /= period;
  averageLoss /= period;

  const points = [{
    time: candles[period].time as Time,
    value: averageLoss === 0 ? 100 : 100 - (100 / (1 + averageGain / averageLoss)),
  }];
  for (let index = period + 1; index < candles.length; index += 1) {
    const change = candles[index].close - candles[index - 1].close;
    averageGain = ((averageGain * (period - 1)) + Math.max(change, 0)) / period;
    averageLoss = ((averageLoss * (period - 1)) + Math.max(-change, 0)) / period;
    points.push({
      time: candles[index].time as Time,
      value: averageLoss === 0 ? 100 : 100 - (100 / (1 + averageGain / averageLoss)),
    });
  }
  return points;
}

function Logo() {
  return (
    <div className="flex items-center gap-3" data-testid="brand-v6-master-pro">
      <div className="relative flex h-9 w-9 items-center justify-center overflow-hidden rounded-xl bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))]">
        <span className="absolute h-5 w-5 rotate-45 border-2 border-current" />
        <span className="relative z-10 text-xs font-extrabold tracking-tighter">V6</span>
      </div>
      <div>
        <div className="display-font text-[15px] font-extrabold tracking-tight text-slate-100">MASTER PRO</div>
        <div className="mono text-[9px] tracking-[.22em] text-slate-500">TRADING TERMINAL</div>
      </div>
    </div>
  );
}

function Sidebar({
  activeView,
  setActiveView,
  connection,
}: {
  activeView: string;
  setActiveView: (view: string) => void;
  connection: StreamStatus;
}) {
  const items = [
    { id: 'overview', label: 'Top 20 scanner', icon: LayoutDashboard },
    { id: 'chart', label: 'Closed-candle chart', icon: LineChart },
  ];
  return (
    <aside className="hidden min-h-dvh w-[236px] shrink-0 border-r border-[hsl(var(--sidebar-border))] bg-[hsl(var(--sidebar))] px-4 py-5 lg:block">
      <Logo />
      <div className="mt-10 px-3 eyebrow">Command center</div>
      <nav className="mt-3 space-y-1" aria-label="Main navigation">
        {items.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setActiveView(id)}
            data-testid={`button-nav-${id}`}
            className={`group flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors ${activeView === id ? 'bg-[rgba(47,207,176,.1)] text-[hsl(var(--primary))]' : 'text-slate-500 hover:bg-white/[.035] hover:text-slate-200'}`}
          >
            <Icon size={16} strokeWidth={1.8} />
            <span className="text-[12px] font-semibold">{label}</span>
            {activeView === id && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-[hsl(var(--primary))]" />}
          </button>
        ))}
        <Link
          href="/coin"
          data-testid="link-nav-coin-sidebar"
          className="group flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-slate-500 transition-colors hover:bg-white/[.035] hover:text-slate-200"
        >
          <Search size={16} strokeWidth={1.8} />
          <span className="text-[12px] font-semibold">Coin lookup</span>
        </Link>
      </nav>
       <div className="mt-auto pt-24">
        <div className="panel-muted p-3">
           <div className="flex items-center gap-2 text-[11px] font-semibold text-slate-300"><ShieldCheck size={14} className="teal-text" /> Binance stream</div>
           <div className="mt-2 flex items-center gap-2 text-[10px] text-slate-500"><span className={`status-dot ${connection === 'connected' ? '' : 'amber'}`} /> {connection === 'connected' ? 'Connected' : connection === 'reconnecting' ? 'Reconnecting' : 'Connecting'}</div>
        </div>
      </div>
    </aside>
  );
}

function Topbar({ activeView, connection }: { activeView: string; connection: StreamStatus }) {
  const connectionText = connection === 'connected'
    ? 'BINANCE STREAM LIVE'
    : connection === 'reconnecting'
      ? 'RECONNECTING'
      : connection === 'error'
        ? 'FEED ERROR'
        : 'CONNECTING';
  return (
    <header className="flex min-h-[74px] items-center justify-between gap-4 border-b border-white/[.07] px-5 py-4 lg:px-8">
      <div className="flex items-center gap-4">
        <div className="lg:hidden"><Logo /></div>
        <div className="hidden h-8 w-px bg-white/[.08] lg:block" />
        <div>
          <div className="eyebrow">{activeView === 'overview' ? 'Binance market scanner' : 'Live chart'}</div>
          <div className="mt-1 text-[12px] text-slate-500">Top USDT pairs by 24h quote volume</div>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Link
          href="/coin"
          data-testid="link-nav-coin-mobile"
          aria-label="Coin lookup"
          title="Coin lookup"
          className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-white/[.08] text-slate-400 transition-colors hover:border-white/[.16] hover:text-slate-100 lg:hidden"
        >
          <Search size={14} />
        </Link>
        <div className="hidden items-center gap-2 rounded-full border border-white/[.08] bg-white/[.025] px-3 py-1.5 md:flex">
          {connection === 'connected' ? <Wifi size={13} className="teal-text" /> : <Activity size={13} className="amber-text" />}
          <span className="mono text-[10px] text-slate-400">{connectionText}</span>
        </div>
      </div>
    </header>
  );
}

function StatCard({ label, value, sub, tone = 'neutral', icon: Icon }: { label: string; value: string; sub: string; tone?: 'neutral' | 'positive' | 'amber'; icon: typeof Activity }) {
  return (
    <div className="panel animate-rise p-4">
      <div className="flex items-start justify-between">
        <span className="eyebrow">{label}</span>
        <Icon size={15} className={tone === 'positive' ? 'teal-text' : tone === 'amber' ? 'amber-text' : 'text-slate-600'} />
      </div>
      <div className="display-font mt-3 text-[23px] font-bold tracking-tight text-slate-100">{value}</div>
      <div className={`mono mt-1 text-[10px] ${tone === 'positive' ? 'positive' : tone === 'amber' ? 'amber-text' : 'text-slate-500'}`}>{sub}</div>
    </div>
  );
}

function MiniSparkline({ positive = true }: { positive?: boolean }) {
  return (
    <svg viewBox="0 0 120 34" className="h-8 w-[112px]" aria-label={positive ? 'Positive price trend' : 'Negative price trend'}>
      <path d={positive ? 'M1 28 C14 27 15 19 25 23 S39 24 46 16 S57 21 65 15 S79 17 89 8 S106 13 119 2' : 'M1 5 C14 7 17 16 27 11 S42 18 50 17 S63 28 73 21 S93 26 119 31'} fill="none" stroke={positive ? '#39cda9' : '#ed7778'} strokeWidth="1.8" />
      <path d={positive ? 'M1 28 C14 27 15 19 25 23 S39 24 46 16 S57 21 65 15 S79 17 89 8 S106 13 119 2 L119 34 L1 34 Z' : 'M1 5 C14 7 17 16 27 11 S42 18 50 17 S63 28 73 21 S93 26 119 31 L119 34 L1 34 Z'} fill={positive ? 'rgba(57,205,169,.09)' : 'rgba(237,119,120,.07)'} />
    </svg>
  );
}

function OverviewStats({ marketBreadth, sessionPnl, coinCount }: { marketBreadth: number; sessionPnl: number; coinCount: number }) {
  return (
    <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
      <StatCard label="Market breadth" value={`${marketBreadth.toFixed(1)}%`} sub="Live from market snapshot" tone="positive" icon={BarChart3} />
       <StatCard label="Market pulse" value={`${sessionPnl >= 0 ? '+' : ''}${sessionPnl.toFixed(2)}%`} sub="Live average move across top assets" tone="positive" icon={TrendingUp} />
      <StatCard label="Assets tracked" value={String(coinCount).padStart(2, '0')} sub="Binance + CoinGecko feed" tone="neutral" icon={Grid2X2} />
      <StatCard label="Signal confidence" value="N/A" sub="Not calculated (demo value removed)" tone="amber" icon={Zap} />
    </div>
  );
}

function MarketOverview({ coins, watchlist, toggle, onSelectCoin, huntingMode = false }: { coins: Coin[]; watchlist: string[]; toggle: (coin: Coin) => void; onSelectCoin: (coin: Coin) => void; huntingMode?: boolean }) {
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<'change' | 'volume'>('change');
  const filtered = useMemo(() => coins
    .filter((coin) => `${coin.symbol} ${coin.name}`.toLowerCase().includes(search.toLowerCase()))
    .filter((coin) => !huntingMode || (coin.followers >= 200_000 && coin.maxSupply <= 50_000_000_000 && coin.maxSupply > 0 && coin.circulatingSupply / coin.maxSupply >= 0.7))
    .sort((a, b) => sort === 'change' ? b.change24h - a.change24h : b.volume24h - a.volume24h)
     .slice(0, huntingMode ? 500 : 8), [coins, huntingMode, search, sort]);
  return (
    <section className="panel min-w-0 animate-rise delay-1">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[.07] px-4 py-4">
        <div><div className="eyebrow">{huntingMode ? 'Coin hunter / top 500 screen' : 'Market overview'}</div><div className="mt-1 text-[12px] text-slate-400">{huntingMode ? '≥200K followers · ≥70% circulating · locked max supply ≤50B' : 'Momentum across your trading universe'}</div></div>
        <div className="flex items-center gap-2">
          <div className="relative"><Search size={13} className="absolute left-2.5 top-2.5 text-slate-600" /><input value={search} onChange={(e) => setSearch(e.target.value)} data-testid="input-market-search" placeholder="Find asset" className="h-8 w-[126px] rounded-md border border-white/[.08] bg-black/10 pl-8 pr-2 text-[11px] text-slate-300 outline-none placeholder:text-slate-600 focus:border-[hsl(var(--primary))]" /></div>
          <button type="button" onClick={() => setSort(sort === 'change' ? 'volume' : 'change')} data-testid="button-market-sort" className="flex h-8 items-center gap-1.5 rounded-md border border-white/[.08] px-2 text-[10px] font-semibold text-slate-500 hover:text-slate-200"><ListFilter size={13} /> {sort === 'change' ? 'Change' : 'Volume'} <ChevronDown size={12} /></button>
        </div>
      </div>
       <div className="mobile-scroll max-h-[570px] overflow-y-auto">
          <div className="min-w-[820px]">
           <div className={`grid ${huntingMode ? 'grid-cols-[1.3fr_.8fr_.7fr_.85fr_.75fr_.85fr_1fr_40px]' : 'grid-cols-[1.35fr_.85fr_.75fr_.85fr_1fr_40px]'} gap-3 px-4 py-3 eyebrow`}><span>Asset</span><span>Last price</span><span>24h</span><span>Volume</span>{huntingMode && <><span>Circulating</span><span>Supply cap</span></>}<span>VSA state</span><span /></div>
          {filtered.length ? filtered.map((coin) => (
             <div role="button" tabIndex={0} key={coin.id} onClick={() => onSelectCoin(coin)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') onSelectCoin(coin); }} className={`grid w-full ${huntingMode ? 'grid-cols-[1.3fr_.8fr_.7fr_.85fr_.75fr_.85fr_1fr_40px]' : 'grid-cols-[1.35fr_.85fr_.75fr_.85fr_1fr_40px]'} items-center gap-3 border-t border-white/[.045] px-4 py-3 text-left transition-colors hover:bg-white/[.025]`} data-testid={`row-market-${coin.id}`}>
              <div className="flex items-center gap-2.5"><button type="button" onClick={() => toggle(coin)} data-testid={`button-favorite-${coin.id}`} className={watchlist.includes(coin.id) ? 'amber-text' : 'text-slate-700 hover:text-slate-300'}><Star size={14} fill={watchlist.includes(coin.id) ? 'currentColor' : 'none'} /></button><div className="flex h-7 w-7 items-center justify-center rounded-md bg-slate-800 text-[9px] font-bold text-slate-300">{coin.symbol.slice(0, 2)}</div><div><div className="text-[11px] font-bold text-slate-200">{coin.symbol}</div><div className="text-[9px] text-slate-600">{coin.name}</div></div></div>
              <span className="mono text-[11px] text-slate-300">{formatPrice(coin.price)}</span>
              <span className={`mono text-[11px] font-medium ${coin.change24h >= 0 ? 'positive' : 'negative'}`}>{coin.change24h >= 0 ? '+' : ''}{coin.change24h.toFixed(2)}%</span>
              <span className="mono text-[10px] text-slate-500">{formatUsd(coin.volume24h)}</span>
                {huntingMode && <><span className="mono text-[10px] teal-text">{coin.maxSupply > 0 ? `${((coin.circulatingSupply / coin.maxSupply) * 100).toFixed(1)}%` : 'n/a'}</span><span className="mono text-[10px] text-slate-500">{coin.maxSupply > 0 ? formatSupply(coin.maxSupply) : 'Unknown'}</span></>}
              <span className={`flex items-center gap-1.5 text-[10px] font-semibold ${coin.vsa.includes('manipulation') ? 'red-text' : 'positive'}`}><span className={`status-dot ${coin.vsa.includes('manipulation') ? 'red' : ''}`} />{coin.vsa === 'ok_up' ? 'Accumulation' : coin.vsa === 'ok_down' ? 'Distribution' : coin.vsa.replace('_', ' ')}</span>
               <span className="flex justify-end text-slate-600"><MoreHorizontal size={15} /></span>
             </div>
          )) : <div className="px-4 py-10 text-center text-slate-500">No assets match this search.</div>}
        </div>
      </div>
    </section>
  );
}

function VsaDesk({ checks, coins, onSelectCoin, limit = 4 }: { checks: VsaCheck[]; coins: Coin[]; onSelectCoin: (coin: Coin) => void; limit?: number }) {
  const getCoin = (id: string) => coins.find((coin) => coin.id === id);
  return (
    <section className="panel animate-rise delay-2">
      <div className="flex items-center justify-between border-b border-white/[.07] px-4 py-4"><div><div className="eyebrow">VSA signal desk</div><div className="mt-1 text-[12px] text-slate-400">Volume spread analysis anomalies</div></div><button type="button" data-testid="button-vsa-filter" className="rounded-md border border-white/[.08] p-1.5 text-slate-500 hover:text-slate-200"><ListFilter size={14} /></button></div>
      <div className="space-y-2 p-3">
         {checks.slice(0, limit).map((check) => {
          const coin = getCoin(check.coinId);
           return <button type="button" key={check.id} onClick={() => coin && onSelectCoin(coin)} className="panel-muted flex w-full gap-3 p-3 text-left" data-testid={`card-vsa-${check.id}`}>
            <span className={`mt-1.5 status-dot ${check.status === 'manipulation' ? 'red' : check.priceChange >= 0 ? '' : 'amber'}`} />
            <div className="min-w-0 flex-1"><div className="flex items-center justify-between gap-2"><span className="text-[11px] font-bold text-slate-200">{check.label}</span><span className={`mono text-[10px] ${check.status === 'manipulation' ? 'red-text' : 'positive'}`}>{check.volumeChange >= 0 ? '+' : ''}{check.volumeChange.toFixed(1)}% vol</span></div><p className="mt-1 truncate text-[10px] text-slate-500">{coin?.symbol} · {check.detail}</p><div className="mt-2 flex gap-3 mono text-[9px] text-slate-600"><span>Price {check.priceChange >= 0 ? '+' : ''}{check.priceChange.toFixed(2)}%</span><span className={check.status === 'manipulation' ? 'red-text' : 'teal-text'}>{check.status === 'manipulation' ? 'Review required' : 'Healthy flow'}</span></div></div>
           </button>;
        })}
        {!checks.length && <EmptyMini label="No VSA checks available" />}
      </div>
    </section>
  );
}

function StrategyDesk({ strategies, onStrategyChange }: { strategies: Strategy[]; onStrategyChange: (strategy: Strategy) => void }) {
  const [selected, setSelected] = useState(0);
  const [inspecting, setInspecting] = useState<Strategy | null>(null);
  const strategy = strategies[selected];
  return (
    <section className="panel animate-rise delay-2 min-w-0">
      <div className="flex items-center justify-between border-b border-white/[.07] px-4 py-4"><div><div className="eyebrow">Strategy inspection</div><div className="mt-1 text-[12px] text-slate-400">Rules, bias and historical edge</div></div><button type="button" data-testid="button-strategy-more" className="text-slate-600 hover:text-slate-300"><MoreHorizontal size={16} /></button></div>
      {strategy ? <div className="p-4">
        <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex items-center gap-2"><span className="rounded bg-[rgba(47,207,176,.1)] px-2 py-1 mono text-[9px] font-medium teal-text">{strategy.shortName}</span><span className="mono text-[9px] text-slate-600">{strategy.category}</span></div><h3 className="mt-2 text-[17px] font-bold text-slate-100">{strategy.name}</h3></div><div className={`rounded-full px-2.5 py-1 text-[10px] font-bold ${strategy.bias.toLowerCase().includes('bull') || strategy.bias.toLowerCase().includes('long') ? 'bg-[rgba(47,207,176,.1)] teal-text' : 'bg-[rgba(242,122,120,.1)] red-text'}`}>{strategy.bias}</div></div>
        <div className="mt-5 grid grid-cols-3 gap-2"><div className="panel-muted p-2.5"><div className="eyebrow">Win rate</div><div className="mt-1 mono text-[15px] font-medium positive">{strategy.winRate.toFixed(1)}%</div></div><div className="panel-muted p-2.5"><div className="eyebrow">Trades</div><div className="mt-1 mono text-[15px] font-medium text-slate-200">{strategy.trades}</div></div><div className="panel-muted p-2.5"><div className="eyebrow">Frame</div><div className="mt-1 mono text-[15px] font-medium amber-text">{strategy.timeframe}</div></div></div>
         <div className="mt-5 eyebrow">Active rule set</div><div className="mt-2 space-y-2">{strategy.rules.slice(0, 3).map((rule, index) => <div key={rule} className="flex gap-2 text-[10px] leading-relaxed text-slate-400"><span className="mono text-[9px] text-slate-600">0{index + 1}</span>{rule}</div>)}</div>
         <button type="button" onClick={() => setInspecting(strategy)} data-testid="button-inspect-strategy" className="mt-5 flex w-full items-center justify-between rounded-lg border border-white/[.08] px-3 py-2 text-[10px] font-semibold text-slate-400 hover:border-[rgba(47,207,176,.32)] hover:text-[hsl(var(--primary))]">Inspect dedicated rule set <ChevronRight size={13} /></button>
         {strategies.length > 1 && <div className="mt-5 flex gap-1.5">{strategies.map((item, index) => <button type="button" key={item.id} onClick={() => { setSelected(index); onStrategyChange(item); }} data-testid={`button-strategy-${item.id}`} className={`h-1.5 flex-1 rounded-full transition ${selected === index ? 'bg-[hsl(var(--primary))]' : 'bg-white/[.08]'}`} aria-label={`Select ${item.name}`} />)}</div>}
      </div> : <EmptyMini label="Strategies are loading" />}
      {inspecting && <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/70 p-4" role="dialog" aria-modal="true" aria-label={`${inspecting.name} rules`}>
        <div className="panel max-w-lg p-5 shadow-2xl">
          <div className="flex items-start justify-between gap-4"><div><div className="eyebrow">Dedicated strategy inspection</div><h3 className="mt-2 text-lg font-bold text-slate-100">{inspecting.name}</h3><div className="mt-1 mono text-[10px] teal-text">{inspecting.timeframe} · {inspecting.bias}</div></div><button type="button" onClick={() => setInspecting(null)} className="text-slate-500 hover:text-slate-100" aria-label="Close strategy inspection"><X size={17} /></button></div>
          <div className="mt-5 space-y-3">{inspecting.rules.map((rule, index) => <div key={rule} className="flex gap-3 rounded-lg border border-white/[.06] bg-white/[.02] p-3 text-[11px] leading-relaxed text-slate-300"><span className="mono text-[10px] teal-text">0{index + 1}</span><span>{rule}</span></div>)}</div>
        </div>
      </div>}
    </section>
  );
}

function ChartMapping({
  pair,
  strategy,
  strategies,
  onStrategyChange,
}: {
  pair?: TopUsdtPair;
  strategy?: Strategy;
  strategies: Strategy[];
  onStrategyChange: (strategyId: string) => void;
}) {
  const [period, setPeriod] = useState<KlineInterval>('1h');
  const chartContainer = useRef<HTMLDivElement | null>(null);
  const rsiContainer = useRef<HTMLDivElement | null>(null);
  const periods: KlineInterval[] = ['15m', '1h'];
  const candles = pair?.candles[period] ?? [];
  const pairSymbol = pair?.symbol;
  useEffect(() => {
    if (!chartContainer.current || !rsiContainer.current || !pairSymbol || candles.length < 2) return;
    const container = chartContainer.current;
    const chart = createChart(container, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#64748b' },
      grid: { vertLines: { color: 'rgba(148, 163, 184, 0.06)' }, horzLines: { color: 'rgba(148, 163, 184, 0.06)' } },
      rightPriceScale: { borderColor: 'rgba(148, 163, 184, 0.12)' },
      timeScale: { borderColor: 'rgba(148, 163, 184, 0.12)', timeVisible: true, secondsVisible: false },
      crosshair: { vertLine: { color: 'rgba(47, 207, 176, .45)', labelBackgroundColor: '#173b37' }, horzLine: { color: 'rgba(47, 207, 176, .45)', labelBackgroundColor: '#173b37' } },
    });
    const chartCandles = candles.map((candle) => ({
      time: candle.time as Time,
      open: candle.open,
      high: candle.high,
      low: candle.low,
      close: candle.close,
    }));
    const series = chart.addSeries(CandlestickSeries, { upColor: '#2fcfb0', downColor: '#f27a78', borderVisible: false, wickUpColor: '#2fcfb0', wickDownColor: '#f27a78' });
    series.setData(chartCandles);
    {
      const fvgZones = detectFvg(candles).slice(-20);
      for (const z of fvgZones) {
        const col = z.kind === "bullish" ? "rgba(47,207,176,0.35)" : "rgba(255,23,68,0.35)";
        const from = candles[z.confirmIndex - 2].time as Time;
        const to = (z.fillIndex !== null ? candles[z.fillIndex].time : candles[candles.length - 1].time) as Time;
        const top = chart.addSeries(LineSeries, { color: col, lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false });
        top.setData([{ time: from, value: z.top }, { time: to, value: z.top }]);
        createSeriesMarkers(top, [{ time: from, position: "aboveBar", color: z.kind === "bullish" ? "#2fcfb0" : "#ff1744", shape: "square", size: 0, text: "FVG" }]);
        const bot = chart.addSeries(LineSeries, { color: col, lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false });
        bot.setData([{ time: from, value: z.bottom }, { time: to, value: z.bottom }]);
      }
    }
    const firstTime = chartCandles[0].time;
    const lastCandle = chartCandles[chartCandles.length - 1];
    const lastTime = lastCandle.time;
    chart.timeScale().fitContent();
    const rsiChart = createChart(rsiContainer.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#64748b' },
      grid: { vertLines: { color: 'rgba(148, 163, 184, 0.04)' }, horzLines: { color: 'rgba(148, 163, 184, 0.04)' } },
      rightPriceScale: { borderColor: 'rgba(148, 163, 184, 0.12)', scaleMargins: { top: 0.08, bottom: 0.08 } },
      timeScale: { borderColor: 'rgba(148, 163, 184, 0.12)', timeVisible: false, secondsVisible: false },
    });
    const rsiSeries = rsiChart.addSeries(LineSeries, { color: '#c18cff', lineWidth: 2, priceLineVisible: false, lastValueVisible: true, title: 'RSI' });
    const rsiValues = calculateRsi(candles);
    rsiSeries.setData(rsiValues);
    [30, 50, 70].forEach((value) => {
      const threshold = rsiChart.addSeries(LineSeries, {
        color: value === 50 ? 'rgba(246, 190, 81, .65)' : 'rgba(148, 163, 184, .35)',
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        priceLineVisible: false,
        lastValueVisible: false,
        title: String(value),
      });
      threshold.setData([{ time: firstTime, value }, { time: lastTime, value }]);
    });
    rsiChart.timeScale().fitContent();
    return () => {
      chart.remove();
      rsiChart.remove();
    };
  }, [candles, pairSymbol, period, strategy]);
  return (
    <section className="panel animate-rise delay-3 overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[.07] px-4 py-4"><div><div className="eyebrow">Binance closed candles · strategy overlays</div><div className="mt-1 flex items-center gap-2 text-[12px] text-slate-300"><span className="font-bold">{pair?.baseAsset ?? '—'} / USDT</span><span className="mono text-[10px] text-slate-500">{pair?.lastPrice !== null && pair?.lastPrice !== undefined ? formatPrice(pair.lastPrice) : '—'}</span><span className={pair?.change24h && pair.change24h > 0 ? 'positive mono text-[10px]' : 'negative mono text-[10px]'}>{pair ? `${pair.change24h > 0 ? '+' : ''}${pair.change24h.toFixed(2)}%` : '--'}</span></div></div><div className="flex flex-wrap items-center gap-2"><select aria-label="Chart strategy overlay" value={strategy?.id ?? ''} onChange={(event) => onStrategyChange(event.target.value)} className="h-7 max-w-[150px] rounded-md border border-white/[.08] bg-[hsl(var(--card))] px-2 mono text-[9px] text-slate-400">{strategies.map((item) => <option key={item.id} value={item.id}>{item.shortName}</option>)}</select><div className="flex rounded-md border border-white/[.08] p-0.5">{periods.map((item) => <button type="button" key={item} onClick={() => setPeriod(item)} data-testid={`button-chart-${item}`} className={`rounded px-2 py-1 mono text-[9px] ${period === item ? 'bg-white/[.1] text-slate-200' : 'text-slate-600'}`}>{item.toUpperCase()}</button>)}</div></div></div>
      <div className="relative h-[270px] p-3"><div ref={chartContainer} className="h-full w-full" />{(!pair || candles.length < 2) && <div className="absolute inset-0 flex items-center justify-center bg-[hsl(var(--card))]/90 px-5 text-center text-[11px] text-slate-500">{!pair ? 'Select a pair from the scanner.' : 'Waiting for closed Binance candles…'}</div>}</div>
      <div className="border-t border-white/[.07] px-4 pt-2"><div className="eyebrow">RSI 14 · calculated from live closes</div><div ref={rsiContainer} className="mt-1 h-[82px] w-full" /></div>
    </section>
  );
}

function Watchlist({ coins, ids, toggle, onSelectCoin }: { coins: Coin[]; ids: string[]; toggle: (coin: Coin) => void; onSelectCoin: (coin: Coin) => void }) {
  const entries = ids.map((id) => coins.find((coin) => coin.id === id)).filter(Boolean) as Coin[];
  return <section className="panel animate-rise delay-3"><div className="flex items-center justify-between border-b border-white/[.07] px-4 py-4"><div><div className="eyebrow">Your watchlist</div><div className="mt-1 text-[12px] text-slate-400">Pinned for the next decision</div></div><button type="button" data-testid="button-watchlist-add" className="rounded-md border border-white/[.08] p-1.5 text-slate-500 hover:text-[hsl(var(--primary))]"><Plus size={14} /></button></div><div className="p-3">{entries.length ? <div className="space-y-1">{entries.slice(0, 5).map((coin) => <div key={coin.id} role="button" tabIndex={0} onClick={() => onSelectCoin(coin)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') onSelectCoin(coin); }} className="flex items-center gap-2.5 rounded-lg px-2 py-2.5 hover:bg-white/[.025]" data-testid={`row-watchlist-${coin.id}`}><div className="flex h-7 w-7 items-center justify-center rounded-md bg-slate-800 text-[9px] font-bold text-slate-300">{coin.symbol.slice(0, 2)}</div><div className="flex-1"><div className="text-[11px] font-bold text-slate-200">{coin.symbol}</div><div className="mono text-[9px] text-slate-600">{formatPrice(coin.price)}</div></div><div className={`mono text-[10px] ${coin.change24h >= 0 ? 'positive' : 'negative'}`}>{coin.change24h >= 0 ? '+' : ''}{coin.change24h.toFixed(2)}%</div><button type="button" onClick={(event) => { event.stopPropagation(); toggle(coin); }} data-testid={`button-remove-watchlist-${coin.id}`} className="ml-1 text-slate-700 hover:text-[hsl(var(--accent))]"><X size={13} /></button></div>)}</div> : <EmptyMini label="Star an asset to pin it here" />}</div></section>;
}

function CopyBots({ strategies }: { strategies: Strategy[] }) {
  const [running, setRunning] = useState<Record<string, boolean>>({});
  const botStrategyIds = ['v1', 'price-action', 'rsi-smc'];
  const botStrategies = botStrategyIds.map((id) => strategies.find((strategy) => strategy.id === id)).filter(Boolean) as Strategy[];
  return <section className="panel animate-rise delay-3"><div className="flex items-center justify-between border-b border-white/[.07] px-4 py-4"><div><div className="eyebrow">Whale copy bots</div><div className="mt-1 text-[12px] text-slate-400">Three strategy automations under your control</div></div><button type="button" data-testid="button-bot-add" className="rounded-md border border-white/[.08] p-1.5 text-slate-500 hover:text-[hsl(var(--primary))]"><Plus size={14} /></button></div><div className="divide-y divide-white/[.045]">{botStrategies.map((strategy, index) => { const active = running[strategy.id] ?? index === 0; const botLabel = strategy.id === 'v1' ? 'V1 + RSI 55' : strategy.id === 'price-action' ? 'Price Action + OB/FVG' : 'SMC + Divergence'; return <div key={strategy.id} className="flex items-center gap-3 px-4 py-3.5" data-testid={`row-bot-${strategy.id}`}><div className={`flex h-8 w-8 items-center justify-center rounded-lg ${active ? 'bg-[rgba(47,207,176,.1)] teal-text' : 'bg-white/[.045] text-slate-600'}`}><Bot size={15} /></div><div className="min-w-0 flex-1"><div className="truncate text-[11px] font-bold text-slate-200">{botLabel} Bot</div><div className="mt-0.5 flex items-center gap-1.5 text-[9px] text-slate-600"><span className={`status-dot ${active ? '' : 'amber'}`} />{active ? 'Monitoring' : 'Paused'} · {strategy.timeframe}</div></div><button type="button" onClick={() => setRunning((prev) => ({ ...prev, [strategy.id]: !active }))} data-testid={`button-toggle-bot-${strategy.id}`} className={`flex h-7 w-7 items-center justify-center rounded-md border ${active ? 'border-[rgba(47,207,176,.25)] teal-text' : 'border-white/[.08] text-slate-500'}`}>{active ? <Pause size={12} /> : <Play size={12} />}</button></div>; })}</div></section>;
}

function ExecutionLog({ logs, coins }: { logs: ExecutionLog[]; coins: Coin[] }) {
  const coinName = (id: string) => coins.find((coin) => coin.id === id)?.symbol ?? id;
  return <section className="panel animate-rise delay-3"><div className="flex items-center justify-between border-b border-white/[.07] px-4 py-4"><div><div className="eyebrow">Urdu execution log</div><div className="mt-1 text-[12px] text-slate-400">Live actions from your strategy desk</div></div><span className="flex items-center gap-1.5 mono text-[9px] teal-text"><span className="status-dot" /> STREAMING</span></div><div className="max-h-[282px] overflow-auto p-3">{logs.length ? logs.slice(0, 7).map((log) => <div key={log.id} className="relative flex gap-3 px-2 py-2.5" data-testid={`row-log-${log.id}`}><div className="relative pt-1.5"><span className={`status-dot ${log.type.toLowerCase().includes('sell') ? 'red' : log.type.toLowerCase().includes('warn') ? 'amber' : ''}`} />{log.id !== logs[Math.min(logs.length - 1, 6)].id && <span className="absolute left-[3px] top-4 h-full w-px bg-white/[.07]" />}</div><div className="min-w-0 flex-1"><div className="flex items-center justify-between gap-2"><span className="text-[10px] font-semibold text-slate-300">{log.message}</span><span className="mono shrink-0 text-[9px] text-slate-700">{timeAgo(log.timestamp)}</span></div><div className="mt-1 mono text-[9px] uppercase tracking-wide text-slate-600">{log.type} · {coinName(log.coinId)}</div></div></div>) : <EmptyMini label="No executions in this session" />}</div></section>;
}

function UrduNotepad() {
  const strategyNotes = [
    { name: 'V1 Smoothed Heikin Ashi + RSI 55', description: '30m entry کو 1D trend کے ساتھ align کریں۔', rules: ['Smoothed Heikin Ashi candle trend direction میں close ہو۔', 'RSI 55 سے اوپر اور rising ہو، پھر VSA confirmation لیں۔', 'Wick protected swing کو توڑے تو setup invalidate کریں؛ target 1% ہے۔'] },
    { name: 'Price Action / Scalp', description: '4H open-close اور 1H structure سے 1–3% scalp پلان کریں۔', rules: ['Valid 1H support/resistance کے بغیر Order Block یا FVG نہ بنائیں۔', '12h اور 24h heatmap میں مخالف liquidity ہو تو trade چھوڑ دیں۔', 'Uptrend میں RSI تقریباً 30، downtrend reversal میں RSI 15–25 اور structure shift ضروری ہے۔'] },
    { name: 'ICT Method 2', description: 'Session consolidation، sweep اور fair value return دیکھیں۔', rules: ['Dealing range اور active session کے آخری minutes پہلے mark کریں۔', 'Displacement اور clean liquidity sweep کے بعد fair value area پر entry لیں۔', 'Sweep extreme کے باہر close ہو تو setup ختم ہے۔'] },
    { name: 'Institutional OB + FVG', description: '1W/1D order-flow اور multi-drop validation استعمال کریں۔', rules: ['Body، wick اور trend-base candle classify کریں۔', '1W اور 1D structure، multi-drop reaction اور unfilled FVG سے block validate کریں۔', 'Fresh mitigation یا far-side break پر level invalidate کریں۔'] },
    { name: 'RSI Divergence + SMC Scalp 4', description: 'RSI divergence کو market structure shift کے ساتھ trade کریں۔', rules: ['Hidden bullish divergence RSI 30–40 میں confirmation ہے۔', 'Hidden bearish divergence RSI 50 سے اوپر Sell condition ہے۔', 'Fresh swing break کے خلاف ہو تو tight scalp فوراً invalidate کریں۔'] },
  ];
  return <section className="panel animate-rise delay-3">
    <div className="border-b border-white/[.07] px-4 py-4"><div className="eyebrow">Urdu strategy notepad</div><div className="mt-1 text-[12px] text-slate-400">حکمتِ عملی کے مرحلہ وار اصول</div></div>
    <div className="max-h-[490px] space-y-3 overflow-auto p-3" dir="rtl">{strategyNotes.map((strategy, index) => <div key={strategy.name} className="rounded-lg border border-white/[.05] bg-white/[.02] p-3 text-right"><div className="flex items-center gap-2"><span className="mono text-[9px] teal-text">۰{index + 1}</span><span className="text-[11px] font-bold text-slate-200">{strategy.name}</span></div><p className="mt-1 text-[10px] leading-relaxed text-slate-500">{strategy.description}</p><div className="mt-2 space-y-1.5">{strategy.rules.map((rule) => <div key={rule} className="flex items-start gap-2 text-[10px] leading-relaxed text-slate-300"><span className="teal-text">•</span><span>{rule}</span></div>)}</div></div>)}</div>
  </section>;
}

function EmptyMini({ label }: { label: string }) {
  return <div className="flex min-h-[100px] flex-col items-center justify-center gap-2 text-center"><Activity size={17} className="text-slate-700" /><span className="text-[10px] text-slate-600">{label}</span></div>;
}

function SkeletonWorkspace() {
  return <div className="space-y-4"><div className="grid grid-cols-2 gap-3 xl:grid-cols-4">{[1, 2, 3, 4].map((i) => <div className="panel h-[104px] p-4" key={i}><div className="skeleton h-3 w-20" /><div className="skeleton mt-4 h-7 w-24" /><div className="skeleton mt-2 h-2 w-32" /></div>)}</div><div className="grid gap-4 xl:grid-cols-[1.7fr_1fr]"><div className="panel h-[390px] p-4"><div className="skeleton h-3 w-32" /><div className="skeleton mt-7 h-8 w-full" />{[1, 2, 3, 4].map((i) => <div className="skeleton mt-7 h-4 w-full" key={i} />)}</div><div className="panel h-[390px] p-4"><div className="skeleton h-3 w-32" />{[1, 2, 3, 4].map((i) => <div className="skeleton mt-7 h-12 w-full" key={i} />)}</div></div></div>;
}

function Terminal() {
  const [activeView, setActiveView] = useState('overview');
  const [selectedPairSymbol, setSelectedPairSymbol] = useState<string | null>(null);
  const [selectedStrategyId, setSelectedStrategyId] = useState<string | null>(null);
  const marketFeed = useTopUsdtPairs();
  const strategiesQuery = useListStrategies();
  const strategies = strategiesQuery.data ?? [];
  const selectedPair = marketFeed.pairs.find((pair) => pair.symbol === selectedPairSymbol) ?? marketFeed.pairs[0];
  const selectedStrategy = strategies.find((item) => item.id === selectedStrategyId) ?? strategies[0];
  useEffect(() => {
    if (!marketFeed.pairs.length) {
      setSelectedPairSymbol(null);
      return;
    }
    if (!marketFeed.pairs.some((pair) => pair.symbol === selectedPairSymbol)) {
      setSelectedPairSymbol(marketFeed.pairs[0].symbol);
    }
  }, [marketFeed.pairs, selectedPairSymbol]);

  const selectPair = (symbol: string) => {
    setSelectedPairSymbol(symbol);
    setActiveView('chart');
  };

  return <div className="terminal-shell flex">
    <Sidebar activeView={activeView} setActiveView={setActiveView} connection={marketFeed.status} />
    <main className="min-w-0 flex-1">
      <Topbar activeView={activeView} connection={marketFeed.status} />
       <div className="mx-auto max-w-[1540px] px-4 pb-10 pt-5 sm:px-6 lg:px-8">
         <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
           <div>
             <div className="flex items-center gap-2"><span className={`status-dot ${marketFeed.status === 'connected' ? '' : 'amber'}`} /><span className="mono text-[10px] font-medium tracking-[.12em] teal-text">BINANCE SPOT · PUBLIC FEED</span></div>
             <h1 className="display-font mt-2 text-[25px] font-bold tracking-tight text-slate-100 sm:text-[29px]">Top 20 USDT pairs<span className="text-[hsl(var(--primary))]">.</span></h1>
             <p className="mt-1 text-[12px] text-slate-500">24h quote-volume ranking refreshes every 10 minutes. Signal calculations use closed candles only.</p>
           </div>
           <div className="flex gap-2 lg:hidden">
             {(['overview', 'chart'] as const).map((view) => <button key={view} type="button" onClick={() => setActiveView(view)} className={`rounded-md border px-3 py-2 text-[10px] font-semibold ${activeView === view ? 'border-[rgba(47,207,176,.3)] teal-text' : 'border-white/[.08] text-slate-500'}`}>{view === 'overview' ? 'Scanner' : 'Chart'}</button>)}
           </div>
         </div>
         <div className="space-y-4">
           {activeView === 'overview' && (
             <TopUsdtSignals
               pairs={marketFeed.pairs}
               status={marketFeed.status}
               isLoading={marketFeed.isLoading}
               lastTickerRefresh={marketFeed.lastTickerRefresh}
               error={marketFeed.error}
               selectedSymbol={selectedPair?.symbol ?? null}
               onSelectPair={selectPair}
             />
           )}
           {activeView === 'chart' && (
             <ChartMapping
               pair={selectedPair}
               strategy={selectedStrategy}
               strategies={strategies}
               onStrategyChange={setSelectedStrategyId}
             />
           )}
         </div>
      </div>
    </main>
  </div>;
}

function Router() {
  return <ErrorBoundary resetKey={useLocation()[0]}><Switch><Route path="/" component={Terminal} /><Route path="/coin" component={CoinPage} /><Route component={NotFound} /></Switch></ErrorBoundary>;
}

function App() {
  return <QueryClientProvider client={queryClient}><TooltipProvider><WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}><Router /></WouterRouter><Toaster /></TooltipProvider></QueryClientProvider>;
}

export default App;