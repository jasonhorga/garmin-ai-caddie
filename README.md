# Garmin Golf 国服数据抓取与分析

把 connect.garmin.cn 上的高尔夫成绩单拉下来本地存着，做统计、画图、生成 dashboard。

## 数据来源与认证（重要）

国服 Garmin Connect 的 golf API 路径：

```
https://connect.garmin.cn/golf-api/gcs-golfcommunity/api/v2/scorecard/summary
https://connect.garmin.cn/golf-api/gcs-golfcommunity/api/v2/scorecard/detail
https://connect.garmin.cn/golf-api/gcs-golfcommunity/api/v2/shot/scorecard/{id}/hole
```

跟国际服不一样：

- 国际服走 `connectapi.garmin.com/gcs-golfcommunity/...`，国服在 `connect.garmin.cn` 加 `/golf-api/` 前缀
- 国服**不接受** OAuth2 Bearer token，必须用 web cookie + `connect-csrf-token` header
- 现成的 `garminconnect` / `garth` 库**国服都不能直接用**于 golf endpoint（前者登录流程在国服跑不通，后者绕到 connectapi.garmin.cn 上 503）

所以登录走"浏览器手动登录 → 复制 cookie + csrf"这条路。Cookie 是用户信息，全程不离开本地。

## 一次性环境准备

```bash
# 进入项目目录
cd /Users/jason/workspace/garmin

# 装依赖（uv 自动用 Python 3.12 + .venv）
uv sync

# 如果要处理 Garmin prodgeometry / Draco mesh
npm install
```

## 抓取数据

### Step 1 — 从浏览器导出认证

1. 浏览器登录 https://connect.garmin.cn ，进入"高尔夫"页
2. 打开开发者工具 → Network 标签 → Fetch/XHR 过滤
3. 刷新一次页面，随便点一条带 `gc-api` 或 `golf-api` 的请求
4. 在 **Request Headers** 里找：
   - 整行 `Cookie: ...` 的值（不带 `Cookie:` 前缀）→ 存到 `.garmin_tokens/web_cookie.txt`
   - `connect-csrf-token: ...` 的 UUID → 存到 `.garmin_tokens/csrf.txt`

```bash
# 简便做法：在终端粘贴
chmod 700 .garmin_tokens
pbpaste > .garmin_tokens/web_cookie.txt   # 粘贴 cookie 值后跑这个
pbpaste > .garmin_tokens/csrf.txt         # 粘贴 csrf 值后跑这个
chmod 600 .garmin_tokens/*
```

### Step 2 — 拉数据

```bash
uv run python fetch.py             # summary + 每场 detail
uv run python fetch.py --shots     # 加上每杆 GPS 点位（慢，可选）
```

- 增量：已下载的 scorecard 跳过，断网中断后重跑没事
- 数据存 `data/summary.json` 和 `data/scorecards/{id}.json`

### Cookie 过期后

JWT_WEB cookie 有效期约 ~9 小时。过期后 fetch 会 401/403。重做 Step 1 即可，CSRF token 通常较长期有效但顺手一起更新最稳。

## 分析脚本

| 命令 | 输出 | 作用 |
|---|---|---|
| `uv run python build_dashboard.py` | `output/dashboard/` + `output/dashboard.html` | 完整 dashboard 和 shot-distance 视图 |
| `uv run python fetch_courseview.py` | `data/courseview/*.pb` | 批量拉 CourseView IMG/protobuf |
| `uv run python parse_courseview.py` | 终端 / 调试结构 | 解析 Garmin IMG / GMP / TRE / RGN |
| `uv run python render_courseview.py` | `output/courseview/` | 渲染 CourseView IMG 几何 |
| `uv run python build_hole_view.py` | `output/hole_views/` | 把 IMG 几何叠到 Esri 卫星图 |
| `uv run python segment_hole.py` | `output/segmentation/` | 对 Garmin 730×730 raster 做 HSV 分割调试 |
| `uv run python ai_review.py` | `output/ai_reviews/` | 单场 AI 点评，需要 `ANTHROPIC_API_KEY` |

## CourseView prodgeometry 几何层

精细球洞几何不要依赖 IMG 主线。当前更可靠的路线是 Garmin Golf app 使用的
`prodgeometry` zip：解密后包含 `Fairway.drc`、`Green.drc`、`Bunker.drc`、
`Lake.drc`、`Rough.drc`、`Teebox.drc` 等 Draco mesh。

示例流程：

