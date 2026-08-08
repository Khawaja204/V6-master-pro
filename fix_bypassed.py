#!/usr/bin/env python3
with open("main.py","r") as f: lines=f.readlines()
fixed=[]; i=0
while i<len(lines):
    line=lines[i]
    if "# Bypassed:" in line and "send_telegram" in line:
        parts=line.split("# Bypassed:",1)
        if len(parts)==2:
            after=parts[1]
            orig=len(after)-len(after.lstrip())
            if orig>0: orig-=1
            code=after.strip()
            if code.count("(") > code.count(")"):
                fixed.append(line); i+=1
                while i<len(lines):
                    nl=lines[i]; ns=nl.strip(); ni=len(nl)-len(nl.lstrip())
                    if ni>orig or (ni==orig and ns.startswith(")")):
                        fixed.append("# "+nl); i+=1
                        if ns.startswith(")"): break
                    else: break
                continue
    fixed.append(line); i+=1
with open("main.py","w") as f: f.writelines(fixed)
import ast, subprocess, sys
try:
    ast.parse("".join(fixed))
    print("✅ main.py syntax check PASSED — all Bypassed blocks fixed.")
    sys.exit(0)
except SyntaxError as e:
    print(f"❌ Line {e.lineno}: {e.msg}"); sys.exit(1)
