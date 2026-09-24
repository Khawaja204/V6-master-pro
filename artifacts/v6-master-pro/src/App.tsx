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
import {
  useGetMarketSnapshot,
  useGetWatchlist,
  useHealthCheck,
  useListExecutionLogs,
  useListStrategies,
  useToggleWatchlist,
} from '@workspace/api-client-react';
import type { Coin, ExecutionLog, Strategy, VsaCheck } from '@workspace/api-client-react';
import { ErrorBoundary } from '@/components/error-boundary';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import NotFound from '@/pages/not-found';
import { Route, Switch, Router as WouterRouter, useLocation } from 'wouter';
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

const timeAgo = (timestamp: string) => {
  const mins = Math.max(1, Math.round((Date.now() - new Date(timestamp).getTime()) / 60000));
  return mins < 60 ? `${mins}m ago` : `${Math.round(mins / 60)}h ago`;
};

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

function Sidebar({ activeView, setActiveView }: { activeView: string; setActiveView: (view: string) => void }) {
  const items = [
    { id: 'overview', label: 'Workspace', icon: LayoutDashboard },
    { id: 'hunter', label: 'Coin hunter', icon: Target },
    { id: 'signals', label: 'Signal desk', icon: Crosshair },
    { id: 'strategies', label: 'Strategies', icon: LineChart },
    { id: 'bots', label: 'Copy bots', icon: Bot },
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
      </nav>
      <div className="mt-8 border-t border-white/[.07] pt-6 px-3 eyebrow">System</div>
      <div className="mt-3 space-y-1">
        <button type="button" onClick={() => setActiveView('watchlist')} data-testid="button-nav-watchlist" className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-slate-500 transition-colors hover:bg-white/[.035] hover:text-slate-200">
          <Star size={16} strokeWidth={1.8} />
          <span className="text-[12px] font-semibold">Watchlist</span>
        </button>
        <button type="button" onClick={() => setActiveView('logs')} data-testid="button-nav-logs" className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-slate-500 transition-colors hover:bg-white/[.035] hover:text-slate-200">
          <Activity size={16} strokeWidth={1.8} />
          <span className="text-[12px] font-semibold">Execution log</span>
        </button>
      </div>
      <div className="mt-auto pt-24">
        <div className="panel-muted p-3">
          <div className="flex items-center gap-2 text-[11px] font-semibold text-slate-300"><ShieldCheck size={14} className="teal-text" /> Terminal status</div>
          <div className="mt-2 flex items-center gap-2 text-[10px] text-slate-500"><span className="status-dot" /> API connected <span className="ml-auto mono text-[9px] text-slate-600">LIVE</span></div>
        </div>
        <button type="button" onClick={() => setActiveView('settings')} data-testid="button-nav-settings" className="mt-4 flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-slate-500 hover:text-slate-200">
          <Settings2 size={16} strokeWidth={1.8} /><span className="text-[12px] font-semibold">Terminal settings</span>
        </button>
      </div>
    </aside>
  );
}

