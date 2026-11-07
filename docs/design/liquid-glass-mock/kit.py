"""Tiny HTML/CSS kit for the C388 Liquid Glass design previews (headless Chromium).

These are design mockups, not simulator screenshots. Regenerate with:
  python candidates.py ../shots/proposal && python recommended.py ../shots/proposal
(needs Pillow and a Playwright chromium-headless-shell in ~/.cache/ms-playwright).
"""
import os, subprocess, base64, tempfile
SCRATCH = os.path.join(tempfile.gettempdir(), "caddie-liquid-glass-mock")

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
HOLE = os.path.join(REPO, "docs/design/2026-09-25-ui-redesign/hole1-topo.png")
CH = os.path.expanduser("~/.cache/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-linux64/chrome-headless-shell")

CSS = r"""
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,"Noto Sans CJK SC","Noto Sans",sans-serif;-webkit-font-smoothing:antialiased;background:#fff}
.ph{position:relative;width:390px;height:844px;overflow:hidden}
.light{background:#f2f2f7;color:#000}.dark{background:#0b0d0b;color:#fff}
.status{position:absolute;top:0;left:0;right:0;height:54px;display:flex;justify-content:space-between;align-items:center;padding:0 34px;font-weight:600;font-size:16px;z-index:9}
.island{position:absolute;top:11px;left:50%;margin-left:-62px;width:124px;height:36px;border-radius:20px;background:#000;z-index:10}
.homeind{position:absolute;bottom:8px;left:50%;margin-left:-67px;width:134px;height:5px;border-radius:3px;z-index:10}
.light .homeind{background:#000}.dark .homeind{background:#fff}
.g{backdrop-filter:blur(14px) saturate(180%);-webkit-backdrop-filter:blur(14px) saturate(180%);box-shadow:inset 0 1px 0 rgba(255,255,255,.55),inset 0 -1px 0 rgba(255,255,255,.12),0 6px 22px rgba(0,0,0,.18)}
.light .g,.g.l{background:rgba(255,255,255,.62);color:#000;border:.5px solid rgba(255,255,255,.7)}
.dark .g,.g.d{background:rgba(40,44,40,.42);color:#fff;border:.5px solid rgba(255,255,255,.28)}
.gp{background:#f5f5f2;color:#111;box-shadow:inset 0 1px 0 #fff,0 0 0 1px rgba(0,0,0,.12),0 8px 24px rgba(0,0,0,.35)}
.gpg{background:#187a43;color:#fff;box-shadow:inset 0 1px 0 rgba(255,255,255,.45),0 0 0 2px #000,0 8px 22px rgba(0,0,0,.25)}
.circ{border-radius:50%;display:flex;align-items:center;justify-content:center;flex-direction:column}
.cap{border-radius:999px;display:flex;align-items:center;justify-content:center;gap:6px}
.abs{position:absolute}
.t-large{font-size:34px;font-weight:700;letter-spacing:.3px}
.t-title{font-size:22px;font-weight:700}.t-head{font-size:17px;font-weight:600}.t-body{font-size:17px}
.t-sub{font-size:15px}.t-foot{font-size:13px}.t-cap{font-size:12px}
.sec{color:rgba(60,60,67,.6)}.dark .sec{color:rgba(235,235,245,.6)}
.card{background:#fff;border-radius:22px;padding:14px 16px}.dark .card{background:#1c1c1e}
.list{background:#fff;border-radius:22px;overflow:hidden}.dark .list{background:#1c1c1e}
.row{display:flex;align-items:center;justify-content:space-between;min-height:48px;padding:0 16px;border-bottom:.5px solid rgba(60,60,67,.18);font-size:17px}
.row:last-child{border-bottom:none}.chev{color:rgba(60,60,67,.35);font-size:18px}
.seg{display:flex;background:rgba(118,118,128,.14);border-radius:999px;padding:3px}.seg div{flex:1;text-align:center;font-size:14px;font-weight:600;padding:7px 0;border-radius:999px}
.seg .on{background:#fff;box-shadow:0 2px 6px rgba(0,0,0,.12)}.dark .seg{background:rgba(118,118,128,.3)}.dark .seg .on{background:#636366}
.btnp{background:#1f8a4c;color:#fff;border-radius:999px;font-weight:600;font-size:17px;display:flex;align-items:center;justify-content:center;height:52px}
.btnb{background:rgba(118,118,128,.14);color:#1f8a4c;border-radius:999px;font-weight:600;font-size:17px;display:flex;align-items:center;justify-content:center;height:48px}
.dark .btnb{background:rgba(118,118,128,.3);color:#fff}
.num{font-variant-numeric:tabular-nums}
.tag{position:absolute;left:8px;bottom:8px;font-size:11px;color:#fff;background:rgba(200,0,60,.85);padding:2px 6px;border-radius:6px;z-index:20}
.w{position:relative;overflow:hidden;background:#000;color:#fff;border-radius:46px}
.w46{width:208px;height:248px}.w41{width:176px;height:215px;border-radius:40px}.w49{width:205px;height:251px;border-radius:52px}
"""

def hole_bg(dim=0.0, pos="center 40%"):
    data = base64.b64encode(open(HOLE, "rb").read()).decode()
    over = f"linear-gradient(rgba(0,0,0,{dim}),rgba(0,0,0,{dim})),"
    return f"background:{over}url(data:image/png;base64,{data});background-size:cover;background-position:{pos};"

def phone(body, dark=False, status=True, tag=None, bg=""):
    cls = "dark" if dark else "light"
    st = '<div class="status"><span>9:41</span><span>􀙇 ▮▮▮</span></div><div class="island"></div>' if status else ""
    t = f'<div class="tag">{tag}</div>' if tag else ""
    return f'<div class="ph {cls}" style="{bg}">{st}{body}<div class="homeind"></div>{t}</div>'

def watch(body, size="w46", tag=None, bg=""):
    t = f'<div class="tag" style="left:50%;transform:translateX(-50%);top:2px;bottom:auto;white-space:nowrap">{tag}</div>' if tag else ""
    return f'<div class="w {size}" style="{bg}">{body}{t}</div>'

def render(name, inner, w, h, outdir, scale=2):
    html = f'<html><head><meta charset="utf-8"><style>{CSS}</style></head><body style="width:{w}px;height:{h}px;overflow:hidden">{inner}</body></html>'
    hp = os.path.join(SCRATCH, "html", name + ".html"); os.makedirs(os.path.dirname(hp), exist_ok=True)
    open(hp, "w").write(html)
    raw = os.path.join(SCRATCH, "raw", name + ".png"); os.makedirs(os.path.dirname(raw), exist_ok=True)
    subprocess.run([CH, "--no-sandbox", "--disable-gpu", "--hide-scrollbars", f"--force-device-scale-factor={scale}",
                    f"--window-size={w},{h}", f"--screenshot={raw}", "file://" + hp],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    from PIL import Image
    im = Image.open(raw).convert("RGB")
    tw = w if w > 300 else w * 2  # phones at 1x width (390), watches at 2x for legibility
    im = im.resize((tw, round(im.height * tw / im.width)), Image.LANCZOS)
    im = im.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    os.makedirs(outdir, exist_ok=True)
    im.save(os.path.join(outdir, name + ".png"), optimize=True)