```bash
node fetch_courseview_geometry_key.js \
  --image-url '<prodgeometry zip URL or path>' \
  --profile-id '<playerProfileId>' \
  --zip data/courseview/prodgeometry/31795/hole02_220542.zip \
  --extract data/courseview/prodgeometry/31795/Hole02_220542 \
  --json

node decode_courseview_geometry.js \
  --geometry-dir data/courseview/prodgeometry/31795/Hole02_220542

.venv/bin/python overlay_prodgeometry_on_raster.py \
  --mesh-json output/prodgeometry/gid31795_h02_meshes.json \
  --snapshot logs/probe_map_bodies/snapshot_400065_hole.json \
  --hole 2

.venv/bin/python measure_prodgeometry_distances.py \
  --mesh-json output/prodgeometry/gid31795_h02_meshes.json
```

本地认证、个人 Garmin 数据、下载的 CourseView/prodgeometry 文件和生成图都由
`.gitignore` 排除，不要上传到 GitHub。

新增数据后建议跑顺序：

```bash
uv run python fetch.py
uv run python fetch.py --shots      # 可选：拉每杆 GPS
uv run python build_dashboard.py
open output/dashboard.html
```

## 项目结构

```
.
├── fetch.py                    # 拉 scorecard
├── fetch_courseview.py         # 拉 CourseView IMG / protobuf
├── parse_courseview.py         # Garmin IMG parser
├── decode_courseview_geometry.js # Draco mesh 解码
├── overlay_prodgeometry_on_raster.py # prodgeometry → 730 raster overlay
├── measure_prodgeometry_distances.py # tee/target 到 hazard 距离
├── build_dashboard.py          # 完整 HTML dashboard
├── pyproject.toml / uv.lock    # Python 依赖
├── package.json / package-lock.json # Node / draco3d 依赖
├── clubs.example.json          # 杆包映射示例；本地用 clubs.json
├── .garmin_tokens/             # cookie + csrf / OAuth token（mode 600，禁止提交）
│   ├── web_cookie.txt
│   └── csrf.txt
├── data/                       # 抓下来的原始数据（禁止提交）
│   ├── summary.json            #   所有 scorecard 的 summary 列表
│   ├── scorecards/{id}.json    #   每场详情（每洞杆数/推杆/Fairway/GPS）
│   ├── shots/{id}.json         #   每杆 GPS（仅在 fetch.py --shots 后）
│   └── courseview/             #   IMG/prodgeometry 本地缓存
├── output/                     # 生成的图和 dashboard（禁止提交）
└── logs/                       # probe 调试日志（禁止提交）
```

## 球场归一化逻辑（重要）

国服把"黑骑士 A/B/C"这种 9 洞场切分得很彻底，每个 9 洞有独立 `globalId`：

- A=31794, B=31795, C=31796（黑骑士）
- A=31765, B=46249, C=39668（香山）

每场 round 在 detail 里有 `frontNineGlobalCourseId` 和 `backNineGlobalCourseId`，可以可靠拆分。

`build_course_map.py` 自动推断每个 globalId 对应的字母 label：扫数据，看每个 ID 在不同 round 里关联到哪个字母（"A/B" 拆出 A=front、B=back），出现最多的字母赢。

**18 洞整场判定**：俱乐部下只有一个 globalId 的，标记为 `is_18=true`（北湖九号、龙泉谷、万柳等）。这种球场 detail 里 `backNineGlobalCourseId=null`，分析时不能拆 9 洞统计，要作为 18 洞整体。

## 已知坑

1. **Garth 有 deprecation warning**：底层装了 garth 但实际不用它登录，可以忽略 warning。后续可以彻底移除依赖。
2. **数据有些字段在早期场次缺失**：2024 年之前手表没记 putts，所以早期 round 没有推杆数据。Fairway 命中数据更早就有。
3. **Cookie 过期**：脚本不会自动续期，过期了脚本会 401 退出，重跑 Step 1 即可。
4. **本地数据不进 GitHub**：`.garmin_tokens/`、`data/`、`downloads/`、`output/`、`logs/`、`clubs.json` 都由 `.gitignore` 排除。

## 下一步可选

- **AI 单场点评**：把单场 scorecard 喂给 Claude API，生成"亮点 + 短板 + 下次重点"。需要 `ANTHROPIC_API_KEY`。
- **Fairway 偏向分析**：HIT/LEFT/RIGHT 比例随时间，看失误是不是固定偏一侧
- **罚杆地图**：哪些洞老吃罚杆，结合 GPS 看是不是固定区域
- **每杆轨迹图**：用 `fetch.py --shots` 抓 GPS，叠卫星图画出每杆落点（之前讨论过的方案）
