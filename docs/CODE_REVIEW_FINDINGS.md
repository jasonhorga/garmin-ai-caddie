# 代码库复查发现(Codex,2026-06-23)

> Codex(gpt-5.5)对整个 garmin-ai-caddie 代码库的工程复查结果 + 处置建议。
> 复查为只读,未跑测试。**无 blocker**,以下为 high/medium 的真实问题。
> 处置:本次已做「文档归位」+ 记录;代码 bug 与工具重组按下方分阶段计划安全执行(避免一次性大改破坏 CI)。

## 1. 正确性(优先修)

- **HIGH — 窗口化统计 shot-ref 重索引**:`cached_build_history_stats` 从 `windowed_history_data()` 构建,该函数**过滤** shots(history_stats.py:3743),随后 `_effective_shots` 枚举过滤后的列表生成 `{round}:{hole}:{index}` 引用(history_stats.py:183/33)。→ `last10`/`12m` 的 shot-ref 与全量不一致,**订正(球杆/球位)和 mobile 统计的 refs 可能静默指向错误的杆**。修法:过滤前先固定稳定的 `globalShotIndex`/源 ref,或由 shot provenance 派生 ref。根因见 §4(4 处重复 ref 生成器)。
- **MEDIUM — decision audit 不认 shot 字段别名**:`_actual_option_id` 只读 `meters`(decision.py:3189)、`_club_match` 只读 `clubName`(:3279)、风险检测只看 `end.feature.surface.kind`/`end.lie`(:3249);别处用 `distance`/`club`/`surface`/`endLie`。真实 Garmin/mobile 杆会被 audit 成 `info_gap`/缺 carry/未知 surface。修:audit 前归一 actual shot 字段。
- **MEDIUM — 网格几何无法分类 WGS84 端点**:`classify_shot_surface`(geometry_evidence.py:313)和 route evidence(:361)只从 hazards 读 `refLat/refLon`;而 `build_hole_map_dto`(:706)正确回退到 mesh ref。修:分类/证据也用同样的 mesh 回退。
- **MEDIUM — 非 owner mobile flow 不一致**:player token 能访问 course options(players_api.py:104 / main.py:759),但 course/round package 端点不接受 `player_id`、默认加载 owner 数据(main.py:764 / mobile.py:76)。非 owner 能选球场却无法用自己 token 开局;若后续打开有 owner 数据耦合风险。
- **LOW/MED — course_prep 运行时依赖根脚本**:`course_prep` 从 `measure_prodgeometry_distances.py` import `mesh_components`(course_prep.py:137/245)。打包/部署缺散落脚本时,沙坑/果岭距离逻辑会降级。(→ §2 把该模块迁进包。)

## 2. 仓库结构重组(分阶段,安全)

**绝不能直接移**(被生产包 import):`fetch.py`、`garmin_auth.py`、`inspect_courseview_release.py`、`batch_prodgeometry_course.py`、`measure_prodgeometry_distances.py`(被 connectors/garmin_cn.py:11、geometry_sync.py:10、course_reference.py:17、course_search.py:14、course_prep.py 等 import)。

**阶段 1(先做,重构)**:把共享逻辑迁进包 —— `ai_caddie/garmin_fetch.py`、`ai_caddie/garmin_auth.py`、`ai_caddie/courseview_release.py`、`ai_caddie/prodgeometry.py`;根目录留薄 shim 过渡。每步跑 `uv run python -m unittest discover -s tests` 保绿。
**阶段 2(再做)**:移独立/原型工具(注意工具间互相 import 需一并处理 + 更新 README 命令/目录树):
- `tools/prodgeometry/`:ai_caddie_batch_geometry.py、export_prodgeometry_hazards.py、overlay_prodgeometry_on_raster.py、overlay_img_on_garmin_raster.py、decode_courseview_geometry.js、fetch_courseview_geometry_key.js
- `tools/courseview/`:parse_courseview.py、fetch_courseview.py、render_courseview.py、inspect_courseview_release.py(shim 后)
- `tools/prototype/`:ai_caddie_web.py、build_dashboard.py、build_hole_overlay.py、build_hole_view.py、segment_hole.py、cross_validate_hole.py
- `tools/reports/`:ai_review.py、ai_caddie_analyze.py
- `ops/` 保持原样(运维脚本)。
**文档(本次已做)**:README 留根;FEASIBILITY.md + IMG_RESEARCH.md → `docs/research/`;REMOTE_DEV.md → `docs/deployment/`;STATUS.md → `docs/operations/`。

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
