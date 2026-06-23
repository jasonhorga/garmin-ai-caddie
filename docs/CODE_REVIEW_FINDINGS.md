# 代码库复查发现(Codex,2026-06-23)

> Codex(gpt-5.5)对整个 garmin-ai-caddie 代码库的工程复查结果 + 处置建议。
> 复查为只读,未跑测试。**无 blocker**,以下为 high/medium 的真实问题。
> 处置:本次已做「文档归位」+ 记录;代码 bug 与工具重组按下方分阶段计划安全执行(避免一次性大改破坏 CI)。

## 1. 正确性(优先修)

- **✅ 已修(2026-06-23)HIGH — 窗口化统计 shot-ref 重索引**:`cached_build_history_stats` 从 `windowed_history_data()` 构建,该函数**过滤** shots(history_stats.py:3743),随后 `_effective_shots` 枚举过滤后的列表生成 `{round}:{hole}:{index}` 引用(history_stats.py:183/33)→ `last10`/`12m` 的 shot-ref 与全量不一致,**订正(球杆/球位)和 mobile 统计的 refs 静默指向错误的杆**;`build_drilldown_index` 也跑在窗口化 data 上、同样受影响。**修法**:`load_history_data` 给每个 shot 打稳定 `_globalIndex`(全量列表位置,= 旧全量 ref 行为 → 已落库订正仍匹配);窗口化共享 shot dict 引用会带着它;4 处 `_shot_ref`(history_stats/history_drilldown/history_round_detail/caddie_context)统一改用 `shot.get('_globalIndex', index)`。回归测试 `test_windowed_shot_refs_stay_stable_for_corrections` 锁死:r3 在 last10 窗口仍是 `r3:1:2` 不漂成 `r3:1:0`。
- **✅ 已修(2026-06-23)MEDIUM — decision audit 不认 shot 字段别名**:`_actual_option_id` 只读 `meters`、`_club_match` 只读 `clubName`、`_risk_triggered` 只看 `end.feature.surface.kind`/`end.lie`;真实 Garmin/mobile 杆用 `distance`/`club`/`surface`/`endLie` → 被 audit 成 `info_gap`/缺 carry/未知 surface。**修法**:新增 `_normalize_actual_shot`,在 `_actual_shots_from_input`(audit_decision 路径)+ `judge_decision_outcome` 的 `first` 提取后单点归一(distance→meters / club→clubName / surface|endLie→end.lie,镜像 history_stats `_shot_distance`/`_shot_surface`/`_shot_club` 别名优先级),返回副本不改入参。回归测试 `test_audit_reads_garmin_field_aliases` + `test_outcome_reads_garmin_field_aliases`。
- **MEDIUM — 网格几何无法分类 WGS84 端点**:`classify_shot_surface`(geometry_evidence.py:313)和 route evidence(:361)只从 hazards 读 `refLat/refLon`;而 `build_hole_map_dto`(:706)正确回退到 mesh ref。修:分类/证据也用同样的 mesh 回退。
- **MEDIUM — 非 owner mobile flow 不一致**:player token 能访问 course options(players_api.py:104 / main.py:759),但 course/round package 端点不接受 `player_id`、默认加载 owner 数据(main.py:764 / mobile.py:76)。非 owner 能选球场却无法用自己 token 开局;若后续打开有 owner 数据耦合风险。
- **LOW/MED — course_prep 运行时依赖根脚本**:`course_prep` 从 `measure_prodgeometry_distances.py` import `mesh_components`(course_prep.py:137/245)。打包/部署缺散落脚本时,沙坑/果岭距离逻辑会降级。(→ §2 把该模块迁进包。)

## 2. 仓库结构重组(分阶段,安全)

> **2026-06-23 复核纠正(import 图全量审计)**:Codex 的「不可移」列表**不完整**。Docker 用 `COPY *.py ./` + `COPY *.js ./` **glob** 把根脚本铺进镜像,这是 `ai_caddie/*` 能 import 根模块的机制;prodgeometry 链(`ensure_prodgeometry`→`geometry_sync.process_hole`)**按裸文件名 `cwd=ROOT` subprocess**。因此除 Codex 原列 5 个外,还有 4 个**必须留根**:`export_prodgeometry_hazards.py`、`garmin_playwright_login.py`、`fetch_courseview_geometry_key.js`、`decode_courseview_geometry.js`。

