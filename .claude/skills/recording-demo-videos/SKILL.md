---
name: recording-demo-videos
description: Use when the user wants to SEE a built AI-Caddie feature demonstrated on video before it ships — a demo / 录屏 / 走查 / 演示 / visual proof — across ANY of the three surfaces (iOS app · Apple Watch app · Web). Covers capturing per-step screenshots on each surface, stitching them into a captioned mp4, publishing a public link, and self-verifying it before sending.
---

# Recording demo videos — iOS · Watch · Web (跨终端)

## Core principle
A demo is only useful if the viewer can follow it **silently, at a readable pace, start to finish**, and only trustworthy if **I watched it myself first**. A raw fast screen-grab wastes his time and looks unverified.

**One unified method for all three surfaces: per-step screenshots → captioned mp4.** Each surface only has to produce **ordered, labelled screenshots**; a single tool (`stitch_demo.py`) turns them into the video — one screenshot per step held ~4.5 s with a plain-Chinese caption strip on top. This is *better than live screen-recording* for native apps: deterministic (no home-screen / frozen-tail / timing artefacts — the live simctl route hit all of those), captions are fully controlled, and the frames literally ARE the screenshots so verification is trivial.

## Hard rules (don't negotiate)
- **Captions, not narration.** One **plain-Chinese** line per step, burned into a TOP strip. **Zero dev jargon** — say what it does for the user (see [[plain-language-no-jargon]]).
- **Readable pace.** Hold each step ~4.5 s (`DWELL_SECONDS` in `stitch_demo.py`). Silent-test: if you can't follow it muted, it's not done.
- **Whole flow, clean end.** Walk the full path; last step is a natural end (no long frozen tail — the stitch handles this).
- **mp4 (H.264, yuv420p, +faststart, `-an`), never webm.** Safari/iOS can't play VP8 webm. `stitch_demo.py` already emits this.
- **Reflect CURRENT code.** Deploy the change to the homeserver (web/backend) or merge it to `integration/v2` (iOS/Watch) BEFORE capturing — don't demo a bug you already fixed. Native captures run the app against the **live funnel backend**, so the homeserver must be on the right commit.
- **Verify it YOURSELF before sending.** HTTP 200 ≠ verified. `ffprobe` (real duration/codec) + full decode (`ffmpeg -v error -i v.mp4 -f null -` = exit 0) + **extract 3–5 frames and Read them as images** — captions present + plain Chinese, real current UI (not a black/placeholder frame).

## The stitch tool (the heart — same for all three)
`stitch_demo.py` (in this skill dir). Input: a manifest + output path.
```
python3 stitch_demo.py manifest.json out.mp4
# manifest.json = [{"image": "01-home.png", "caption": "首页:打球 · 备战 · 历史复盘"}, ...]
```
It normalises each screenshot to 1280-tall (even dims), burns the caption (文泉驿 CJK font at `/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc`), and ffmpeg-concats each held 4.5 s → H.264 mp4. **Write the manifest yourself** — the captions are the demo; order the screenshots by their filename prefix.

## Capturing screenshots per surface

### Web (fast, local on the homeserver)
Playwright drives the real web app + `page.screenshot({path})` per step. Reuse the notebook skill's caption/pace idea but capture STILLS (don't rely on live recordVideo). Serve `web_v2` against the live backend on a free port, script the flow, screenshot each step to a dir, then stitch. See [[web-screenshot-test-env]] for the ungated/mock render harness (`web_v2/e2e/screenshots.spec.ts`) — the cleanest way to hit every page with seeded data.

### iOS app (native — GitHub Actions macOS, no local Mac)
The **only** way to run/record a native app here is the macОС runner. The harness already exists:
- `.github/workflows/native-mobile.yml` (workflow_dispatch): boots an iPhone-16 sim, runs `AICaddieUITests` (`RealFlowUITests` drives the REAL app against the funnel + owner token + injected GPS), writes `XCUIScreen.main.screenshot()` per step to `Documents/real-screenshots/` → uploads the **`real-screenshots`** artifact (+ a11y trees).
- Trigger: `gh workflow run native-mobile.yml --ref integration/v2` → wait ~8–23 min → `gh run download <id> -n real-screenshots`.
- Add/adjust steps by editing `RealFlowUITests.swift` (`save("NN-name")` per screen). Some review holes are "暂无落点数据" without decoded geometry — swipe the 落点图 pager to a hole that has it (see `ReviewEditUITests.swift`), or ensure geometry is deployed ([[geometry-deploy-private-volume]]).

### Apple Watch app (native — same runner, no XCUITest on watchOS)
- Same workflow boots a Watch sim and, via `simctl launch … -uitest-screen <name>` against `WatchUITestRoot.swift` (seeded screens), does `simctl io … screenshot` per screen → uploads the **`watch-real-screenshots`** artifact.
- To show a NEW watch screen: add it to `WatchUITestRoot.swift`'s `-uitest-screen` switch, list its name in the workflow's watch loop.

## Publish + verify + deliver
1. **Stitch** each surface's screenshots (with a hand-written caption manifest) → one mp4 per surface (or a combined one).
2. **Publish** via Tailscale Funnel sub-path on the homeserver (passwordless sudo; give the trailing slash): `python3 -m http.server <port> --bind 0.0.0.0` in the video dir, then `sudo tailscale funnel --bg --set-path=/<name> <port>` → `https://caddie.taile36706.ts.net/<name>/`. Don't steal the occupied 443/8443/10000 roots — add a fresh `--set-path`. Reach the homeserver via [[homeserver-access]].
3. **Self-verify**: `ffprobe` + decode + Read 3–5 extracted frames (`ffmpeg -ss <t> -i v.mp4 -frames:v 1 f.png`).
4. **Deliver** the URL(s) + a short plain-Chinese "what each video shows" list. Wait for him to watch.
5. **Teardown** after he's seen it: `sudo tailscale funnel --set-path=/<name> off`; stop the http.server.

## Common mistakes → fix
| Mistake | Fix |
|---|---|
| Tried to Playwright-record the native iOS/Watch app | Playwright is web-only. Native = macOS-runner screenshots → stitch. |
| `.webm` / raw simctl recordVideo (desktop/frozen-tail) | Use the screenshot→stitch path; `stitch_demo.py` emits Safari-safe mp4. |
| Captions flash / dev jargon | one plain-Chinese line per step, ~4.5 s dwell, silent-test. |
| Demo'd an already-fixed bug | deploy/merge the change first; native runs against the live funnel. |
| "I checked it's up (200)" | not verified — ffprobe + decode + **Read frames**. |
| Left the funnel path / http.server up | teardown after he's watched. |

## Cost note
Native captures go through a **~8–23 min** GitHub Actions run — normal, not stuck. Web + stitch are fast/local. Trigger the run, poll with a bounded loop, download, stitch, verify.
