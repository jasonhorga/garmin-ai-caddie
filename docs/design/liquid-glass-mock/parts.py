from kit import *

def route_svg():
    # caddie route overlay (content layer, not chrome): tee -> landing -> green
    return '''<svg class="abs" style="left:0;top:0" width="390" height="844">
<polyline points="205,770 172,470 196,196" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" opacity=".95"/>
<path d="M110 520 Q190 440 300 470" fill="none" stroke="#f5c400" stroke-width="2.5" stroke-dasharray="7 6"/>
<circle cx="205" cy="770" r="9" fill="#fff"/><circle cx="205" cy="770" r="5.5" fill="#1a73e8"/>
<circle cx="172" cy="470" r="6" fill="#fff" stroke="#1f8a4c" stroke-width="3"/>
<line x1="196" y1="196" x2="196" y2="168" stroke="#fff" stroke-width="2"/><path d="M196 168 L214 174 L196 180Z" fill="#e53935"/>
</svg>
<div class="abs g d cap t-foot" style="left:186px;top:452px;height:26px;padding:0 10px;font-weight:600">一号木 230</div>
<div class="abs g d cap t-foot" style="left:206px;top:200px;height:26px;padding:0 10px;font-weight:600">八号铁 135</div>
<div class="abs t-cap" style="left:70px;top:512px;color:#fff;font-weight:700;text-shadow:0 1px 3px #000">220 码</div>'''

def toolbar_play(prep=False):
    sub = "开局前预览 · T 台 ⌄" if prep else "第 1 杆 · T 台 ⌄"
    return f'''<div class="abs g d circ" style="left:16px;top:58px;width:44px;height:44px;font-size:22px">‹</div>
<div class="abs g d cap" style="left:72px;top:58px;height:44px;padding:0 16px;flex-direction:column;gap:0;align-items:flex-start">
 <div class="t-head">1 · Par 4 · 410 码</div><div class="t-cap" style="opacity:.75">{sub}</div></div>
<div class="abs g d circ" style="right:16px;top:58px;width:44px;height:44px;font-size:20px">⋯</div>'''

def dist_card(top=112):
    return f'''<div class="abs g d" style="right:16px;top:{top}px;width:112px;border-radius:24px;padding:10px 12px;text-align:center">
 <div class="t-cap" style="opacity:.75">前 373</div><div class="num" style="font-size:52px;font-weight:800;line-height:1.05">364</div>
 <div class="t-cap" style="opacity:.75">后 355 · 码</div></div>'''

def record(right=20, bottom=34, label="记一杆"):
    return f'''<div class="abs gpg circ" style="right:{right}px;bottom:{bottom}px;width:76px;height:76px">
 <div style="font-size:28px;line-height:1;font-weight:300">＋</div><div class="t-cap" style="font-weight:700">{label}</div></div>'''

def score_btn(left=20, bottom=42):
    return f'''<div class="abs g d circ" style="left:{left}px;bottom:{bottom}px;width:60px;height:60px">
 <div style="font-size:20px">⚑</div><div class="t-cap" style="font-weight:600">记分</div></div>'''

def side_rail(top=300, left=16):
    return f'''<div class="abs g d circ" style="left:{left}px;top:{top}px;width:44px;height:44px;font-size:18px">◈</div>
<div class="abs g d circ" style="left:{left}px;top:{top+56}px;width:44px;height:44px;font-size:16px">⌖</div>'''

def hazard_pill(left=16, bottom=118):
    return f'''<div class="abs g d cap" style="left:{left}px;bottom:{bottom}px;height:40px;padding:0 6px 0 14px;font-size:14px;font-weight:600">
 <span style="color:#f5c400">●</span> 球道沙坑 2/2 <span class="circ" style="width:32px;height:32px">‹</span><span class="circ" style="width:32px;height:32px">›</span></div>'''

def w_corners(menu_left=14, bottom=12):
    return f'''<div class="abs g d circ" style="left:{menu_left}px;bottom:{bottom}px;width:44px;height:44px;font-size:18px">☰</div>
<div class="abs gpg circ" style="right:{menu_left}px;bottom:{bottom}px;width:44px;height:44px;font-size:24px">＋</div>'''

def w_title(t="H7 · P4", s="+3"):
    return f'<div class="abs" style="left:22px;top:12px;font-size:15px;font-weight:700">{t} <span style="color:#ff6b5a">{s}</span></div>'
