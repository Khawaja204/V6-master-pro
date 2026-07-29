import re

# Fix main.py
with open('main.py','r') as f: lines=f.readlines()
out=[]
for line in lines:
    if '5 * 3600' in line:
        out.append(line); continue
    line=re.sub(r'time\.strftime\("([^"]+)", time\.gmtime\(\)\)', r'time.strftime("\1", time.gmtime(time.time() + 5 * 3600))', line)
    line=re.sub(r'time\.strftime\("([^"]+)"\)(?!\s*,)', r'time.strftime("\1", time.gmtime(time.time() + 5 * 3600))', line)
    out.append(line)
with open('main.py','w') as f: f.writelines(out)
print("✅ main.py")

# Fix logic.py
with open('logic.py','r') as f: lines=f.readlines()
out=[]
for line in lines:
    if '5 * 3600' in line:
        out.append(line); continue
    line=re.sub(r'time\.strftime\("([^"]+)", time\.gmtime\(([^)]+)\)\)', r'time.strftime("\1", time.gmtime(\2 + 5 * 3600))', line)
    line=re.sub(r'time\.strftime\("([^"]+)"\)(?!\s*,)', r'time.strftime("\1", time.gmtime(time.time() + 5 * 3600))', line)
    out.append(line)
with open('logic.py','w') as f: f.writelines(out)
print("✅ logic.py")

# Fix frontend
for fn in ['V6_Master_Pro_UI/index.html','V6_Master_Pro_UI/script.js','index.html','focus.html']:
    try:
        with open(fn,'r') as f: c=f.read()
        c=c.replace('new Date().toLocaleTimeString()','new Date(Date.now()+5*3600*1000).toISOString().slice(11,19)')
        c=c.replace('new Date().toTimeString().slice(0,8)','new Date(Date.now()+5*3600*1000).toISOString().slice(11,19)')
        with open(fn,'w') as f: f.write(c)
        print("✅",fn)
    except: pass

print("\n🎉 PKT patch done. Restart bot now.")
