import sys
from parts import *
OUT = sys.argv[1]
BG = hole_bg()

# ---------- 打球页四套 ----------
A = phone(route_svg() + toolbar_play() + dist_card() + '''
<div class="abs g d cap" style="left:12px;right:12px;bottom:28px;height:76px;justify-content:space-between;padding:0 8px 0 18px">
 <div style="text-align:center"><div style="font-size:20px">⚑</div><div class="t-cap" style="font-weight:600">记分</div></div>
 <div class="t-foot" style="font-weight:600"><span style="color:#f5c400">●</span> 球道沙坑 2/2 ‹ ›</div>
 <div class="gpg cap" style="height:60px;padding:0 20px;font-weight:700;font-size:17px">＋ 记一杆</div></div>''', dark=True, bg=BG, tag="A 底部玻璃条")
B = phone(route_svg() + toolbar_play() + '''
<div class="abs g d" style="left:0;right:0;bottom:0;height:252px;border-radius:34px 34px 0 0;padding:8px 20px">
 <div style="width:36px;height:5px;border-radius:3px;background:rgba(255,255,255,.45);margin:0 auto 10px"></div>
 <div style="display:flex;align-items:flex-end;gap:16px"><div class="num" style="font-size:56px;font-weight:800;line-height:1">364</div>
 <div class="t-foot" style="opacity:.8;padding-bottom:6px">到果岭中 · 码<br>前 373 · 后 355</div></div>
 <div class="t-sub" style="margin-top:8px">球童：一号木 230 → 八号铁 135 · 稳妥</div>
 <div class="t-foot" style="opacity:.7;margin-top:4px"><span style="color:#f5c400">●</span> 球道沙坑 到 220 · 过 248</div>
 <div style="display:flex;gap:12px;margin-top:14px"><div class="g d cap" style="flex:1;height:56px;font-weight:600">⚑ 记分</div>
 <div class="gpg cap" style="flex:1.4;height:56px;font-weight:700">＋ 记一杆</div></div></div>''', dark=True, bg=BG, tag="B 地图抽屉")
C = phone(route_svg() + toolbar_play() + dist_card() + side_rail() + hazard_pill() + score_btn() + record(), dark=True, bg=BG, tag="C 四角拇指（推荐）")
D = phone(route_svg() + '''
<div class="abs g d cap" style="left:16px;top:58px;height:44px;padding:0 16px;flex-direction:column;gap:0;align-items:flex-start">
 <div class="t-head">‹ 1 · Par 4 · 410</div><div class="t-cap" style="opacity:.75">第 1 杆 · T 台</div></div>''' + dist_card(58) + '''
<div class="abs g d" style="right:12px;bottom:28px;width:88px;height:400px;border-radius:44px;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;gap:14px;padding:14px 0 6px">
 <div class="circ" style="width:44px;height:44px;font-size:20px">⋯</div><div class="circ" style="width:44px;height:44px">◈</div>
 <div class="circ" style="width:44px;height:44px">⌖</div><div class="circ" style="width:56px;height:56px;font-size:20px">⚑<span class="t-cap">记分</span></div>
 <div class="gpg circ" style="width:76px;height:76px"><div style="font-size:28px;line-height:1">＋</div><div class="t-cap" style="font-weight:700">记一杆</div></div></div>''', dark=True, bg=BG, tag="D 右侧拇指轨")
for n, h in [("cand-play-A", A), ("cand-play-B", B), ("cand-play-C", C), ("cand-play-D", D)]:
    render(n, h, 390, 844, OUT)

# ---------- 首页导航三套 ----------
def hub_cards(top=150):
    return f'''<div class="abs" style="left:16px;right:16px;top:{top}px;display:flex;flex-direction:column;gap:12px">
 <div class="card"><div class="t-foot" style="color:#1f8a4c;font-weight:600">● 进行中</div><div style="display:flex;justify-content:space-between;align-items:flex-end">
  <div><div class="t-title">北京丽宫</div><div class="t-foot sec">已打 6 洞 · 第 7 洞</div></div><div class="num" style="font-size:34px;font-weight:800">+2</div></div></div>
 <div class="t-foot sec" style="margin:4px 4px -4px">快捷开局</div>
 <div style="display:flex;gap:8px"><div class="btnb" style="height:40px;padding:0 14px;font-size:15px">➤ 北京丽宫</div><div class="btnb" style="height:40px;padding:0 14px;font-size:15px">◷ Black Knight</div></div>
 <div class="card" style="display:flex;justify-content:space-between;align-items:center"><div><div class="t-foot sec">上一场</div><div class="t-head">Fixture Links</div><div class="t-cap sec">05-20 · 18 洞 · Par 72</div></div><div style="text-align:right"><div class="num" style="font-size:28px;font-weight:800">81</div><div class="t-foot" style="color:#d33">+9</div></div></div>
 <div class="card" style="display:flex;justify-content:space-between"><div><div class="t-head">成绩</div><div class="t-foot sec">差点 18.2 · 近 10 场均杆 88.4</div></div><span class="chev">›</span></div></div>'''
