import re

with open("main.py", "r") as f:
    content = f.read()

# Fix broken commented lines that caused indentation errors
content = content.replace("# Bypassed direct call:", "# Bypassed:")

with open("main.py", "w") as f:
    f.write(content)

# Run a syntax check to ensure zero indentation/syntax errors
import subprocess
result = subprocess.run(["python3", "-m", "py_compile", "main.py"], capture_output=True, text=True)

if result.returncode == 0:
    print("✅ Main.py Syntax Check Passed! Indentation error fixed perfectly.")
else:
    print("⚠️ Syntax Error details:")
    print(result.stderr)