function Topbar({ activeView, onRefresh, refreshing, health }: { activeView: string; onRefresh: () => void; refreshing: boolean; health?: { status: string } }) {
  return (
    <header className="flex min-h-[74px] items-center justify-between gap-4 border-b border-white/[.07] px-5 py-4 lg:px-8">
      <div className="flex items-center gap-4">
        <div className="lg:hidden"><Logo /></div>
        <div className="hidden h-8 w-px bg-white/[.08] lg:block" />
        <div>
          <div className="eyebrow">{activeView === 'overview' ? 'Live market intelligence' : activeView.replace('-', ' ')}</div>
          <div className="mt-1 text-[12px] text-slate-500">One workspace for decisive execution</div>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <div className="hidden items-center gap-2 rounded-full border border-white/[.08] bg-white/[.025] px-3 py-1.5 md:flex">
          <Wifi size={13} className="teal-text" />
          <span className="mono text-[10px] text-slate-400">{health?.status === 'ok' ? 'FEED STABLE' : 'SYNCING FEED'}</span>
        </div>
        <button type="button" onClick={onRefresh} disabled={refreshing} data-testid="button-refresh-terminal" className="flex h-8 items-center gap-2 rounded-lg border border-white/[.08] px-2.5 text-slate-400 transition hover:border-[hsl(var(--primary))] hover:text-[hsl(var(--primary))]">
          <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} /><span className="hidden text-[11px] font-semibold sm:block">Refresh</span>
        </button>
        <button type="button" data-testid="button-notifications" className="relative flex h-8 w-8 items-center justify-center rounded-lg border border-white/[.08] text-slate-400 hover:text-slate-200">
          <Bell size={15} /><span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-[hsl(var(--accent))]" />
        </button>
        <div className="ml-1 flex h-8 w-8 items-center justify-center rounded-full bg-[#2b766e] text-[11px] font-bold text-[#d9fff4]" data-testid="avatar-user">AK</div>
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
      <StatCard label="Market breadth" value={`${marketBreadth.toFixed(1)}%`} sub="▲ 4.8% vs previous session" tone="positive" icon={BarChart3} />
      <StatCard label="Session P&L" value={`${sessionPnl >= 0 ? '+' : '-'}$${Math.abs(sessionPnl).toFixed(2)}`} sub="▲ 12.6% from open" tone="positive" icon={TrendingUp} />
      <StatCard label="Assets tracked" value={String(coinCount).padStart(2, '0')} sub="Across 12 active venues" tone="neutral" icon={Grid2X2} />
      <StatCard label="Signal confidence" value="82.4%" sub="High conviction · 6 setups" tone="amber" icon={Zap} />
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
    .slice(0, 8), [coins, huntingMode, search, sort]);
  return (
    <section className="panel min-w-0 animate-rise delay-1">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[.07] px-4 py-4">
        <div><div className="eyebrow">{huntingMode ? 'Coin hunter / top 500 screen' : 'Market overview'}</div><div className="mt-1 text-[12px] text-slate-400">{huntingMode ? '≥200K followers · ≥70% circulating · locked max supply ≤50B' : 'Momentum across your trading universe'}</div></div>
        <div className="flex items-center gap-2">
          <div className="relative"><Search size={13} className="absolute left-2.5 top-2.5 text-slate-600" /><input value={search} onChange={(e) => setSearch(e.target.value)} data-testid="input-market-search" placeholder="Find asset" className="h-8 w-[126px] rounded-md border border-white/[.08] bg-black/10 pl-8 pr-2 text-[11px] text-slate-300 outline-none placeholder:text-slate-600 focus:border-[hsl(var(--primary))]" /></div>
          <button type="button" onClick={() => setSort(sort === 'change' ? 'volume' : 'change')} data-testid="button-market-sort" className="flex h-8 items-center gap-1.5 rounded-md border border-white/[.08] px-2 text-[10px] font-semibold text-slate-500 hover:text-slate-200"><ListFilter size={13} /> {sort === 'change' ? 'Change' : 'Volume'} <ChevronDown size={12} /></button>
        </div>
      </div>
      <div className="mobile-scroll">
          <div className="min-w-[820px]">
           <div className={`grid ${huntingMode ? 'grid-cols-[1.3fr_.8fr_.7fr_.85fr_.75fr_.85fr_1fr_40px]' : 'grid-cols-[1.35fr_.85fr_.75fr_.85fr_1fr_40px]'} gap-3 px-4 py-3 eyebrow`}><span>Asset</span><span>Last price</span><span>24h</span><span>Volume</span>{huntingMode && <><span>Circulating</span><span>Supply cap</span></>}<span>VSA state</span><span /></div>
          {filtered.length ? filtered.map((coin) => (
             <div role="button" tabIndex={0} key={coin.id} onClick={() => onSelectCoin(coin)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') onSelectCoin(coin); }} className={`grid w-full ${huntingMode ? 'grid-cols-[1.3fr_.8fr_.7fr_.85fr_.75fr_.85fr_1fr_40px]' : 'grid-cols-[1.35fr_.85fr_.75fr_.85fr_1fr_40px]'} items-center gap-3 border-t border-white/[.045] px-4 py-3 text-left transition-colors hover:bg-white/[.025]`} data-testid={`row-market-${coin.id}`}>
              <div className="flex items-center gap-2.5"><button type="button" onClick={() => toggle(coin)} data-testid={`button-favorite-${coin.id}`} className={watchlist.includes(coin.id) ? 'amber-text' : 'text-slate-700 hover:text-slate-300'}><Star size={14} fill={watchlist.includes(coin.id) ? 'currentColor' : 'none'} /></button><div className="flex h-7 w-7 items-center justify-center rounded-md bg-slate-800 text-[9px] font-bold text-slate-300">{coin.symbol.slice(0, 2)}</div><div><div className="text-[11px] font-bold text-slate-200">{coin.symbol}</div><div className="text-[9px] text-slate-600">{coin.name}</div></div></div>
              <span className="mono text-[11px] text-slate-300">{formatPrice(coin.price)}</span>
              <span className={`mono text-[11px] font-medium ${coin.change24h >= 0 ? 'positive' : 'negative'}`}>{coin.change24h >= 0 ? '+' : ''}{coin.change24h.toFixed(2)}%</span>
              <span className="mono text-[10px] text-slate-500">{formatUsd(coin.volume24h)}</span>
               {huntingMode && <><span className="mono text-[10px] teal-text">{((coin.circulatingSupply / coin.maxSupply) * 100).toFixed(1)}%</span><span className="mono text-[10px] text-slate-500">{coin.maxSupply >= 1000 ? `${(coin.maxSupply / 1000).toFixed(1)}B` : `${coin.maxSupply.toFixed(1)}M`}</span></>}
              <span className={`flex items-center gap-1.5 text-[10px] font-semibold ${coin.vsa.includes('manipulation') ? 'red-text' : 'positive'}`}><span className={`status-dot ${coin.vsa.includes('manipulation') ? 'red' : ''}`} />{coin.vsa === 'ok_up' ? 'Accumulation' : coin.vsa === 'ok_down' ? 'Distribution' : coin.vsa.replace('_', ' ')}</span>
               <span className="flex justify-end text-slate-600"><MoreHorizontal size={15} /></span>
             </div>
          )) : <div className="px-4 py-10 text-center text-slate-500">No assets match this search.</div>}
        </div>
      </div>
    </section>
  );
}