NA = phone('<div class="abs t-large" style="left:16px;top:96px">晚上好</div>' + hub_cards() + '''
<div class="abs g l cap" style="left:16px;bottom:26px;height:62px;width:250px;justify-content:space-around">
 <div style="text-align:center;color:#1f8a4c"><div style="font-size:20px">⛳</div><div class="t-cap" style="font-weight:600">打球</div></div>
 <div style="text-align:center"><div style="font-size:20px">▤</div><div class="t-cap">成绩</div></div></div>
<div class="abs g l circ" style="right:16px;bottom:26px;width:62px;height:62px;font-size:22px">⌕</div>''', tag="A 标签栏：打球/成绩+搜索")
NC = phone('<div class="abs t-large" style="left:16px;top:96px">晚上好</div><div class="abs g l circ" style="right:16px;top:58px;width:44px;height:44px;font-size:20px">⚙</div>' + hub_cards() + '''
<div class="abs g l cap" style="left:16px;bottom:26px;height:56px;width:150px;justify-content:flex-start;padding-left:16px;font-size:16px" ><span class="sec">⌕ 搜索球场</span></div>
<div class="abs gpg cap" style="right:16px;bottom:26px;height:56px;width:192px;font-weight:700;font-size:17px">▶ 继续 · 第 7 洞</div>''', tag="B/C 枢纽+底部工具栏（推荐）")
ND = phone('''<div class="abs" style="left:0;right:0;top:0;height:560px;''' + hole_bg(0.15, "center 30%") + '''"></div>
<div class="abs g d" style="left:16px;right:16px;top:330px;border-radius:30px;padding:16px 18px;color:#fff">
 <div class="t-foot" style="opacity:.8">➤ 你在 北京丽宫 · 0.3 公里</div><div class="t-title" style="margin-top:2px">B 场 · 蓝 T · 3393 码</div>
 <div class="gp cap" style="height:54px;margin-top:14px;font-weight:700;font-size:17px">开始第 1 洞</div>
 <div class="t-foot" style="opacity:.8;margin-top:10px;text-align:center">换球场 · 换发球台</div></div>
<div class="abs" style="left:16px;right:16px;top:600px;display:flex;gap:12px"><div class="card" style="flex:1"><div class="t-foot sec">上一场</div><div class="t-head">81 <span style="color:#d33">+9</span></div></div><div class="card" style="flex:1"><div class="t-foot sec">成绩</div><div class="t-head">差点 18.2</div></div></div>
<div class="abs g l circ" style="right:16px;top:58px;width:44px;height:44px;font-size:20px">⚙</div>''', tag="D 球场模式：到场直接开局")
for n, h in [("cand-nav-A", NA), ("cand-nav-C", NC), ("cand-nav-D", ND)]:
    render(n, h, 390, 844, OUT)

# ---------- 手表三套（46mm） ----------
def hero(top=48):
    return f'''<div class="abs" style="left:0;right:0;top:{top}px;text-align:center"><div class="num" style="font-size:58px;font-weight:800;line-height:1;color:#7ee08a">152</div>
<div style="font-size:13px;opacity:.8">码 · 到果岭中</div><div style="display:flex;justify-content:space-between;padding:4px 30px;font-size:14px" class="num"><span>前 140</span><span>后 161</span></div>
<div style="font-size:13px;color:#ffd45a">7 号铁 · 稳妥</div></div>'''
W1 = watch(w_title() + hero() + w_corners() + '<div class="abs" style="right:6px;top:96px;width:4px;height:30px;display:flex;flex-direction:column;gap:4px"><i style="height:8px;background:#fff;border-radius:2px"></i><i style="height:8px;background:#666;border-radius:2px"></i><i style="height:8px;background:#666;border-radius:2px"></i></div>', tag="A/C 竖翻页+系统角落钮")
W2 = watch('<div class="abs" style="right:0;top:0;width:118px;height:248px;' + hole_bg(0, "center 45%") + '"></div>' + w_title() + '''
<div class="abs num" style="left:16px;top:44px;font-size:22px;font-weight:700">161</div><div class="abs num" style="left:16px;top:70px;font-size:34px;font-weight:800;color:#7ee08a">152</div>
<div class="abs num" style="left:16px;top:110px;font-size:22px;font-weight:700">140</div><div class="abs" style="left:16px;top:142px;font-size:11px;opacity:.8">表冠缩放 ↕</div>''' + w_corners(), tag="B 单页仪表+表冠缩放")
W3 = watch(w_title() + hero(42) + '''<div class="abs gpg cap" style="left:12px;right:12px;bottom:10px;height:48px;font-size:17px;font-weight:700">＋ 记一杆</div>
<div class="abs g d circ" style="right:14px;top:8px;width:34px;height:34px;font-size:14px">☰</div>''', tag="D 底部整条记一杆")
for n, h in [("cand-watch-A", W1), ("cand-watch-B", W2), ("cand-watch-D", W3)]:
    render(n, h, 208, 248, OUT)
