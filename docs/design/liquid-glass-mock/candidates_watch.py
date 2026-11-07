from parts import *

def hero(top=46, big=58):
    return f'''<div class="abs" style="left:0;right:0;top:{top}px;text-align:center"><div class="num" style="font-size:{big}px;font-weight:800;line-height:1;color:#7ee08a">152</div>
<div style="font-size:13px;opacity:.8">码 · 到果岭中</div><div class="num" style="display:flex;justify-content:space-between;padding:4px 28px;font-size:14px"><span>前 140</span><span>后 161</span></div>
<div style="font-size:13px;color:#ffd45a">7 号铁 · 稳妥</div></div>'''
dots = '<div class="abs" style="right:5px;top:96px;width:4px;display:flex;flex-direction:column;gap:4px"><i style="height:8px;background:#fff;border-radius:2px"></i><i style="height:8px;background:#666;border-radius:2px"></i><i style="height:8px;background:#666;border-radius:2px"></i></div>'
def wlist(title, items, back=True):
    b = '<div class="abs g d circ" style="left:12px;top:10px;width:36px;height:36px;font-size:18px">‹</div>' if back else ""
    rows = "".join(f'<div style="background:#222;border-radius:16px;min-height:42px;margin-bottom:5px;padding:6px 12px;display:flex;align-items:center;justify-content:space-between;font-size:15px;{s}"><span>{a}</span><span style="opacity:.7;font-size:12px">{c}</span></div>' for a, c, s in items)
    return f'{b}<div class="abs" style="left:56px;top:18px;font-size:16px;font-weight:700">{title}</div><div class="abs" style="left:8px;right:8px;top:54px">{rows}</div>'

W = {}
W["rec-w-distance-46"] = (watch(w_title() + hero() + dots + w_corners()), "w46")
W["rec-w-distance-41"] = (watch(w_title() + hero(40, 50) + dots + w_corners(10, 8), "w41"), "w41")
W["rec-w-holemap-46"] = (watch('<div class="abs" style="left:56px;right:0;top:0;bottom:0;' + hole_bg(0, "center 45%") + '"></div>' + w_title() +
  '<div class="abs num" style="left:14px;top:46px;font-size:20px;font-weight:700">161</div><div class="abs num" style="left:14px;top:70px;font-size:30px;font-weight:800;color:#7ee08a">152</div><div class="abs num" style="left:14px;top:106px;font-size:20px;font-weight:700">140</div>' +
  '<div class="abs g d cap" style="left:64px;right:64px;bottom:14px;height:40px;font-size:13px;font-weight:600">第 2 杆 ↺</div>' + dots + w_corners()), "w46")
W["rec-w-score-46"] = (watch('<div class="abs g d circ" style="left:12px;top:10px;width:36px;height:36px">✕</div><div class="abs" style="left:56px;top:18px;font-size:15px;font-weight:700">H7 · P4</div>' + "".join(
  f'<div class="abs" style="left:10px;right:10px;top:{t}px;display:flex;align-items:center;justify-content:space-between"><div class="g d circ" style="width:44px;height:44px;font-size:22px">−</div><div style="{s};border-radius:14px;width:80px;height:44px;display:flex;align-items:center;justify-content:center;gap:4px"><span style="font-size:11px;opacity:.8">{l}</span><b class="num" style="font-size:24px">{v}</b></div><div class="g d circ" style="width:44px;height:44px;font-size:22px">＋</div></div>'
  for t, l, v, s in [(52, "总杆", 5, "box-shadow:inset 0 0 0 2px #7ee08a"), (102, "推杆", 2, ""), (152, "罚杆", 0, "")]) +
  '<div class="abs g d cap" style="left:10px;bottom:8px;width:84px;height:40px;font-size:14px">开球 —</div><div class="abs gpg cap" style="right:10px;bottom:8px;width:92px;height:40px;font-size:15px;font-weight:700">保存</div>'), "w46")
W["rec-w-score-41"] = (watch('<div class="abs g d circ" style="left:10px;top:8px;width:32px;height:32px">✕</div><div class="abs" style="left:48px;top:14px;font-size:14px;font-weight:700">H7 · P4</div>' + "".join(
  f'<div class="abs" style="left:8px;right:8px;top:{t}px;display:flex;align-items:center;justify-content:space-between"><div class="g d circ" style="width:40px;height:40px;font-size:20px">−</div><div style="{s};border-radius:12px;width:64px;height:40px;display:flex;align-items:center;justify-content:center;gap:3px"><span style="font-size:10px;opacity:.8">{l}</span><b class="num" style="font-size:22px">{v}</b></div><div class="g d circ" style="width:40px;height:40px;font-size:20px">＋</div></div>'
  for t, l, v, s in [(46, "总杆", 5, "box-shadow:inset 0 0 0 2px #7ee08a"), (92, "推杆", 2, ""), (138, "罚杆", 0, "opacity:.5")]) +
  '<div class="abs" style="left:0;right:0;bottom:0;height:56px;background:linear-gradient(transparent,#000 40%)"></div><div class="abs g d cap" style="left:8px;bottom:6px;width:70px;height:38px;font-size:13px">开球 —</div><div class="abs gpg cap" style="right:8px;bottom:6px;width:80px;height:38px;font-size:15px;font-weight:700">保存</div>', "w41"), "w41")
W["rec-w-menu-46"] = (watch(wlist("菜单", [("⚑ 记分", "", ""), ("▦ 计分卡", "+3", ""), ("⌖ 选洞", "H7", ""), ("✦ 球童选项", "", "")])), "w46")
W["rec-w-scorecard-41"] = (watch(wlist("计分卡 +2", [("1 · P4", "<b style='color:#7ee08a;font-size:16px'>4</b>", ""), ("2 · P5", "<b style='color:#ff6b5a;font-size:16px'>6</b>", ""), ("3 · P3", "<b style='color:#7ee08a;font-size:16px'>2</b>", ""), ("4 · P4", "<b style='font-size:16px'>5</b>", "")]), "w41"), "w41")
W["rec-w-tees-46"] = (watch(wlist("发球台", [("<span style='color:#fff'>●</span> 白 T", "✓", ""), ("<span style='color:#1a73e8'>●</span> 蓝 T", "码数未知", ""), ("<span style='color:#d33'>●</span> 红 T", "码数未知", "")])), "w46")
W["rec-w-finish-46"] = (watch('<div class="abs" style="left:14px;right:14px;top:34px;text-align:center"><div style="font-size:19px;font-weight:700">结束本场？</div><div style="font-size:13px;opacity:.75;margin-top:6px">先保存到本机，服务器确认后完成同步</div></div><div class="abs cap" style="left:12px;right:12px;bottom:62px;height:44px;background:#ff453a;font-weight:700">确认结束</div><div class="abs g d cap" style="left:12px;right:12px;bottom:12px;height:44px;font-weight:600">返回</div>'), "w46")
W["rec-w-turn-49"] = (watch(wlist("后九打完了", [("前九", "第 1–9 洞", ""), ("后九再打一次", "", ""), ("只打 9 洞", "结束本场", "")]) + '<div class="abs gpg cap" style="left:14px;right:14px;bottom:12px;height:44px;font-weight:700">接着打 前九</div>', "w49"), "w49")
