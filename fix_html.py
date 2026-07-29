with open('V6_Master_Pro_UI/index.html', 'r') as f:
    content = f.read()

# 1. Header columns fix
old_head = '''    <thead>
      <tr><th>Coin</th><th>Dir</th><th>Wall Price</th><th>SL</th><th>Target</th><th>Size(USDT)</th><th>OBI</th><th>Rate</th><th>Conf%</th><th>News</th></tr>
    </thead>'''

new_head = '''    <thead>
      <tr><th>Coin</th><th>Dir</th><th>Wall Price</th><th>SL</th><th>Target</th><th>ETA</th><th>Size(USDT)</th><th>OBI</th><th>Rate</th><th>Conf%</th><th>Time</th><th>News</th></tr>
    </thead>'''

if old_head in content:
    content = content.replace(old_head, new_head)
    print("✅ Table header updated (ETA + Time columns added)")
else:
    print("❌ Header not found")

# 2. Render block fix
old_render = '''        return `<tr>
          <td style="cursor:pointer" onclick="loadCoin('${s.symbol}')"><span class="cc" style="background:${coinClr(sym)}"></span><b>${sym}</b></td>
          <td><span class="at ${dirCls}">${dirLbl}</span><br>${confBadge}</td>
          <td>${fmt6(s.wall_price||0)}</td>
          <td style="color:var(--red)">${fmt6(s.stop_loss||0)}</td>
          <td style="color:var(--green)">${fmt6(s.target||0)}</td>
          <td>${s.eta||'—'}</td>
          <td>${fmtNum(s.wall_size_usdt||0)}</td>
          <td style="color:${(s.obi||0)>0?'var(--green)':'var(--red)'}">${(s.obi||0).toFixed(3)}</td>
          <td>${(s.obi_velocity||0).toFixed(2)}</td>
          <td>${s.confidence||0}%</td>
          <td><a href="${newsUrl}" target="_blank" style="color:var(--blue);font-size:9px">📰 News</a></td>
        </tr>`;'''

new_render = '''        const targetColor = s.direction==='COPY_BUY' ? 'var(--green)' : 'var(--red)';
        return `<tr>
          <td style="cursor:pointer" onclick="loadCoin('${s.symbol}')"><span class="cc" style="background:${coinClr(sym)}"></span><b>${sym}</b></td>
          <td><span class="at ${dirCls}">${dirLbl}</span><br>${confBadge}</td>
          <td>${fmt6(s.wall_price||0)}</td>
          <td style="color:var(--red)">${fmt6(s.stop_loss||0)}</td>
          <td style="color:${targetColor}">${fmt6(s.target||0)}</td>
          <td>${s.eta||'—'}</td>
          <td>${fmtNum(s.wall_size_usdt||0)}</td>
          <td style="color:${(s.obi||0)>0?'var(--green)':'var(--red)'}">${(s.obi||0).toFixed(3)}</td>
          <td>${(s.obi_velocity||0).toFixed(2)}</td>
          <td>${s.confidence||0}%</td>
          <td style="color:var(--grey);font-size:9px">${s.detected_at||'—'}</td>
          <td><a href="${newsUrl}" target="_blank" style="color:var(--blue);font-size:9px">📰 News</a></td>
        </tr>`;'''

if old_render in content:
    content = content.replace(old_render, new_render)
    print("✅ Table render block updated (target color + Time column)")
else:
    print("❌ Render block not found")

with open('V6_Master_Pro_UI/index.html', 'w') as f:
    f.write(content)
print("✅ V6_Master_Pro_UI/index.html saved")
