import sys
from parts import *
OUT = sys.argv[1]
BG = hole_bg()
TOOLB = lambda title, trail="", lead="‹": (f'<div class="abs g l circ" style="left:16px;top:58px;width:44px;height:44px;font-size:22px">{lead}</div>' if lead else "") + \
    f'<div class="abs t-head" style="left:0;right:0;top:70px;text-align:center">{title}</div>' + \
    (f'<div class="abs g l cap" style="right:16px;top:58px;height:44px;min-width:44px;padding:0 14px;font-size:16px;font-weight:600">{trail}</div>' if trail else "")
SHEET = lambda h, inner, dark=True: f'<div class="abs" style="left:0;right:0;top:0;bottom:0;background:rgba(0,0,0,.35)"></div><div class="abs g {"d" if dark else "l"}" style="left:6px;right:6px;bottom:6px;height:{h}px;border-radius:40px;padding:10px 18px;background:rgba(28,30,28,.88)">{inner}</div>'
def rows(items): return '<div class="list">' + "".join(f'<div class="row"><span>{a}</span><span class="sec t-sub">{b}</span></div>' for a, b in items) + '</div>'
P = {}

# 1 登录
P["rec-ip-signin"] = phone('''<div class="abs" style="left:0;right:0;top:250px;text-align:center"><div style="font-size:56px">⛳</div>
<div class="t-large" style="margin-top:10px">AI 高尔夫球童</div><div class="t-body sec" style="margin:10px 40px">用 Apple 登录，开始你的球场备战、记分与球童建议。</div></div>
<div class="abs cap" style="left:24px;right:24px;bottom:60px;height:54px;background:#000;color:#fff;font-weight:600;font-size:18px"> 通过 Apple 登录</div>''')
# 2 首页（无进行中）
cards = '''<div class="abs" style="left:16px;right:16px;top:150px;display:flex;flex-direction:column;gap:12px">
 <div class="t-foot sec" style="margin:0 4px -4px">快捷开局</div>
 <div style="display:flex;gap:8px"><div class="btnb" style="height:44px;padding:0 14px;font-size:15px">➤ 北京丽宫 0.3 公里</div><div class="btnb" style="height:44px;padding:0 14px;font-size:15px">◷ Black Knight</div></div>
 <div class="card" style="display:flex;justify-content:space-between;align-items:center"><div><div class="t-foot sec">上一场</div><div class="t-head">Fixture Links</div><div class="t-cap sec">05-20 · 18 洞 · Par 72</div></div><div style="text-align:right"><div class="num" style="font-size:28px;font-weight:800">81</div><div class="t-foot" style="color:#d33">+9</div></div></div>
 <div class="card"><div style="display:flex;justify-content:space-between"><div class="t-head">成绩</div><span class="chev">›</span></div>
  <div style="display:flex;gap:22px;margin-top:6px"><div><div class="num t-title">18.2</div><div class="t-cap sec">差点估算</div></div><div><div class="num t-title">88.4</div><div class="t-cap sec">近 10 场均杆</div></div><div><div class="num t-title">78</div><div class="t-cap sec">最佳</div></div></div>
  <svg width="320" height="40" style="margin-top:8px"><polyline points="0,30 40,22 80,26 120,18 160,20 200,12 240,16 280,8 320,10" fill="none" stroke="#1f8a4c" stroke-width="2.5"/></svg></div></div>'''
P["rec-ip-home"] = phone('<div class="abs t-large" style="left:16px;top:96px">晚上好</div><div class="abs g l circ" style="right:16px;top:58px;width:44px;height:44px;font-size:20px">⚙</div>' + cards +
 '<div class="abs g l cap" style="left:16px;bottom:26px;height:56px;width:150px;justify-content:flex-start;padding-left:16px;font-size:16px"><span class="sec">⌕ 搜索球场</span></div><div class="abs gpg cap" style="right:16px;bottom:26px;height:56px;width:192px;font-weight:700;font-size:17px">⛳ 打一场球</div>')
