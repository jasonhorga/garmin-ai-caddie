# 选发球台 设计(2026-07-07)

> **目标**:开一局(或备战)时能选从哪个发球台开球(黑/蓝/白/金/红…),选了之后**距离、难度、球童建议都按那个台算**。这是 Garmin"开新球局"就有的基本功能。
>
> **关键前提(好消息)**:后端**基本已经支持**了——
> - `ai_caddie/caddie/analysis._selected_tee(geometry, tee_box)`:按台名(black/blue/white/gold/yellow/red → set 号,`TEE_SET_BY_BOX`)选台,默认取最长台;
> - `mobile_live._courseview_tee_names(global_id)`:从 CourseView 拿到这球场的台颜色名(金/黑/蓝/白/红,就是 Garmin 选台列表);
> - `tee_box` 参数**已经从端点(`server_v2/main.py`、`mobile.py`)一路穿到球童**(mobile_live 多处);
> - 各台的实际码数在 `output/prodgeometry/gid*_h*_tee_distances.json`(每台一个 `target_distance_m` + 障碍距离)。
> - 现在的默认是写死 blue(`decision_api` `teeBox="blue"`)。
>
> **所以这件事不是大改,是把"用户选的台"接上去 + 给个选台界面。**

## 要做的三块

### 1. 后端:一个"这球场有哪些台"的列表接口
`GET /api/v2/courses/{globalId}/tees` → 返回该球场可选的台:每个台的 **颜色名**(`_courseview_tee_names`)+ **总码数**(把该 gid 各洞 `tee_distances` 里对应 set 的 `target_distance_m` 求和,换算成码)+ set 号。缺 CourseView 名时退化成"长/中/短台"。**默认台** = 当前默认(blue,若无则最长)。诚实:拿不到码数的台只给名、码数留空。

### 2. 客户端:开局选台界面
- **iOS `StartRoundView`**:在现有"起始9洞"分段旁,加一个**发球台**分段/选择器(照 `nine` 那套 UI),选项来自接口 1,默认高亮默认台。选择随 `StartRoundView → app model → SyncClient` 穿成 `tee_box`(镜像 `nine` 的穿法)。
- **Web**:备战/开局处同样一个选台下拉(选项来自接口 1),选择带进 prep/caddie 请求的 `tee_box`。
- **中途可改**:像 `nine` 那样,改台 = 用新 `tee_box` 重取(零后端改,后端已支持)。

### 3. 把选择穿进现有调用
prep/caddie 的前端调用带上 `tee_box`(端点已收)。球局记住这个选择(镜像 `nine` 的持久化)。

## 边界 / 默认(YAGNI)
- **MVP**:选台 → 距离/难度/球童按台算(后端已支持)。
- **不做**:自定义台、每洞不同台、女子/男子台区分(先只 MEN,`_courseview_tee_names` 已默认 MEN)。
- **默认台**:blue(现状),无 blue 取最长——不逼用户选。
- **不造假**:某台没码数就只显示名、码数留空,不编。

## 验证
- 后端接口 1:`unittest`(CI 权威,Tokyo 预验)——给定 gid 返回台名+码数,缺数据退化。
- Web:vitest + 截图(可现在验)。
- iOS:native-mobile 编译 + 快照(真选台手感要 TestFlight,已搁置)。
- 契约:`test_mobile_contracts` 断言 StartRoundView 有选台控件 + `tee_box` 穿进链路。

## 关联
- 参照 `nine` 选九洞的端到端穿法(已上线)。
- 后端台机制:`ai_caddie/caddie/analysis._selected_tee` / `mobile_live._courseview_tee_names` / `TEE_SET_BY_BOX`。
- 手表重做里也有个选台屏设计(`WatchTeeSelectView`,蓝/白/金/红 + 码数),将来手表整合时复用同一份台列表。