**绝不能移(生产 import / 裸名 subprocess,共 9)**:`fetch.py`、`garmin_auth.py`、`garmin_playwright_login.py`、`inspect_courseview_release.py`、`batch_prodgeometry_course.py`、`measure_prodgeometry_distances.py`、`export_prodgeometry_hazards.py`、`fetch_courseview_geometry_key.js`、`decode_courseview_geometry.js`。

**✅ 已做(2026-06-23)阶段 2(安全子集)**:把**零生产/ops/CI/test 入向 + 出向干净(只 stdlib/三方/`ai_caddie` 包/簇内同伴)**的 10 个独立工具移入 `tools/`,`git mv` 保历史,README 命令/目录树同步更新,全后端套件 + 移动文件 py_compile + 簇内 import 解析均验证:
- `tools/courseview/`:`parse_courseview.py`(簇库)+ 依赖它的 `build_hole_view.py`、`cross_validate_hole.py`、`render_courseview.py`、`overlay_img_on_garmin_raster.py` + `fetch_courseview.py`(**整簇同移**,保按 script 运行时 `from parse_courseview import` 可解析)。
- `tools/prototype/`:`build_dashboard.py`、`build_hole_overlay.py`、`segment_hole.py`。
- `tools/reports/`:`ai_caddie_analyze.py`(只 import `ai_caddie` 包,`uv run` 可解析)。

**延后(需额外接线,风险/边际)**:`ai_review.py`(test 入向 `test_ai_review_cli.py`)、`ai_caddie_web.py`(test 入向 + 出向 pinned `garmin_auth`/`inspect_courseview_release`/subprocess `fetch.py`)、`ai_caddie_batch_geometry.py`(出向裸名 subprocess `batch_prodgeometry_course.py`)、`overlay_prodgeometry_on_raster.py`(prod 走 `skip_overlay=True` 死分支,但被 pinned orchestrator 裸名引用)。

**阶段 1(未做,高风险)**:把 `fetch`/`garmin_auth`/`courseview_release`/`prodgeometry` 共享逻辑迁进 `ai_caddie/` 包 + 根留 shim —— 触及 auth/sync 关键路径,uv 测试 mock 这层、无法验真实 Garmin 认证 + Docker glob + 裸名 subprocess 解析,**应在可验证部署时由用户在场再做**。

**文档(已做)**:README 留根;FEASIBILITY.md + IMG_RESEARCH.md → `docs/research/`;REMOTE_DEV.md → `docs/deployment/`;STATUS.md → `docs/operations/`。

## 3. 安全 / 数据处理

- **MEDIUM — player token 进 query/path**:capability token 走 query string(players_api.py:45),admin 生成的分享 URL 把 token 嵌在路径(:157)。会经浏览器历史/日志/截图/referrer 泄漏。建议改 bearer-only 或短时换取链接。
- **MEDIUM — Garmin 同步改全局模块路径**:同步期间改 `fetch.py`/`garmin_auth.py` 的全局 path(garmin_cn.py:63)。并发同步/测试会交叉写 token/数据根。建议加进程锁或把 `fetch.py` 改成接收显式 config。
- **LOW/MED — readiness/sync-status 公开**:`/api/v2/readiness`、`/api/v2/sync/status` 是公开路由(main.py:370/946),暴露运维计数/快照状态。私有试用期可 admin 门控或只回粗粒度健康。
- **LOW — iOS 记录会话响应体**:GarminSessionClient.swift:63 以 public privacy 记录非 2xx Garmin 会话响应体。会话/token 端点避免记 body。

## 4. 死代码 / 重复

- **shot-ref 生成器重复**于 `history_stats`/`history_drilldown`/`history_round_detail`/`caddie_context` —— 这是 §1 HIGH 窗口化 ref bug 的根因。集中成单一 canonical ref 生成。
- `ai_caddie_web.py`、`build_dashboard.py`、`ai_caddie/analysis.py` 大部分是 legacy/原型;活跃产品路径是 `server_v2/`、`web_v2/`、mobile。冻结或移 `tools/prototype/`(更新测试后)。
- `ai_caddie/llm.py` 是 `llm_providers` 的薄包装;生产多直接 import `llm_providers`。仅 legacy CLI 需要则保留,否则弃用。

---

*Codex 全库复查,2026-06-23。本会话已处置:文档归位 + 本文档记录;代码 bug 与工具重组按上方分阶段计划执行。*
