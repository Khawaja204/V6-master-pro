import sys, ast

PATH = 'main.py'
with open(PATH, 'r', encoding='utf-8') as f:
    content = f.read()

OLD = "    fetch_strategy_indicators, pick_best_strategy,\n)"
NEW = "    fetch_strategy_indicators, pick_best_strategy,\n    fetch_candlestick_pattern,\n)"

if 'fetch_candlestick_pattern,\n)' in content or content.count('fetch_candlestick_pattern') and 'from logic import' in content and content.split('from logic import')[1].split(')')[0].find('fetch_candlestick_pattern') != -1:
    print("main.py: fetch_candlestick_pattern already imported — skipping")
else:
    cnt = content.count(OLD)
    if cnt != 1:
        print(f"FAILED - expected 1 anchor match, found {cnt}. Aborting, no changes written.")
        sys.exit(1)
    content = content.replace(OLD, NEW, 1)
    ast.parse(content)
    with open(PATH, 'w', encoding='utf-8') as f:
        f.write(content)
    print("main.py: fetch_candlestick_pattern import added OK, syntax-checked OK")

print("Done — critical scan-loop crash fix applied.")