# 3 开局·选球场（搜索在底部）
P["rec-ip-start"] = phone(TOOLB("开始一场") + '''<div class="abs" style="left:16px;right:16px;top:118px">
<div class="t-foot sec" style="margin:0 16px 6px">附近</div><div class="list"><div class="row" style="min-height:62px"><div><div class="t-head">北京丽宫体育公园高尔夫俱乐部</div><div class="t-foot sec">0.3 公里 · 27 洞 · 已下载</div></div><span style="color:#1f8a4c">✓</span></div>
<div class="row" style="min-height:62px"><div><div class="t-head">北京高尔夫俱乐部</div><div class="t-foot sec">4.1 公里 · 18 洞</div></div><span class="chev">›</span></div></div>
<div class="t-foot sec" style="margin:18px 16px 6px">最近打过</div><div class="list"><div class="row" style="min-height:62px"><div><div class="t-head">Black Knight</div><div class="t-foot sec">05-18 · 78 杆</div></div><span class="chev">›</span></div>
<div class="row" style="min-height:62px"><div><div class="t-head">Fixture Links</div><div class="t-foot sec">05-20 · 81 杆</div></div><span class="chev">›</span></div></div></div>
<div class="abs g l cap" style="left:16px;right:16px;bottom:26px;height:52px;justify-content:flex-start;padding-left:18px;font-size:17px"><span class="sec">⌕ 球场或城市</span></div>''')
# 4 开局·设置
P["rec-ip-setup"] = phone(TOOLB("北京丽宫") + '''<div class="abs" style="left:16px;right:16px;top:120px">
<div class="t-foot sec" style="margin:0 16px 8px">从哪个 9 洞开始</div><div class="seg"><div>A 场</div><div class="on">B 场</div><div>C 场</div></div>
<div class="t-foot sec" style="margin:6px 16px 18px">B 场 · 9 洞 · 3393 码 · 上次搭配 C 场</div>
<div class="t-foot sec" style="margin:0 16px 8px">发球台</div><div class="list">
<div class="row"><span><span style="color:#d4a017">●</span> 金 T</span><span class="sec t-sub">3585 码</span></div>
<div class="row"><span><span style="color:#1a73e8">●</span> 蓝 T</span><span style="color:#1f8a4c;font-weight:600">3393 码 ✓</span></div>
<div class="row"><span><span style="color:#bbb">●</span> 白 T</span><span class="sec t-sub">3019 码</span></div>
<div class="row"><span><span style="color:#d33">●</span> 红 T</span><span class="sec t-sub">2533 码</span></div></div></div>
<div class="abs gpg cap" style="left:16px;right:16px;bottom:26px;height:58px;font-weight:700;font-size:18px">开始 · B 场第 1 洞</div>''')
# 5 打球页（推荐 C）+ 开局前预览
P["rec-ip-play"] = phone(route_svg() + toolbar_play() + dist_card() + side_rail() + hazard_pill() + score_btn() + record(), dark=True, bg=BG)
P["rec-ip-prep"] = phone(route_svg() + toolbar_play(prep=True) + dist_card() + side_rail() + record(label="开始") , dark=True, bg=BG)
P["rec-ip-play-menu"] = phone(route_svg() + toolbar_play() + dist_card() + side_rail() + score_btn() + record() + '''
<div class="abs g d" style="right:16px;top:108px;width:220px;border-radius:26px;padding:6px 0;z-index:5">
''' + "".join(f'<div style="height:46px;display:flex;align-items:center;justify-content:space-between;padding:0 18px;font-size:17px;{c}">{a}<span>{b}</span></div>' for a, b, c in
 [("计分卡", "▦", ""), ("洞位图", "⌖", ""), ("换发球台", "T", ""), ("球洞调整", "±", ""), ("结束本场", "⏻", "color:#ff6b5a")]) + '</div>', dark=True, bg=BG)
