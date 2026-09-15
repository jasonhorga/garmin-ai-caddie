# CourseView 球场名称来源补充证据

日期：2026-09-14 UTC  
范围：PHONE-UX5 最新附近球场名称混用反馈；Red Flag Valley、West Park、
Bangchuidao、Dalian Wanshan、Blue Ocean。本文是只读调查，不修改产品代码。

## 结论

当前 Garmin CN CourseView 目录没有可见的“中文名称字段”或认证目录接口。
匿名目录返回的 `f12` 是单一 provider `name` 字符串；即使请求带
`languageCode=zh-CN`，返回仍是英文。不能把中文查询成功、城市字段是中文，或
历史/球员输入的中文名称，解释成 CourseView 已提供中文翻译。

## 2026-09-14 匿名 CourseView 实测

证据保存在 homeserver：
`/home/jason/garmin-ai-caddie-data/operations/phone-ux5-course-name-evidence-20260914/`。
`queries.json` 是英文查询，`queries-zh.json` 是中文查询，
`boundaries-nearby.json` 是 Dalian 100 km/20 km Nearby 查询；所有 protobuf 和
JSON 的 SHA-256 在 `sha256.txt`。请求均为无 cookie、无 Authorization 的 GET。

目录请求模板（代码同 `ai_caddie/courses/course_search.py:158-183`）：

```text
https://omt.garmin.cn/CourseViewData/Courses?courseName=<urlencoded>&bits=23&pageSize=100&page=1&languageCode=zh-CN
```

Nearby/Boundaries 模板（代码同 `ai_caddie/courses/course_search.py:186-203`）：

```text
https://omt.garmin.cn/CourseViewData/Boundaries/<lon_semicircles>,<lat_semicircles>,<radius_m>,32/Courses?pageSize=100&page=1&languageCode=zh-CN
```

| 用户看到的名称 | CourseView 返回名 | global ID / build | 中文请求结果 |
|---|---|---:|---|
| Red Flag Valley | `Red Flag Valley Golf Club ~ Dragon` / `~ Unicorn` | 31716/31717, 266 | 查询“红旗谷高尔夫俱乐部”仍返回上述英文；“红旗谷高尔夫球场”返回 204 |
| West Park | `West Park Golf & Country Club ~ West` / `~ Light` | 31719/31720, 266 | “西郊高尔夫…”查询返回 204；英文 provider 名不变 |
| Bangchuidao | `Bangchuidao Golf Club ~ Left` / `~ Right` | 39256/42075, 290 | “棒棰岛高尔夫…”查询仍返回上述英文 |
| Dalian Wanshan | `Dalian Wanshan Golf Club` | 31722, 266 | “大连万山…”的多个精确查询均 204 |
| Blue Ocean | `Dalian Blue Ocean Golf Club`（9 洞；另有加拿大 `Blue Ocean Golf Club`） | 39576, 266（Dalian） | “蓝海高尔夫”返回 `Dalian Blue Ocean Golf Club`，没有中文字段 |

Nearby 的同一返回也确认了这五个 provider 名：
`boundaries-nearby.json` 的 Dalian 100 km 结果包含 39576、39256、42075、
31716、31717、31719、31720、31722，全部是英文 `name`。注意 provider 自己还把
Bangchuidao 的城市拼成 `Dailian City`，这也不是本地化证据。

### locale 参数不是翻译开关

Red Flag Valley 的同一请求分别使用 `languageCode=zh-CN`、`zh_CN`、`en-US`、
错误参数 `language=zh-CN` 和不带语言参数；五份 protobuf 都是 521 bytes，
SHA-256 均为 `7e961bcfcb3e299e21bd44dfcc0a8e765e4bbdade2273a9bad5b595ae7e0b6ab`，
且记录内容为英文两个 layout。也就是说目前该 endpoint 对名称没有可观察的 locale
选择行为。

### courseData 也不含名称

对 31716、31717、31719、31720、31722、39256、42075、39576 的
`courseData/{build},{gid},32` 和 `/Hazards` 均返回 200 JSON；顶层键只有：
`$id`、`BuildId`、`GlobalLayoutId`、`Group`、`Holes`、`Tees`。没有 `Name`、
`CourseName`、`LocalizedName`、`Names` 或语言映射。代码固定使用该路径见
`ai_caddie/courses/courseview_core.py:315-333`，解析器也只读取这些事实字段见
`ai_caddie/courses/courseview_core.py:260-305`。

## 认证 Garmin CN API 的边界

仓库中的认证连接器只使用 `https://connect.garmin.cn/golf-api/gcs-golfcommunity/api/v2`
（`ai_caddie/garmin/fetch.py:33`），并通过 cookie + `connect-csrf-token` 建立
会话（同文件 `:1-6,40-50`）。已实现的认证请求是：

- `/scorecard/summary?user-locale=zh_CN&per-page=...`
  （`fetch.py:64-78`）；
- `/scorecard/detail` 与 `/shot/scorecard/{id}/hole`
  （`fetch.py:247-306`）；
- `/club/player`、`/club/types`（`fetch.py:81-105`）。

其中只有 scorecard 的 `courseSnapshots[0].name` 能作为玩家已打球局的 Garmin
名称来源；归一化时明确写入 `garminSnapshotName`，见
`ai_caddie/connectors/snapshot.py:221-246,287-296`。它是“某次已同步球局的
localized snapshot name”，不是 CourseView 目录的翻译表。

无认证访问 `/golf-api/gcs-golfcommunity/api/v2/scorecard/summary?...` 在本次
调查返回 HTTP 403、0 bytes（证据 `connect-scorecard-unauth.headers/body`）。
没有在仓库或公开 CourseView 响应中发现一个“按 global ID 获取中文目录名”的认证
路径；不能凭猜测调用私有接口，也不应把认证 scorecard 名称跨物理球场 ID 迁移。

## 对五个球场的产品建议

1. 对这五个 CourseView 行，按 provider 原文显示英文（可做空白/`~` 分隔符的
   规范化），并保留 `providerName`；不要恢复旧的英文→中文 global-ID 别名。
2. 只有同一 global ID 的 Garmin 认证 scorecard `courseSnapshots[0].name`，且
   provenance 标记为 `garmin_cn_web_session`，才可以覆盖附近/目录英文名；这与
   `ai_caddie/courses/name_authority.py:465-509` 和当前审计
   `docs/reviews/2026-09-14-course-name-authority-audit.md` 一致。
3. `Dalian Blue Ocean Golf Club` 的“蓝海”只是中文搜索词命中了英文 provider
   行，不能据此生成“蓝海高尔夫”；还要用坐标/global ID 区分加拿大同名行。
4. 如果产品必须中文，增加明确的用户/运营翻译层，字段命名应是
   `displayAlias`/`translationSource=manual`，不可伪装成 Garmin 原生字段；并在 UI
   同时保留 provider 原名与来源，避免把同名或错配 global ID 合并。

## Handoff

- 模式：只读调查；未修改产品代码。
- 代码来源：canonical checkout `integration/v2`，仅做静态读取；没有创建 review snapshot。
- 远程资源：homeserver 仅发出匿名 CourseView/Connect GET 并写入上述持久证据目录；未创建容器、卷、端口、隧道、服务、依赖或缓存。
- 证据目录为项目持久数据，保留期由项目数据策略管理；本调查没有待清理的临时资源。
- 交付物：本报告 + homeserver 原始 protobuf/JSON、响应摘要和 SHA-256 清单；无 commit、无 patch。
