with open("v6_database.py", "r") as f:
    lines = f.readlines()

# Migration block (4-space indented to match init_db body)
migration = [
    "\n",
    "    # ── Auto-migrate: add missing columns silently ──\n",
    "    c.execute(\"PRAGMA table_info(backtest_signals)\")\n",
    "    existing_cols = {row[1] for row in c.fetchall()}\n",
    "    \n",
    "    if \"score_breakdown\" not in existing_cols:\n",
    "        try:\n",
    "            c.execute(\"ALTER TABLE backtest_signals ADD COLUMN score_breakdown TEXT\")\n",
    "            print(\"[V6 DB] Auto-migrated: added column 'score_breakdown'\")\n",
    "        except Exception as e:\n",
    "            print(f\"[V6 DB] Migration warning: {e}\")\n",
    "    \n",
    "    if \"price_source\" not in existing_cols:\n",
    "        try:\n",
    "            c.execute(\"ALTER TABLE backtest_signals ADD COLUMN price_source TEXT DEFAULT 'rest_scan'\")\n",
    "            print(\"[V6 DB] Auto-migrated: added column 'price_source'\")\n",
    "        except Exception as e:\n",
    "            print(f\"[V6 DB] Migration warning: {e}\")\n",
    "\n",
]

in_init_db = False
insert_idx = -1
base_indent = None

for i, line in enumerate(lines):
    if line.strip().startswith("def init_db"):
        in_init_db = True
        continue
    if in_init_db:
        if line.strip() and base_indent is None:
            base_indent = len(line) - len(line.lstrip())
        if "conn.commit()" in line or "conn.close()" in line:
            insert_idx = i
            break
        if line.strip().startswith("def "):
            curr_indent = len(line) - len(line.lstrip())
            if base_indent is not None and curr_indent <= base_indent:
                in_init_db = False

if insert_idx != -1:
    lines[insert_idx:insert_idx] = migration
    with open("v6_database.py", "w") as f:
        f.writelines(lines)
    print("✅ v6_database.py patched successfully!")
    print("   Auto-migration logic added inside init_db().")
else:
    print("❌ Could not find insertion point (conn.commit/conn.close).")
    print("   Please share v6_database.py content for manual fix.")