# 6 记分弹层
cell = lambda n, l, on=False: f'<div class="{"gp" if on else "g d"} circ" style="width:52px;height:52px"><div class="num" style="font-size:20px;font-weight:700">{n}</div></div><div class="t-cap" style="text-align:center;opacity:.75;margin-top:4px">{l}</div>'
strip = '<div style="display:flex;justify-content:space-between">' + "".join(f'<div>{cell(n, l, n == 5)}</div>' for n, l in [(2, "老鹰"), (3, "小鸟"), (4, "标准"), (5, "+1"), (6, "+2"), (7, "+3")]) + '</div>'
P["rec-ip-score"] = phone(route_svg() + toolbar_play() + SHEET(520, f'''<div style="display:flex;justify-content:space-between;align-items:center;height:44px"><div class="g d circ" style="width:44px;height:44px">✕</div><div class="t-head">第 1 洞 · Par 4</div><div style="width:44px"></div></div>
<div class="t-foot" style="opacity:.75;margin:12px 0 8px">杆数</div>{strip}
<div class="t-foot" style="opacity:.75;margin:16px 0 8px">推杆</div><div class="seg"><div>0</div><div>1</div><div class="on">2</div><div>3</div><div>4+</div></div>
<div class="t-foot" style="opacity:.75;margin:16px 0 8px">开球</div><div class="seg"><div>← 偏左</div><div class="on">球道</div><div>偏右 →</div></div>
<div style="display:flex;justify-content:space-between;align-items:center;margin-top:16px"><span class="t-body">罚杆</span><div class="seg" style="width:120px"><div>−</div><div class="on num">0</div><div>＋</div></div></div>
<div class="gp cap" style="height:58px;margin-top:20px;font-weight:700;font-size:17px">保存 5 杆 · 去第 2 洞</div>'''), dark=True, bg=BG)
# 7 选杆提示
P["rec-ip-club"] = phone(route_svg() + toolbar_play() + SHEET(430, '''<div style="display:flex;justify-content:space-between;align-items:center;height:44px"><div style="width:60px"></div><div class="t-head">这一杆用了什么球杆？</div><div class="g d cap" style="height:36px;padding:0 12px;font-size:14px">跳过</div></div>
<div class="t-foot" style="opacity:.7;text-align:center;margin:2px 0 12px">第 1 杆的位置已保存</div>''' + "".join(
 f'<div class="g d" style="height:52px;border-radius:18px;margin-bottom:8px;display:flex;align-items:center;justify-content:space-between;padding:0 16px"><span class="t-body">{a} <span class="t-foot" style="opacity:.7">{b} 码</span></span><span class="t-foot" style="color:#7ee08a">{c}</span></div>'
 for a, b, c in [("一号木", 230, "球童建议"), ("三号木", 212, ""), ("七号铁", 171, ""), ("八号铁", 157, ""), ("九号铁", 144, "")])), dark=True, bg=BG)
# 8 计分卡
def grid(start):
    h = "".join(f'<td>{i}</td>' for i in range(start, start + 9)); par = "".join(f'<td class="sec">{p}</td>' for p in [4, 4, 3, 5, 4, 4, 3, 5, 4])
    sc = "".join(f'<td>{s}</td>' for s in (["<b style=\'border:2px solid #7ee08a;border-radius:50%;padding:1px 6px\'>3</b>", "5"] + ["–"] * 7 if start == 1 else ["–"] * 9))
    return f'<table style="width:100%;font-size:14px;text-align:center;border-spacing:0 6px" class="num"><tr class="sec"><td style="text-align:left">洞</td>{h}</tr><tr><td style="text-align:left" class="sec">Par</td>{par}</tr><tr><td style="text-align:left">成绩</td>{sc}</tr></table>'
