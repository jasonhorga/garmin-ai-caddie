# Apple Watch 高尔夫体验 — 设计 Spec (2026-06-22)

> 设计稿(真数据 + 可交互意图):完整流程 served at the funnel `https://caddie.taile36706.ts.net/flow_all.png`。
> 对标 Garmin Approach S70 的打球范式 + 我们的 **AI 球童**差异点。
> **状态(2026-07-02):设计已落地为 ~20 屏 SwiftUI 设计快照**(真实球洞几何 + macOS CI `ImageRenderer` 验证),branch `superpowers/watch-holeview-redesign`(PR #218)。**design-only —— 尚未接入 app 真导航 + 实时数据**;下一步 = **集成 → TestFlight**。逐屏与整改细节见文末「§ 实现状态」。
> 关联:`watch-golf-redesign`、`r13-product-redesign`、`auto-shot-tracking-vision` (memory)。

## 定位
Apple Watch = 打球当下的腕上设备:**地图为底、信息悬浮、流程化**。核心差异 = AI 球童(推荐杆 + 打法 + 预期杆数,**不给成功率**)。单位**全用码**。深色。

## 交互模型(按 Apple HIG — 关键:Apple Watch 没有上下硬件键)
- **数码表冠 转** = 每屏不同功能:home=地图缩放 · 球童=切激进/保守 · 障碍=逐个切 · 选杆=滚动调杆 · 记分=±分 · 选洞=换洞 · 计分卡/菜单=滚动。
- **数码表冠 按** = 系统回表盘(不占用)。**侧边键** = 系统(Control Center/SOS/Pay,不可改)。**Action 键(仅 Ultra)** = 可选快捷:记杆/下一洞。
- **触摸**:点(选中/点果岭→调旗/点球童条→打法)· **左右滑**(切并列视图)· **左缘右滑 = 返回**(所有子屏都支持)· **长按地图 = 打开菜单**(一个入口)· **点地图 = 直接选障碍**(不进二级菜单)。

## 屏幕清单
1. **球道图 home**:底图=完整球洞俯视图;悬浮 后/中(大橙)/前果岭距离、**距上一杆实时距离**、**坡度补偿 ±码**、球童一行;**18 洞环贴圆角矩形屏幕边缘**(1号洞上中起、顺时针、首尾留缺口、洞号+成绩颜色、当前洞高亮),环只在此屏。表冠=缩放。
2. **AI 球童打法**:激进/推荐/保守(表冠切),推荐杆 + 打法 + 避开 + 预期杆数 + 坡度。无成功率。
3. **靠近果岭**:果岭放大(仍是球道图);点果岭进 4。
4. **果岭调旗**:果岭特写 + 可拖红旗 → 到旗距离实时更新(本轮保存)+ 到旗坡度。近果岭自动弹 / 也可从菜单进。
5. **障碍 Hazard View**:整张球道图上**高亮当前障碍**,**转表冠逐个切**,显示 落前/越过(前沿/后沿)距离。点地图直接进。
6. **AutoShot 记杆**:检测到挥杆→**立即进选杆**(表冠滚轮,默认=上一杆推荐杆,确认即用;无"更多"、无取消)→ 上一杆码 + 下次击球自动记两点轨迹 → 回球道图。可补/改上一杆。
7. **记分序列**:杆数 → 推杆 → **罚杆(保留选择)** → **击球方位**(偏左/球道中央/偏右,**按落点 GPS 自动默认**、可改);连续自动跳转;内容居中、保存为小按钮;随时 Back 不保存。**离开果岭(geofence)才自动弹**,非推球入洞即弹。
8. **选洞**:独立屏(1–18 格 / 表冠换洞)。
9. **计分卡**:**逐洞列表**(洞·Par·成绩,按 par 着色),点某洞直接改该洞 杆/推(对标 S70)。
10. **菜单(hub)**:长按地图进;纯文字无图标;项=球童打法/调旗·放大果岭/选洞/计分卡·调分/障碍·自定义目标/本场成绩/球杆距离/设置/结束本场(对标 S70 14 项)。
11. **开始/结束**:开始=按定位列附近球场;恢复进行中的局;结束小结(总杆/球道/GIR,后台算)。

## 数据 / 可行性(已核 repo)
- **GIR / 开球左中右 / 每杆 lat-lon-lie 已在 Garmin 原始数据**(`ai_caddie/connectors/snapshot.py`),只是统计 pipeline 没透出 → 后端接出来即可;`WatchRoundState` 需扩这些字段。
- **坡度补偿(PlaysLike)用现有数据就能做,无需 DEM**(2026-06-22 纠正之前"需 DEM"的结论):Garmin prodgeometry 网格 `positions` 是 **3D 米制**,第二维 y = 高程(实测样本 `[-70.07, 1.15, 335.98]`,y 在洞内有起伏)。我们一直只投影 x/z 当 2D 地图、丢了 y。PlaysLike = green 网格高程 − 球位网格高程 → ±码。**与地图/障碍同一份数据、同一"几何 ready"门控**。限制:相对米(算高差够用)、精度/幅度按球场验(平场起伏小)。`hole_render._local`/`course_prep._local` = `(-p[0], p[2])` 已证 p[1] 是高程轴。
- **球洞地图后端已有** `/api/v2/geometry/hole/.../map`;**几何覆盖 ready/partial/missing** 是 gating → 无几何洞优雅降级(只记分 + 球童文字距离)。
- **AI 球童引擎够用**(`ai_caddie/decision.py` 出 球杆+预期杆数;无成功率,要做需新校准模型)。
- **球杆数据需清洗**(Unknown 14864、PW/Pw 大小写重复、低样本离群)。
- **AutoShot 在 Apple Watch 可行**(竞品 Golfshot/Roundabout 已用 watchOS 10 高频运动 API + GPS + HealthKit workout);难点=误报+续航,可调。当前手表无 HealthKit/CoreMotion/CoreLocation,是新传感器活。

## 落地排期(MVP → 完整)
1. 扩 watch state(码/前中后/全18汇总/几何覆盖)+ 后端透出 GIR/球道/每杆位置 + map API 给表。
2. HOME(球道图+距离+环)+ 记分序列 + 球童卡。
3. 障碍/layup(几何 ready 时,缺则降级)。
4. 计分卡列表 + 选洞。
5. 果岭调旗 + 触摸测距(拖目标)。
6. **坡度补偿(用现有 prodgeometry 网格高程 y 轴,无需 DEM;随几何档做)** — hole-map-v2 契约里加 elevation/PlaysLike 字段。
7. AutoShot(HealthKit workout + CoreMotion 挥杆检测 + CoreLocation + 误报/续航调优)。
- 全程走 native-mobile CI + design-snapshot 自验(见 `auto-shot-tracking-vision` memory 的快照流水线)。

## 去掉(明确不做 / 暂不做)
成功率(无引擎数据,需校准)· 风(场上难估)· 果岭坡度等高线(只留 ±码坡度补偿)· **大字距离速览页(2026-07-02 用户定:与洞视图 后/中/前 重复,砍)**。

---

## § 实现状态(2026-06-30 ~ 07-02:design-only,已落地为 SwiftUI 快照)

**已建:~20 屏 SwiftUI 设计快照**,branch `superpowers/watch-holeview-redesign`(PR #218)。真实球洞几何(后端 `hole_render` 烘焙图 gid31669 h4,base64 baked 进 `WatchHoleMapSampleImage.swift`;`WatchMapDraw.drawInto` 把图画进任意 `Canvas` 并返回 img-px→canvas 变换供叠加)。**每屏经 macOS CI `ImageRenderer` 渲成 PNG(`WatchDesignSnapshotTests`)→ 采集 `watch-snapshots` artifact → 拼图 served 到 funnel** 逐屏肉眼核对。**不需要真机/TestFlight 就能验 UI 保真度**。

**屏幕(对应上文清单,均已出图验证)**:选球场 / 打几洞(9·18)/ 哪个9 / 发球台 / 球局主页(hub)/ 高球菜单 / **洞视图**(左数据列+右真图,后中前果岭·球童条·距上一杆·18洞环)/ Zoom(表冠缩放)/ 球童打法(左右滑切打法)/ **果岭**(定心十字准星+拖地图,前沿/中/后沿)/ **障碍**(沿打球线求交点,进/过)/ **选点测距**(定心拖地图:你→点+点→果岭)/ PinPointer / 记分(杆·推·球道·罚)/ 积分卡(转冠滚动)/ 选洞(3列≥44pt 大格转冠滚)/ 球杆数据 / 本洞击球 / 结束球局。

**用户驱动的关键整改(2026-07-02)**:
- **地图提亮加饱和**(PIL 对烘焙图 Color×1.42/Bright×1.12/Contrast×1.16,不动后端)→ 鲜绿高对比,对齐 Garmin。
- **障碍/果岭 = 前沿+后沿距离,不是中心**:障碍从**当前位置沿瞄准方向画射线、与真沙坑求交**得 进(会进)/过(能过)两点(射线逐像素扫真沙像素定位;排除 cart-path 米色污染);果岭补 前沿/后沿(真 front/center/back=273/287/300)。
- **果岭/测距 = 定心十字准星 + 拖地图**(旗/准星固定屏幕中心,拖地图对准;避免手指遮挡,Gemini/HIG,用户定),不是拖旗桿。
- **交互按 watchOS**:表冠缩放/滚动(右缘轨道指示,非 +/−)· 左右滑翻屏(分页圆点,非小箭头)· 列表转冠滚动(不平铺)。
- **距上一杆**距离补进洞视图。**PinPointer 箭头从圆心发出 + 调大**。**地图上所有数字套黑底不透明药丸**(户外对比度)。**大字速览页砍掉**。
- **双 AI 复审(GPT-5.5 xhigh + Gemini 3.1-pro,homeserver)** 收敛驱动:药丸对比度 / 障碍可读 / 触控≥44pt / 环只在洞视图。

**未做 = 下一步「集成」**:接进 app 真导航 + 实时 `WatchRoundState`/后端数据;传感器活(AutoShot 挥杆检测 / GPS 测距 / HealthKit workout)—— **快照测不了传感器/GPS,须 TestFlight + 球场实测**(见 §8.2)。集成后按上文「落地排期」推进。