function VsaDesk({ checks, coins, onSelectCoin }: { checks: VsaCheck[]; coins: Coin[]; onSelectCoin: (coin: Coin) => void }) {
  const getCoin = (id: string) => coins.find((coin) => coin.id === id);
  return (
    <section className="panel animate-rise delay-2">
      <div className="flex items-center justify-between border-b border-white/[.07] px-4 py-4"><div><div className="eyebrow">VSA signal desk</div><div className="mt-1 text-[12px] text-slate-400">Volume spread analysis anomalies</div></div><button type="button" data-testid="button-vsa-filter" className="rounded-md border border-white/[.08] p-1.5 text-slate-500 hover:text-slate-200"><ListFilter size={14} /></button></div>
      <div className="space-y-2 p-3">
        {checks.slice(0, 4).map((check) => {
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

function ChartMapping({ coin, strategy }: { coin?: Coin; strategy?: Strategy }) {
  const [period, setPeriod] = useState('1H');
  const chartContainer = useRef<HTMLDivElement | null>(null);
  const periods = ['15M', '1H', '4H', '1D'];
  useEffect(() => {
    if (!chartContainer.current || !coin) return;
    const container = chartContainer.current;
    const chart = createChart(container, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#64748b' },
      grid: { vertLines: { color: 'rgba(148, 163, 184, 0.06)' }, horzLines: { color: 'rgba(148, 163, 184, 0.06)' } },
      rightPriceScale: { borderColor: 'rgba(148, 163, 184, 0.12)' },
      timeScale: { borderColor: 'rgba(148, 163, 184, 0.12)', timeVisible: true, secondsVisible: false },
      crosshair: { vertLine: { color: 'rgba(47, 207, 176, .45)', labelBackgroundColor: '#173b37' }, horzLine: { color: 'rgba(47, 207, 176, .45)', labelBackgroundColor: '#173b37' } },
    });
    const baseTime = Math.floor(Date.now() / 1000) - 23 * 3600;
    const candles = Array.from({ length: 24 }, (_, index) => {
      const wave = Math.sin(index / 1.8) * coin.price * 0.006;
      const trend = (coin.change24h / 100) * coin.price * (index / 24);
      const open = coin.price - coin.price * 0.018 + wave + trend;
      const close = open + Math.cos(index / 2.2) * coin.price * 0.004 + coin.price * 0.0015;
      const high = Math.max(open, close) + coin.price * 0.005;
      const low = Math.min(open, close) - coin.price * 0.004;
      return { time: (baseTime + index * 3600) as Time, open, high, low, close };
    });
    const series = chart.addSeries(CandlestickSeries, { upColor: '#2fcfb0', downColor: '#f27a78', borderVisible: false, wickUpColor: '#2fcfb0', wickDownColor: '#f27a78' });
    series.setData(candles);
    const entry = coin.price * 0.992;
    const stop = coin.price * 0.976;
    const takeProfit = coin.price * (1 + (strategy?.id === 'price-action' ? 0.025 : 0.01));
    const levels = [
      { value: entry, color: '#f6be51', title: 'ENTRY' },
      { value: stop, color: '#f27a78', title: 'INVALIDATION' },
      { value: takeProfit, color: '#2fcfb0', title: 'TARGET' },
    ];
    levels.forEach((level) => {
      const line = chart.addSeries(LineSeries, { color: level.color, lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: true, lastValueVisible: true, title: level.title });
      line.setData([{ time: baseTime as Time, value: level.value }, { time: (baseTime + 23 * 3600) as Time, value: level.value }]);
    });
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [coin, period, strategy]);
  return (
    <section className="panel animate-rise delay-3 overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[.07] px-4 py-4"><div><div className="eyebrow">TradingView lightweight chart · mapped levels</div><div className="mt-1 flex items-center gap-2 text-[12px] text-slate-300"><span className="font-bold">{coin?.symbol ?? 'BTC'} / USDT</span><span className="mono text-[10px] text-slate-500">{coin ? formatPrice(coin.price) : '$0.00'}</span><span className={coin?.change24h && coin.change24h > 0 ? 'positive mono text-[10px]' : 'negative mono text-[10px]'}>{coin ? `${coin.change24h > 0 ? '+' : ''}${coin.change24h.toFixed(2)}%` : '--'}</span></div></div><div className="flex rounded-md border border-white/[.08] p-0.5">{periods.map((item) => <button type="button" key={item} onClick={() => setPeriod(item)} data-testid={`button-chart-${item}`} className={`rounded px-2 py-1 mono text-[9px] ${period === item ? 'bg-white/[.1] text-slate-200' : 'text-slate-600'}`}>{item}</button>)}</div></div>
      <div className="relative h-[270px] p-3"><div ref={chartContainer} className="h-full w-full" /></div>
      <div className="flex flex-wrap gap-3 border-t border-white/[.07] px-4 py-3 mono text-[9px] text-slate-500"><span className="teal-text">TARGET {strategy?.id === 'price-action' ? '2.5%' : '1.0%'}</span><span className="amber-text">ENTRY -0.8%</span><span className="red-text">INVALIDATION -2.4%</span><span className="ml-auto text-slate-600">{strategy?.shortName ?? 'V1'} overlay active</span></div>
    </section>
  );
}

function Watchlist({ coins, ids, toggle, onSelectCoin }: { coins: Coin[]; ids: string[]; toggle: (coin: Coin) => void; onSelectCoin: (coin: Coin) => void }) {
  const entries = ids.map((id) => coins.find((coin) => coin.id === id)).filter(Boolean) as Coin[];
  return <section className="panel animate-rise delay-3"><div className="flex items-center justify-between border-b border-white/[.07] px-4 py-4"><div><div className="eyebrow">Your watchlist</div><div className="mt-1 text-[12px] text-slate-400">Pinned for the next decision</div></div><button type="button" data-testid="button-watchlist-add" className="rounded-md border border-white/[.08] p-1.5 text-slate-500 hover:text-[hsl(var(--primary))]"><Plus size={14} /></button></div><div className="p-3">{entries.length ? <div className="space-y-1">{entries.slice(0, 5).map((coin) => <div key={coin.id} role="button" tabIndex={0} onClick={() => onSelectCoin(coin)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') onSelectCoin(coin); }} className="flex items-center gap-2.5 rounded-lg px-2 py-2.5 hover:bg-white/[.025]" data-testid={`row-watchlist-${coin.id}`}><div className="flex h-7 w-7 items-center justify-center rounded-md bg-slate-800 text-[9px] font-bold text-slate-300">{coin.symbol.slice(0, 2)}</div><div className="flex-1"><div className="text-[11px] font-bold text-slate-200">{coin.symbol}</div><div className="mono text-[9px] text-slate-600">{formatPrice(coin.price)}</div></div><div className={`mono text-[10px] ${coin.change24h >= 0 ? 'positive' : 'negative'}`}>{coin.change24h >= 0 ? '+' : ''}{coin.change24h.toFixed(2)}%</div><button type="button" onClick={(event) => { event.stopPropagation(); toggle(coin); }} data-testid={`button-remove-watchlist-${coin.id}`} className="ml-1 text-slate-700 hover:text-[hsl(var(--accent))]"><X size={13} /></button></div>)}</div> : <EmptyMini label="Star an asset to pin it here" />}</div></section>;
}

function CopyBots({ strategies }: { strategies: Strategy[] }) {
  const [running, setRunning] = useState<Record<string, boolean>>({});
  return <section className="panel animate-rise delay-3"><div className="flex items-center justify-between border-b border-white/[.07] px-4 py-4"><div><div className="eyebrow">Copy bots</div><div className="mt-1 text-[12px] text-slate-400">Automations under your control</div></div><button type="button" data-testid="button-bot-add" className="rounded-md border border-white/[.08] p-1.5 text-slate-500 hover:text-[hsl(var(--primary))]"><Plus size={14} /></button></div><div className="divide-y divide-white/[.045]">{strategies.slice(0, 3).map((strategy, index) => { const active = running[strategy.id] ?? index === 0; return <div key={strategy.id} className="flex items-center gap-3 px-4 py-3.5" data-testid={`row-bot-${strategy.id}`}><div className={`flex h-8 w-8 items-center justify-center rounded-lg ${active ? 'bg-[rgba(47,207,176,.1)] teal-text' : 'bg-white/[.045] text-slate-600'}`}><Bot size={15} /></div><div className="min-w-0 flex-1"><div className="truncate text-[11px] font-bold text-slate-200">{strategy.shortName} Bot</div><div className="mt-0.5 flex items-center gap-1.5 text-[9px] text-slate-600"><span className={`status-dot ${active ? '' : 'amber'}`} />{active ? 'Monitoring' : 'Paused'} · {strategy.timeframe}</div></div><button type="button" onClick={() => setRunning((prev) => ({ ...prev, [strategy.id]: !active }))} data-testid={`button-toggle-bot-${strategy.id}`} className={`flex h-7 w-7 items-center justify-center rounded-md border ${active ? 'border-[rgba(47,207,176,.25)] teal-text' : 'border-white/[.08] text-slate-500'}`}>{active ? <Pause size={12} /> : <Play size={12} />}</button></div>; })}</div></section>;
}

function ExecutionLog({ logs, coins }: { logs: ExecutionLog[]; coins: Coin[] }) {
  const coinName = (id: string) => coins.find((coin) => coin.id === id)?.symbol ?? id;
  return <section className="panel animate-rise delay-3"><div className="flex items-center justify-between border-b border-white/[.07] px-4 py-4"><div><div className="eyebrow">Urdu execution log</div><div className="mt-1 text-[12px] text-slate-400">Live actions from your strategy desk</div></div><span className="flex items-center gap-1.5 mono text-[9px] teal-text"><span className="status-dot" /> STREAMING</span></div><div className="max-h-[282px] overflow-auto p-3">{logs.length ? logs.slice(0, 7).map((log) => <div key={log.id} className="relative flex gap-3 px-2 py-2.5" data-testid={`row-log-${log.id}`}><div className="relative pt-1.5"><span className={`status-dot ${log.type.toLowerCase().includes('sell') ? 'red' : log.type.toLowerCase().includes('warn') ? 'amber' : ''}`} />{log.id !== logs[Math.min(logs.length - 1, 6)].id && <span className="absolute left-[3px] top-4 h-full w-px bg-white/[.07]" />}</div><div className="min-w-0 flex-1"><div className="flex items-center justify-between gap-2"><span className="text-[10px] font-semibold text-slate-300">{log.message}</span><span className="mono shrink-0 text-[9px] text-slate-700">{timeAgo(log.timestamp)}</span></div><div className="mt-1 mono text-[9px] uppercase tracking-wide text-slate-600">{log.type} · {coinName(log.coinId)}</div></div></div>) : <EmptyMini label="No executions in this session" />}</div></section>;
}

function UrduNotepad() {
  const rules = [
    ['مرحلہ ۱', 'مارکیٹ کا رجحان اور 1D structure دیکھیں۔'],
    ['مرحلہ ۲', '30m پر RSI 55 filter اور smoothed Heikin Ashi confirmation لیں۔'],
    ['مرحلہ ۳', 'Volume اور Price کی سمت کو VSA desk سے verify کریں۔'],
    ['مرحلہ ۴', 'Entry، invalidation اور 1% TP پہلے سے chart پر map کریں۔'],
    ['مرحلہ ۵', 'Liquidity sweep یا order block کے بغیر trade execute نہ کریں۔'],
  ];
  return <section className="panel animate-rise delay-3">
    <div className="border-b border-white/[.07] px-4 py-4"><div className="eyebrow">Urdu strategy notepad</div><div className="mt-1 text-[12px] text-slate-400">حکمتِ عملی کے مرحلہ وار اصول</div></div>
    <div className="space-y-2 p-3" dir="rtl">{rules.map(([step, rule]) => <div key={step} className="flex items-start gap-3 rounded-lg border border-white/[.05] bg-white/[.02] p-3 text-right"><span className="mono text-[9px] teal-text">{step}</span><span className="text-[11px] leading-relaxed text-slate-300">{rule}</span></div>)}</div>
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
  const [selectedCoinId, setSelectedCoinId] = useState<string | null>(null);
  const [selectedStrategyId, setSelectedStrategyId] = useState<string | null>(null);
  const market = useGetMarketSnapshot();
  const strategiesQuery = useListStrategies();
  const watchlistQuery = useGetWatchlist();
  const logsQuery = useListExecutionLogs();
  const healthQuery = useHealthCheck();
  const toggleWatchlist = useToggleWatchlist();
  const snapshot = market.data;
  const coins = snapshot?.coins ?? [];
  const strategies = strategiesQuery.data ?? [];
  const watchlist = watchlistQuery.data?.coinIds ?? [];
  const logs = logsQuery.data ?? [];
  const [localWatchlist, setLocalWatchlist] = useState<string[] | null>(null);
  const ids = localWatchlist ?? watchlist;
  const selectedCoin = coins.find((coin) => coin.id === selectedCoinId) ?? coins[0];
  const selectedStrategy = strategies.find((item) => item.id === selectedStrategyId) ?? strategies[0];
  const isLoading = market.isLoading || strategiesQuery.isLoading || watchlistQuery.isLoading || logsQuery.isLoading;
  const refresh = () => { void market.refetch(); void strategiesQuery.refetch(); void watchlistQuery.refetch(); void logsQuery.refetch(); void healthQuery.refetch(); };
  const selectCoin = (coin: Coin) => {
    setSelectedCoinId(coin.id);
    if (activeView === 'overview') setActiveView('hunter');
  };
  const toggle = (coin: Coin) => {
    const favorite = !ids.includes(coin.id);
    setLocalWatchlist(favorite ? [...ids, coin.id] : ids.filter((id) => id !== coin.id));
    toggleWatchlist.mutate({ coinId: coin.id, data: { favorite } }, { onSuccess: (next) => setLocalWatchlist(next.coinIds) });
  };
  return <div className="terminal-shell flex">
    <Sidebar activeView={activeView} setActiveView={setActiveView} />
    <main className="min-w-0 flex-1">
      <Topbar activeView={activeView} onRefresh={refresh} refreshing={market.isFetching} health={healthQuery.data} />
      <div className="mx-auto max-w-[1540px] px-4 pb-10 pt-5 sm:px-6 lg:px-8">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-4"><div><div className="flex items-center gap-2"><span className="status-dot" /><span className="mono text-[10px] font-medium tracking-[.12em] teal-text">MARKETS OPEN · 24/7</span></div><h1 className="display-font mt-2 text-[25px] font-bold tracking-tight text-slate-100 sm:text-[29px]">Good morning, Arman<span className="text-[hsl(var(--primary))]">.</span></h1><p className="mt-1 text-[12px] text-slate-500">Your edge, in one view. Last sync {snapshot ? timeAgo(snapshot.updatedAt) : 'pending'}.</p></div><button type="button" data-testid="button-focus-mode" onClick={() => setActiveView('hunter')} className="flex items-center gap-2 rounded-lg border border-[rgba(47,207,176,.24)] bg-[rgba(47,207,176,.07)] px-3 py-2 text-[11px] font-semibold teal-text hover:bg-[rgba(47,207,176,.12)]"><Crosshair size={14} /> Open focus mode <ChevronRight size={13} /></button></div>
         {isLoading ? <SkeletonWorkspace /> : market.error ? <div className="panel flex min-h-[320px] flex-col items-center justify-center gap-3 p-6 text-center"><CircleHelp size={30} className="red-text" /><h2 className="text-[15px] font-bold text-slate-200">Market feed unavailable</h2><p className="max-w-sm text-[11px] text-slate-500">The terminal could not reach the market snapshot. Check the connection and try again.</p><button type="button" onClick={refresh} data-testid="button-retry-market" className="rounded-md bg-[hsl(var(--primary))] px-3 py-2 text-[11px] font-bold text-[hsl(var(--primary-foreground))]">Retry feed</button></div> : <div className="space-y-4">
           {(activeView === 'overview' || activeView === 'hunter' || activeView === 'strategies') && <OverviewStats marketBreadth={snapshot?.marketBreadth ?? 0} sessionPnl={snapshot?.sessionPnl ?? 0} coinCount={coins.length} />}
           {activeView === 'overview' && <><div className="grid gap-4 xl:grid-cols-[1.65fr_1fr]"><MarketOverview coins={coins} watchlist={ids} toggle={toggle} onSelectCoin={selectCoin} /><VsaDesk checks={snapshot?.vsaChecks ?? []} coins={coins} onSelectCoin={selectCoin} /></div><div className="grid gap-4 xl:grid-cols-[1.1fr_1fr_1fr]"><StrategyDesk strategies={strategies} onStrategyChange={(item) => setSelectedStrategyId(item.id)} /><ChartMapping coin={selectedCoin} strategy={selectedStrategy} /><Watchlist coins={coins} ids={ids} toggle={toggle} onSelectCoin={selectCoin} /></div><div className="grid gap-4 xl:grid-cols-[1fr_1fr]"><CopyBots strategies={strategies} /><ExecutionLog logs={logs} coins={coins} /></div></>}
           {activeView === 'hunter' && <><div className="grid gap-4 xl:grid-cols-[1.6fr_1fr]"><MarketOverview coins={coins} watchlist={ids} toggle={toggle} onSelectCoin={selectCoin} huntingMode /><ChartMapping coin={selectedCoin} strategy={selectedStrategy} /></div><Watchlist coins={coins} ids={ids} toggle={toggle} onSelectCoin={selectCoin} /></>}
           {activeView === 'signals' && <div className="grid gap-4 xl:grid-cols-[1fr_1.15fr]"><VsaDesk checks={snapshot?.vsaChecks ?? []} coins={coins} onSelectCoin={selectCoin} /><ChartMapping coin={selectedCoin} strategy={selectedStrategy} /></div>}
           {activeView === 'strategies' && <div className="grid gap-4 xl:grid-cols-[1fr_1.15fr]"><StrategyDesk strategies={strategies} onStrategyChange={(item) => setSelectedStrategyId(item.id)} /><ChartMapping coin={selectedCoin} strategy={selectedStrategy} /></div>}
           {activeView === 'bots' && <div className="grid gap-4 xl:grid-cols-[1fr_1fr]"><CopyBots strategies={strategies} /><Watchlist coins={coins} ids={ids} toggle={toggle} onSelectCoin={selectCoin} /><div className="xl:col-span-2"><ChartMapping coin={selectedCoin} strategy={selectedStrategy} /></div></div>}
           {activeView === 'watchlist' && <div className="grid gap-4 xl:grid-cols-[.8fr_1.2fr]"><Watchlist coins={coins} ids={ids} toggle={toggle} onSelectCoin={selectCoin} /><ChartMapping coin={selectedCoin} strategy={selectedStrategy} /></div>}
           {activeView === 'logs' && <div className="grid gap-4 xl:grid-cols-[1fr_1fr]"><UrduNotepad /><ExecutionLog logs={logs} coins={coins} /><div className="xl:col-span-2"><ChartMapping coin={selectedCoin} strategy={selectedStrategy} /></div></div>}
           {activeView === 'settings' && <section className="panel max-w-2xl p-5"><div className="eyebrow">Terminal settings</div><h2 className="mt-2 text-xl font-bold text-slate-100">Feed and execution controls</h2><p className="mt-2 text-[12px] leading-relaxed text-slate-500">Live market connectors can be attached here without changing the strategy contract. The current terminal runs on the typed market snapshot and keeps favorite states in the active session.</p><div className="mt-5 space-y-2"><div className="panel-muted flex items-center justify-between p-3 text-[11px]"><span>Market snapshot polling</span><span className="teal-text">CONNECTED</span></div><div className="panel-muted flex items-center justify-between p-3 text-[11px]"><span>Chart overlay engine</span><span className="teal-text">LIGHTWEIGHT CHARTS</span></div><div className="panel-muted flex items-center justify-between p-3 text-[11px]"><span>Urdu execution stream</span><span className="teal-text">STREAMING</span></div></div></section>}
         </div>}
      </div>
    </main>
  </div>;
}

function Router() {
  return <ErrorBoundary resetKey={useLocation()[0]}><Switch><Route path="/" component={Terminal} /><Route component={NotFound} /></Switch></ErrorBoundary>;
}

function App() {
  return <QueryClientProvider client={queryClient}><TooltipProvider><WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}><Router /></WouterRouter><Toaster /></TooltipProvider></QueryClientProvider>;
}

export default App;