P["rec-ip-scorecard"] = phone(route_svg() + SHEET(780, f'''<div style="display:flex;justify-content:space-between;align-items:center;height:44px"><div class="g d circ" style="width:44px;height:44px">✕</div><div class="t-head">计分卡</div><div style="width:44px"></div></div>
<div style="display:flex;align-items:flex-end;gap:12px;margin:14px 4px"><div class="num" style="font-size:52px;font-weight:800;line-height:1">+1</div><div class="t-foot" style="opacity:.75;padding-bottom:6px">8 杆 · 已打 2/18 洞<br>北京丽宫 · B→C</div></div>
<div class="t-foot" style="opacity:.75;margin:10px 4px 0">B 场</div><div class="card" style="background:rgba(255,255,255,.08)">{grid(1)}</div>
<div class="t-foot" style="opacity:.75;margin:12px 4px 0">C 场</div><div class="card" style="background:rgba(255,255,255,.08)">{grid(10)}</div>
<div style="display:flex;gap:10px;margin-top:16px"><div class="btnb" style="flex:1">改成绩</div><div class="btnb" style="flex:1">球洞调整</div></div>'''), dark=True, bg=BG)
# 9 转场
P["rec-ip-turn"] = phone(route_svg() + SHEET(380, '''<div style="display:flex;justify-content:space-between;align-items:center;height:44px"><div style="width:52px"></div><div class="t-head">B 场打完了</div><div class="g d cap" style="height:36px;padding:0 12px;font-size:14px">稍后</div></div>
<div class="t-foot" style="opacity:.75;margin:12px 4px 8px">接着打哪个 9 洞</div><div class="seg"><div>A 场</div><div>B 场</div><div class="on">C 场 · 上次</div></div>
<div class="gp cap" style="height:58px;margin-top:22px;font-weight:700;font-size:17px">接着打 C 场</div><div class="btnb" style="margin-top:12px">不打了 · 只打 9 洞</div>'''), dark=True, bg=BG)
# 10 结束本场
P["rec-ip-summary"] = phone(route_svg() + SHEET(700, f'''<div style="display:flex;justify-content:space-between;align-items:center;height:44px"><div style="width:44px"></div><div class="t-head">北京丽宫 · 本场</div><div style="width:44px"></div></div>
<div style="display:flex;align-items:flex-end;gap:14px;margin:18px 4px"><div class="num" style="font-size:64px;font-weight:800;line-height:1">−1</div><div class="t-sub" style="padding-bottom:8px">3 杆 · 1/18 洞</div></div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">''' + "".join(f'<div class="card" style="background:rgba(255,255,255,.08)"><div class="t-cap" style="opacity:.75">{a}</div><div class="num t-title">{b}</div></div>' for a, b in [("球道命中", "100%"), ("GIR", "100%"), ("推杆", "2"), ("罚杆", "0")]) +
'''</div><div class="gp cap" style="height:58px;margin-top:22px;font-weight:700;font-size:17px">保存并结束</div><div class="btnb" style="margin-top:10px">继续打球</div><div class="btnb" style="margin-top:10px;color:#ff6b5a">放弃本场…</div>'''), dark=True, bg=BG)
# 11 果岭详情
P["rec-ip-green"] = phone('<div class="abs" style="left:0;right:0;top:0;height:600px;' + hole_bg(0, "62% 12%") + 'background-size:260%"></div>' +
 '<div class="abs g d circ" style="left:16px;top:58px;width:44px;height:44px">✕</div><div class="abs g d cap t-head" style="left:72px;top:58px;height:44px;padding:0 16px">第 7 洞 · 果岭</div>' +
 '''<div class="abs card" style="left:12px;right:12px;bottom:30px;padding:18px"><div style="display:flex;align-items:flex-end;gap:10px"><span class="t-foot sec">发球台到旗</span><span class="num" style="font-size:46px;font-weight:800;line-height:1">315</span><span class="t-foot sec">码</span></div>
<div style="display:grid;grid-template-columns:repeat(4,1fr);text-align:center;margin-top:14px" class="num">''' + "".join(f'<div><div class="t-cap sec">{a}</div><div class="t-title">{b}</div></div>' for a, b in [("前沿", 29), ("后沿", 14), ("左边", 33), ("右边", 16)]) + '</div><div class="t-foot sec" style="margin-top:10px">旗在果岭中心后 8 码、偏右 9 码</div></div>', dark=True)
# 12 复盘 + 落点图
P["rec-ip-review"] = phone(TOOLB("单场复盘", "⇪").replace("g l", "g d") + '''<div class="abs" style="left:16px;right:16px;top:118px"><div class="t-title">Black Knight</div><div class="t-foot sec">2026-05-18 · Par 72</div>
<div style="display:flex;align-items:flex-end;gap:14px;margin:16px 0"><div style="font-size:64px;font-weight:800;line-height:1">E</div><div class="t-title">78 杆</div></div>
<div class="card">''' + grid(1).replace("border:2px solid #7ee08a;", "") + '''</div><div class="card" style="margin-top:12px">''' + grid(10) + '''</div>
<div class="t-foot sec" style="margin:14px 4px">点成绩看落点 ›</div></div>''', dark=True)
P["rec-ip-shotmap"] = phone(route_svg().split("<div")[0] + '<div class="abs g d circ" style="left:16px;top:58px;width:44px;height:44px">✕</div><div class="abs g d cap" style="left:72px;top:58px;height:44px;padding:0 16px;flex-direction:column;gap:0;align-items:flex-start"><div class="t-head">第 1 洞 · Par 4</div><div class="t-cap" style="opacity:.75">4 杆 · 标准杆</div></div><div class="abs g d cap t-head" style="right:16px;top:58px;height:44px;padding:0 16px">编辑</div>' +
 '<div class="abs g d cap" style="left:12px;right:12px;bottom:28px;height:60px;justify-content:space-around;padding:0 6px">' + "".join(f'<div class="{"gp" if i == 1 else ""} circ num" style="width:40px;height:44px;border-radius:14px;font-size:13px;line-height:1.1"><b>{i}</b><span class="t-cap">4</span></div>' for i in range(1, 9)) + '</div>', dark=True, bg=BG)
