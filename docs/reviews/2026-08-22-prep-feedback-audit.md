# 2026-08-22 备战反馈回归审计

范围：上一轮关于 Half Moon Bay 备战体验的六组反馈。这里区分“代码已经有对应机制”和“真实端到端已经证明可用”，不把单元测试当成产品验收。

## 结论

Half Moon Bay 的两场 Garmin 同步本身没有问题。本审计针对的是备战下载、球杆、策略、障碍物、地图加载和球场搜索，不改变同步结论。

| 反馈 | 当前判断 | 证据与缺口 |
|---|---|---|
| 下载慢、离开页面后继续下载 | **部分修复** | iOS 已有持久 `PrepCourseDownloadRecord`、进度保存、重新进入恢复和下载库条目；`OfflineStore` 保留未完成意图。进入后台使用的是 `UIApplication.beginBackgroundTask`，只是系统授予的短暂 grace period，不是可持续的后台下载。服务端 course-install 仍是单 worker，不能宣称“已达到 Garmin 速度”。 |
| 3W/3H 杆距不正确 | **代码路径已补，真实数据未验收** | `club_ladder` 现在按 Garmin `adviceDistance` > `averageDistance` > AutoShot 中位数 > 默认值，并按真实球包过滤；已有对应测试。当前没有拿 Half Moon Bay 备战的生产响应逐杆核对 3W/3H 的最终显示值，因此不能宣称用户看到的问题已解决。 |
| Par 4/5 出现“一号木接一号木”，推荐应稳妥优先 | **第一处 bug 修复，策略设计仍未完成** | `_strategy` 已把 driver 从第二杆候选中排除，Par 5 会生成多步链。可是 `_candidate_routes` 仍把 `stock` 与 `attack` 都设为最长杆，且没有基于稳定性、风险和期望杆数排序；这不等于“稳妥优先”的 S70 式策略。 |
| 沙坑显示成沙坑 1、沙坑 2 | **地图 overlay 已补，仍需真实截图验收** | iOS/Web 已使用障碍边界点并显示 `到/过`，且只展示前两个未通过障碍；后端也把重复的果岭边沙坑提醒合并。Watch/旧数据的 legacy fallback 仍可能回到序号标签，需用真实球洞检查。 |
| Half Moon Bay 地图加载很慢 | **性能有缓解，未证明达标** | 服务端有 prep fingerprint/LRU/single-flight cache、topo prewarm；iOS 有 revision-keyed 本地 PNG 缓存。Web 仍在首次拿到 CourseView partial 数据后进入工作台并异步 prewarm，冷启动仍可能等待。没有本轮真实 18 洞耗时基线，不能称为已解决。 |
| 附近球场、城市+关键字搜索、清理搜索交互 | **iOS 已补，Web 未统一** | iOS `MobileCourseSearchView` 有附近按钮、半径选择、城市/关键字两栏和持久下载行；服务端有 nearby endpoint。Web `CourseFinder`/`PrepPage` 仍只有单一球场关键字输入，并保留常打球场卡片，没有附近入口或城市字段。三端统一尚未完成。 |

## 明确未修好的两项

1. **Web 仍违反“不下载完不进入备战”**：`PrepPage` 在收到 `partial` CourseView 后直接渲染 `PrepWorkbench`，并启动 `prewarmCourseTopo`；`PrepHoleCanvas` 还保留 fallback/示意图路径。iOS 的 `CourseReviewView` 已经做了完整本地包 gate，但 Web 没有同等 gate。
2. **真正后台下载和速度仍未闭环**：iOS 的 background task 到期后只是把记录退回 `queued`，下次前台恢复；这保证不丢状态，但不保证在用户离开后继续完成。服务端单 worker 是稳定性选择，不是速度优化。

## 可以复用的实现

- `OfflineStore.savePrepCourseDownloads/loadPrepCourseDownloads`：持久化下载意图和进度。
- `course_install`：服务端可恢复、幂等、按洞记录 geometry/topo 状态。
- `prep_cache`：课程准备事实的 fingerprint cache 和 single-flight。
- `course_search.courseview_nearby`：已有 Garmin 半径查询、分页、距离排序和短期缓存。
- `club_ladder` / `garmin_distance_m`：已有真实球包和 AutoShot 的分层来源规则。

## 下一步应按这个顺序收口

1. 先给 Web 加与 iOS 相同的完整包 readiness gate，移除进入备战前的 fallback/partial 工作台路径。
2. 为 3W、3H、Driver 在真实 Half Moon Bay 响应上做一张“Garmin 原值 → 后端梯子 → iOS/Web 显示”的证据表。
3. 把策略输出改成真正的 `稳妥 → 标准 → 进攻` 三条可解释路线，禁止只换一个最长球杆冒充三种方案。
4. 再决定是否采用 `URLSession` background configuration / BGProcessingTask；在此之前不要把 `beginBackgroundTask` 称作后台持续下载。
5. Web 与 iOS 共用附近/城市/关键字搜索契约，并用一套真实球场 UI 测试验收。

## 本轮验证边界

- Homeserver 的同步切片 Python 测试：相关 pipeline 测试 14 项通过。
- API 状态测试在远端 `ci-venv` 因缺少 Pillow 无法导入完整服务，未把它伪报成通过。
- 当前环境没有 Xcode，因此没有声明 iOS 编译、模拟器截图或 TestFlight 验收。
