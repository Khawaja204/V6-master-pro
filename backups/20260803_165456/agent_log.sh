#!/bin/bash
# =============================================================================
# agent_log.sh — V6 Master Pro | Agent Instruction & Work Tracker
# Run: bash agent_log.sh
# Alias: ag='bash ~/agent_log.sh'
# =============================================================================

OUTPUT="agent_work_log.txt"
TIMESTAMP=$(date -u +"%a %b %d %I:%M:%S %p UTC %Y")
PKT_TIME=$(date -d "+5 hours" +"%Y-%m-%d %H:%M:%S PKT" 2>/dev/null || date -v+5H +"%Y-%m-%d %H:%M:%S PKT" 2>/dev/null || echo "PKT_TIME_UNKNOWN")

# ── Colors ──
GRN='\033[0;32m'
YLW='\033[1;33m'
RED='\033[0;31m'
BLU='\033[0;34m'
NC='\033[0m'

# ── Manual Note Handler ──
if [ "$1" = "note" ] && [ -n "$2" ]; then
    if [ ! -f "$OUTPUT" ]; then
        echo -e "${RED}❌ $OUTPUT not found. Run 'bash agent_log.sh' first.${NC}"
        exit 1
    fi
    echo "[MANUAL] $PKT_TIME | $2" >> "$OUTPUT"
    echo -e "${GRN}✅ Note appended.${NC}"
    exit 0
fi

if [ "$1" = "tail" ]; then
    if [ -f "$OUTPUT" ]; then
        tail -n "${2:-20}" "$OUTPUT"
    else
        echo "No log file yet."
    fi
    exit 0
fi

echo -e "${BLU}📝 Generating Agent Work Log...${NC}"