# 13 成绩
P["rec-ip-results"] = phone(TOOLB("", "", "‹") + '''<div class="abs t-large" style="left:16px;top:108px">成绩</div><div class="abs" style="left:16px;right:16px;top:160px">
<div class="seg"><div>近 10 场</div><div class="on">近 20 场</div><div>近一年</div><div>全部</div></div>
<div class="card" style="margin-top:14px"><div class="t-foot sec">差点估算</div><div style="display:flex;align-items:flex-end;gap:10px"><span class="num" style="font-size:52px;font-weight:800;line-height:1">18.2</span><span class="t-foot" style="color:#1f8a4c">↓ 1.4 近 20 场</span></div>
<svg width="320" height="80" style="margin-top:8px"><polyline points="0,20 40,32 80,28 120,44 160,38 200,52 240,48 280,60 320,62" fill="none" stroke="#1f8a4c" stroke-width="2.5"/></svg>
<div style="display:flex;gap:28px" class="num"><div><div class="t-title">88.4</div><div class="t-cap sec">近 10 场均杆</div></div><div><div class="t-title">82</div><div class="t-cap sec">最佳</div></div><div><div class="t-title">423</div><div class="t-cap sec">场</div></div></div></div>
<div class="list" style="margin-top:14px">''' + "".join(f'<div class="row"><span>{a}</span><span class="chev">›</span></div>' for a in ["表现分析", "时间与频率", "成绩分布", "球场", "全部球局"]) + '</div></div>')
# 14 设置（球包在设置里，不单独成页）
P["rec-ip-settings"] = phone('''<div class="abs" style="left:0;right:0;top:0;bottom:0;background:rgba(0,0,0,.25)"></div><div class="abs" style="left:0;right:0;top:44px;bottom:0;background:#f2f2f7;border-radius:38px 38px 0 0">
<div class="abs g l circ" style="left:16px;top:14px;width:44px;height:44px">✕</div><div class="abs t-head" style="left:0;right:0;top:26px;text-align:center">设置</div>
<div class="abs" style="left:16px;right:16px;top:80px"><div class="t-foot sec" style="margin:0 16px 6px">球包（13 支 · 已同步）</div><div class="list">''' + "".join(
 f'<div class="row"><span>{a}</span><span style="display:flex;align-items:center;gap:10px"><svg width="110" height="10"><rect x="0" y="3" width="110" height="4" rx="2" fill="#e5e5ea"/><rect x="{x}" y="1" width="34" height="8" rx="4" fill="#9fd8b0"/></svg><span class="num t-sub">{b}</span></span></div>'
 for a, b, x in [("一号木", 231, 70), ("三号木", 210, 58), ("七号铁", 152, 30), ("P 杆", 115, 12)]) + '''<div class="row" style="color:#1f8a4c">全部 13 支 · 编辑 ›</div></div>
<div class="t-foot sec" style="margin:18px 16px 6px">离线球场</div><div class="list"><div class="row" style="min-height:58px"><div style="flex:1"><div>北京丽宫</div><div style="height:4px;background:#e5e5ea;border-radius:2px;margin-top:6px"><div style="width:38%;height:4px;background:#1f8a4c;border-radius:2px"></div></div></div><span class="t-foot sec" style="margin-left:12px">7/18</span></div><div class="row"><span>用蜂窝数据预下载</span><span style="width:51px;height:31px;border-radius:16px;background:#34c759;position:relative"><i style="position:absolute;right:2px;top:2px;width:27px;height:27px;border-radius:50%;background:#fff"></i></span></div></div>
<div class="t-foot sec" style="margin:18px 16px 6px">账号</div><div class="list"><div class="row">Garmin 会话<span class="chev">›</span></div><div class="row" style="color:#d33">退出登录</div></div></div></div>''')

for n, h in P.items():
    render(n, h, 390, 844, OUT)

# ---------- 手表 ----------
from candidates_watch import W
for n, (h, size) in W.items():
    wpx = {"w46": (208, 248), "w41": (176, 215), "w49": (205, 251)}[size]
    render(n, h, *wpx, OUT)