# ── Build the log ──
{
  echo "╔══════════════════════════════════════════════════════════════════════════════╗"
  echo "║           🤖 V6 MASTER PRO — AGENT INSTRUCTION & WORK LOG                   ║"
  echo "║           Generated: $TIMESTAMP  |  PKT: $PKT_TIME              ║"
  echo "╚══════════════════════════════════════════════════════════════════════════════╝"
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "📋 SECTION 1: PROJECT ORIGIN & INITIAL INSTRUCTIONS (Agent Start)"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  echo "Project Name        : V6 Master Pro Institutional Crypto Trading Bot"
  echo "Platform            : Replit (dev) + Render (production)"
  echo "Agent First Engaged : 24-Jul-2026"
  echo "Current Version     : v8 (as of main.py header)"
  echo "User Type           : Free Kimi version (session-based, no persistent memory)"
  echo "Project Export      : saveproj.sh (sp alias) → project.txt"
  echo "Env File            : V6_Master_Pro_UI/.env"
  echo ""
  echo "🎯 ORIGINAL MANDATE (P0 — Must Have):"
  echo "   1. OCO (One-Cancels-Other) Orders"
  echo "   2. SQLite Database Migration (replace JSON files)"
  echo "   3. API Key Encryption (at-rest security)"
  echo ""
  echo "🎯 P1 — High Priority:"
  echo "   4. WebSocket Live Prices (Binance stream)"
  echo "   5. Partial Take-Profit (TP1/TP2/TP3 scaling)"
  echo "   6. Multi-Timeframe Confirmation (15m + 1h + 4h confluence)"
  echo ""
  echo "🎯 P2 — Future Backlog:"
  echo "   7. Portfolio Heatmap"
  echo "   8. Funding Rate Arbitrage"
  echo "   9. 2FA / Mobile UI"
  echo "  10. PnL Chart & Trade Journal"
  echo "  11. Enhanced API Encryption + Audit Trail"
  echo "  12. Auto-Deploy Pipeline (GitHub Actions / Render hook)"
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "🔧 SECTION 2: AGENT SERVICES RENDERED (Backend Record)"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  echo "Svc# | Date       | Category        | Status | Description"
  echo "─────┼────────────┼─────────────────┼────────┼──────────────────────────────────"
  echo "001  | 26-07-2026 | Architecture    | ✅ DONE | P0/P1 backlog finalized"
  echo "002  | 26-07-2026 | DevOps          | ✅ DONE | Replit+Render hosting setup"
  echo "003  | 27-07-2026 | Config          | ✅ DONE | saveproj.sh + 'sp' alias"
  echo "004  | 27-07-2026 | Config          | ✅ DONE | .env mapped to V6_Master_Pro_UI/.env"
  echo "005  | 28-07-2026 | Code Review     | ✅ DONE | main.py, logic.py, config.json reviewed"
  echo "006  | 28-07-2026 | Docs            | ✅ DONE | V6_Master_Pro_Backlog.md created"
  echo "007  | 29-07-2026 | DevOps          | ✅ DONE | v6-cmd.sh (11 commands)"
  echo "008  | 29-07-2026 | Security        | ✅ DONE | Admin portal + session + kill-switch"
  echo "009  | 29-07-2026 | Trading Engine  | ✅ DONE | Whale Copy Mode + ATR trailing stops"
  echo "010  | 29-07-2026 | Data Layer      | ✅ DONE | Binance 7-host failover + health monitor"
  echo "011  | 29-07-2026 | Data Layer      | ✅ DONE | Liquidation WebSocket (Binance Futures)"
  echo "012  | 29-07-2026 | UI/UX           | ✅ DONE | V6_Master_Pro_UI/ dashboard + charts"
  echo "013  | 29-07-2026 | Integrations    | ✅ DONE | Google Sheets (8 tabs) + Telegram bot"
  echo "014  | 29-07-2026 | Integrations    | ✅ DONE | Etherscan/BSCscan on-chain flows"
  echo "015  | 31-07-2026 | Documentation   | ✅ DONE | Agent Work Log system (this file)"
  echo ""
  echo "⏳ PENDING SERVICES:"
  echo "016  | --         | Trading Engine  | ⏳ PENDING | OCO Orders (P0)"
  echo "017  | --         | Database        | ⏳ PENDING | SQLite Migration (P0)"
  echo "018  | --         | Trading Engine  | ⏳ PENDING | WebSocket Price Feed (P1)"
  echo "019  | --         | Trading Engine  | ⏳ PENDING | Partial TP Auto-Scale (P1)"
  echo "020  | --         | Analysis        | ⏳ PENDING | Multi-Timeframe Confluence (P1)"
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "💰 SECTION 3: BILLABLE VS NON-BILLABLE BREAKDOWN"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  echo "BILLABLE (Agent Development Work):"
  echo "  ✓ SVC-001~015  → Architecture, code, scripts, integrations, docs"
  echo "  ✓ Custom Scripts → saveproj.sh, v6-cmd.sh, agent_log.sh"
  echo "  ✓ Security Spec  → API encryption plan, 2FA architecture"
  echo "  ✓ DB Design      → SQLite schema for trades/signals/clients"
  echo ""
  echo "NON-BILLABLE / USER-INFRA (You manage these):"
  echo "  ○ Replit free-tier hosting"
  echo "  ○ Render free-tier deployment"
  echo "  ○ Binance Public API (free, rate-limited)"
  echo "  ○ Google Sheets API (free tier, your credentials)"
  echo "  ○ Telegram Bot API (free)"
  echo "  ○ Etherscan/BSCscan API keys (free tier, your keys)"
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "💬 SECTION 4: CHAT INSTRUCTION HISTORY"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  echo "[2026-07-24] SESSION-001 | User: 'V6 Master Pro crypto bot banana hai Replit+Render pe.'"
  echo "             → Agent: P0/P1 backlog created. Project roadmap established."
  echo ""
  echo "[2026-07-27] SESSION-002 | User: 'saveproj.sh aur sp alias set karo.'"
  echo "             → Agent: Auto-export script ready. project.txt generates on demand."
  echo ""
  echo "[2026-07-28] SESSION-003 | User: 'Project files review karo aur backlog update karo.'"
  echo "             → Agent: Full code audit. V6_Master_Pro_Backlog.md persisted."
  echo ""
  echo "[2026-07-29] SESSION-004 | User: 'v6-cmd.sh banao jis mein deploy, push, status, save ho.'"
  echo "             → Agent: 11-command CLI toolkit created. ~/.bashrc workaround documented."
  echo ""
  echo "[2026-07-29] SESSION-005 | User: 'Agent ki instructions aur services track karne wali file banao.'"
  echo "             → Agent: agent_log.sh + agent_work_log.txt created. Audit trail live."
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "📝 SECTION 5: MANUAL UPDATE LOG (User / Agent Notes)"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  echo "Syntax: bash agent_log.sh note 'Your note here'"
  echo "Aliases: ag-note 'Your note'  |  ag-tail  |  ag-cat"
  echo ""
  echo "[INIT] $PKT_TIME | Log file initialized by agent."
} > "$OUTPUT"

LINE_COUNT=$(wc -l < "$OUTPUT")
echo -e "${GRN}✅ Agent Work Log generated: $OUTPUT ($LINE_COUNT lines)${NC}"
echo -e "${YLW}💡 Usage:${NC}"
echo -e "   ${BLU}bash agent_log.sh${NC}          → Regenerate full log"
echo -e "   ${BLU}bash agent_log.sh note '...'${NC} → Append manual note"
echo -e "   ${BLU}bash agent_log.sh tail 30${NC}    → View last 30 lines"
