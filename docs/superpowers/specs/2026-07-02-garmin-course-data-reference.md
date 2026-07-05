# Garmin CourseView 球场数据 —— 完整格式与说明参考手册

> 版本 2026-07-02 · 作者 Fable(只读研究,证据取自真实代码+真实数据,非文档自述)
> 代码基线:主 repo `integration/v2`,根目录 `/home/ubuntu/claude-web-data/repo/garmin-ai-caddie`
> 所有"样本值"均为在本机实测/解码得到,不是猜测。

---

## 0. 数据链总览(4 层怎么串起来)

我们从 Garmin CN 的 **CourseView / prodgeometry / birdseye** 服务下载数据。定位一切的主键是
**`globalId`(gid)** —— 一个 9 洞球场(nine)的全局 ID。gid 从我们自己的记分卡里来
(`scorecard.frontNineGlobalCourseId` / `backNineGlobalCourseId`,见
`ai_caddie/courses/course_reference.py:_rounds_from_files`),也可用名字反查
(D 层搜索端点)。

```
记分卡 scorecard  ──►  globalId (gid)  ──►  释放层 (Release)
                                               │  data/courseview/<gid>_releases.pb
                                               │  匿名 GET .../course-layouts/<gid>/releases/
                                               │
   ┌───────────────────────────────────────────┼───────────────────────────────────────┐
   │ f7.raster_url (每洞)                        │ f7.geometry_url (每洞)                  │ f3.release_id
   ▼                                             ▼                                        ▼
 B1. 官方 3D 俯视 raster                      B. prodgeometry.zip (加密)              C. coursedata IMG
 birdseye.garmin.cn/.../raster3d/2000/...     securemaps.garmin.cn/.../prodgeometry/  .../coursedata/images/
 1242×1920 JPEG                               解密→ HoleNN_<ver>/                     <release_id>/courses/<gid>
 (精绘,带树影/水/条纹)                          ├ hole.json      元数据+高程+路线        内嵌 DSKIMG(TRE/RGN/LBL/DEM)
                                              ├ foliage.json   树/石实例
                                              ├ Terrain.webp   法线贴图(1024²)
                                              └ *.drc          23 种 Draco 网格层

 D. 搜索端点(反查 gid): 匿名 GET .../CourseViewData/courses?CourseName=<名字> → f7=gid
```

**四层怎么指向下一层:**
- **A 释放层** 是入口。它的 **`geometry_url`** 指向 B(加密 zip),**`raster_url`** 指向 B1(官方图),
  **`release_id`** 拼进 C 的 coursedata URL。
- **A → B 的解密**:zip 用密码保护,密码由 app token 流程派生(`fetch_courseview_geometry_key.js`,
  AES-CBC/SHA-256 + 固定后缀 `d802989a-...`),不是暴力破解。
- **B 的坐标系**:hole.json 的 `RefLat/RefLon` 是投影原点;网格顶点是**以此为原点的本地米制 3D**
  `[x, y, z]`,`y=高程`。2D 地图统一取 `(-x, z)`(`hole_render._local`)。
- **端点全部匿名**(A、B1、D 无需 cookie;只有 B 的解密 zip 需要登录态 token)。

**下载脚本索引:**
| 用途 | 脚本 |
|---|---|
| 批量拉 release + IMG | `tools/courseview/fetch_courseview.py`(`fetch_courseview.py` 根目录同名旧版) |
| 解析 release protobuf | `ai_caddie/geometry/inspect_courseview_release.py` |
| 派生 zip 密码 + 解压 | `ai_caddie/geometry/fetch_courseview_geometry_key.js` |
| 解码 Draco 网格 | `ai_caddie/geometry/decode_courseview_geometry.js` |
| 批处理整场每洞 | `ai_caddie/geometry/batch_prodgeometry_course.py`(`batch_prodgeometry_course.py`) |
| 名字反查 gid | `ai_caddie/courses/course_search.py` |
| IMG 逆向(搁置) | `tools/courseview/parse_courseview.py` |

---

## A 层 · Release Protobuf `data/courseview/<gid>_releases.pb`

小体积(~数 KB)匿名 protobuf,本机 104 个。解析器
`ai_caddie/geometry/inspect_courseview_release.py:inspect_release`。裸 protobuf,字段按
`(field_no, wire_type)` 手工解。以下为**顶层字段**(在 104 个文件上的出现次数附后)。

### A.1 顶层字段表

| 字段(f,wire) | 类型 | 含义 | 样本值 | 现在用在哪 | 可能用在哪 | 建议 |
|---|---|---|---|---|---|---|
| f1 (varint) | int | course_id (=gid) | `31795` | **在用** `inspect_release` → 校验 | — | 高·保留 |
| f2 (varint) | int | release_version | `266` | **在用** 存 `release_version` | — | 低 |
| f3 (len) | string | release_id | `"006-D2419-44"` | **在用** 拼 C 层 coursedata URL(`fetch_courseview.py:101`) | — | 高·保留 |
| f4 (len) | string | 球场名(英文) | `"The Players Club ~ B"` | **在用** par 记录 `course_name` | — | 高 |
| **f5 (len) ×174** | message repeated | **九洞汇总记录** `{f1:段名, f2:九洞总par, f3:性别}` | `{1:"OUT", 2:36, 3:"MEN"}` | **未用**(解析器完全没读 f5) | 九洞总 par 兜底、"前九/后九"标签(IN/OUT) | 中·易解,3 行代码 |
| f6 (len) ×874 | message repeated | **Tee 定义**(见 A.2) | — | **部分在用**(名/性别/序号) | Slope/Rating(见 A.2) | 高 |
| f7 (len) ×1548 | message repeated | **每洞记录**(见 A.3) | — | **在用** | raster/女士 par | 高 |
| f8 (varint) | 半圆坐标 | 球场纬度(raw,`*360/2²⁴`=度) | `1865648` → 40.03° | 解析存 `course_lat_raw`,**未转换/未用** | 地图定位、天气、时区 | 中 |
| f9 (varint) | 半圆坐标 | 球场经度(raw) | `5433225` → 116.58° | 解析存 `course_lon_raw`,**未用** | 同上 | 中 |
| f10 (varint) | int | = CourseGenVersion | `22` | 存 `unknown_10`,**未用** | 资产版本判定 | 低(已钉死) |
| **f12 (varint) ×81/104** | int | **未定标志**(那个 deferred flag) | `1` | **未用** | 资产/3D 能力位 | 中·见下方 crosstab |

**f12 全量 crosstab(修正 memory 里"≈CGV≥28"的说法 —— 相关但不严格等价):**
```
(CGV, f12): (28,1)=61  (29,1)=17  (22,None)=8  (29,None)=7  (28,None)=4
            (26,None)=3  (26,1)=2  (22,1)=1  (24,None)=1
```
CGV22 也能是 f12=1(2625),故 f12 ≠ "CGV≥28"。语义仍未定,猜测是"新资产格式/3D 能力"位;
观察到 CGV29 的 39293 其 zip 带 `_f1` 后缀(见 B 层),可能与 f12 关联。**建议**:留到下次批量爬场
时和 `_f1` 后缀一起验,低优先。

### A.2 Tee 记录 f6 子字段(repeated,每 tee 一条)

实测:每场约 8 条(Men/Women × Gold/Blue/White/Red)。**当前只解了 f1/f4/f5**
(`inspect_courseview_release.py:95-101`)。

| 子字段(f,wire) | 类型 | 含义 | 样本值 | 现在用在哪 | 可能用在哪 | 建议 |
|---|---|---|---|---|---|---|
| f1 (len) | string | Tee 名/颜色 | `"Blue"` | **在用** tee 列表(`mobile_live.py:379`) | 选 Tee UI | 高 |
| **f2 (varint)** | int | **USGA Slope Rating** | `116`(全场 92–150) | **未用** | 差点换算、W4b 选 Tee | **高·极易** |
| **f3 (fixed32)** | float LE | **Course Rating**(9洞制) | `36.1`(全场 30.1–83.5) | **未用** | 差点换算、难度展示 | **高·极易** |
| f4 (len) | string | 性别 | `"MEN"` | **在用** | — | 高 |
| f5 (varint) | int | 排序序号(对应 hole.json TeeLocations.Sets) | `2` | **在用** | tee 关联 | 高 |

> Slope/Rating 现成:`31795` 的 Gold=Slope121/Rating37.3、Blue=116/36.1、White=109/34.4
> —— 任意球场全 tee 的官方难度数据,只差 2 个字段没解。

### A.3 每洞记录 f7 子字段(repeated,每洞一条)

| 子字段(f,wire) | 类型 | 含义 | 样本值 | 现在用在哪 | 可能用在哪 | 建议 |
|---|---|---|---|---|---|---|
| f1 (varint) | int | 洞号 | `1` | **在用** | — | 高 |
| **f2 (len) repeated** | message | **par 记录** `{f1:par, f2:性别}` | `{1:5, 2:"MEN"}` / `{1:5,2:"WOMEN"}` | **部分在用**:`_nested_field1` **只取第一条(男)** → 女士 par 被丢 | 女子发球台 par | 中 |
| **f3 (len) repeated** | message | **差点记录** `{f1:hcap, f2:性别, f3:"NotSpecified"}` | 男 `{1:17,...}` / 女 `{1:5,...}`(2625 洞2) | **部分在用**:同样只取男 → **女士差点被丢** | 女子难度排序 | 中 |
| f4 (varint) | 半圆坐标 | 洞(果岭)纬度 raw | `1865511`→40.0295°(实测与 hole.json RefLat 吻合) | 解析存 `lat_raw`,**未用** | 无 mesh 时的洞定位 | 低 |
| f5 (varint) | 半圆坐标 | 洞经度 raw | `5432950`→116.576° | 存 `lon_raw`,**未用** | 同上 | 低 |
| f6 (varint) | int | **洞长(米)** | `492`(实测 dogleg 496m ≈ 一致;2625 洞1=354 vs 358m) | **在用** par 估算 `_hole_yardages` | 洞长展示 | 高 |
| **f7 (len)** | string(URL) | **官方 3D 俯视图 URL** | `birdseye.garmin.cn/.../raster3d/2000/gd31500/gid031795/hole01/gid031795_hole01_1_220542.jpg?garmindlm=...` | 解析存 `raster_url`,**产品未用**(仅早期配准验证) | **换掉自绘洞图底图** | **高** |
| **f8 (len)** | string(URL) | **加密几何 zip URL** → B 层 | `securemaps.garmin.cn/.../prodgeometry/2000/gd31500/gid031795/hole01/hole01_220542.zip?garmindlm=...` | **在用** `geometry_sync.py` 下载解密 | — | 高·核心 |

> **女士 par/差点丢失的根因**:`inspect_courseview_release.py:120-122` 用 `_nested_field1(raw)`
> 只返回第一条子消息的 f1;par/hcap 实为按性别 repeated。修法:遍历所有子消息,按 f2 分男女。

---

## B 层 · prodgeometry.zip(解密后 = Garmin app 3D 飞览场景包)

路径 `data/courseview/prodgeometry/<gid>/HoleNN_<version>/`,本机 **1519 个洞已解密**。
每洞是 Garmin Golf app 的**完整 3D 场景资产**:23 种 Draco 网格 + hole.json + foliage.json + Terrain.webp。
解码 `decode_courseview_geometry.js` → 写 `output/prodgeometry/gid<gid>_h<NN>_meshes.json`。

### B.1 网格层(*.drc,Draco 压缩三角网)—— 全 23 种

**坐标系**:每顶点 `[x, y, z]` 本地米制,**y = 高程(米)**。2D 地图取 `(-x, z)`。
**属性**:多数网格 **4 个属性**(POSITION/NORMAL/TEX_COORD/COLOR),PhysicsMesh=3,PlayableBounds=1。
**关键限制**:`decode_courseview_geometry.js:106-124` **只解 POSITION(3 分量)**,法线/UV/顶点色全丢
(丢 UV 导致 Terrain.webp 无法贴回世界坐标)。

渲染顺序 `hole_render.py:ORDER`;障碍检测 `course_prep.route_hazards`(**仅 Lake+Bunker**)。

| 网格层 | corpus 计数 | 含义 | 渲染用? | 障碍用? | 建议 |
|---|---:|---|:---:|:---:|---|
| Rough.drc | 1519 | 长草/整洞背景面 | ✅ | — | 高·保留 |
| Green.drc | 1519 | 果岭 | ✅ | — | 高(+做坡向) |
| Teebox.drc | 1519 | 发球台面 | ✅ | — | 高 |
| **PhysicsMesh.drc** | 1519 | **碰撞地形(覆盖全洞,3 属性)** | — | — | **高·最适合高程/坡度查询** |
| **IslandExt.drc** | 1519 | 地形裙边/岛外扩展面 | — | — | 低 |
| **PlayableBounds.drc** | 1519 | 可打区域框(4 点,y≡0) | 兜底 | — | 低(y=0 可反证他层 y 真实) |
| **VfxGreenA.drc** | 1519 | 果岭特效层 A | — | — | 低 |
| Bunker.drc | 1510 | 沙坑 | ✅ | ✅ | 高 |
| Fringe.drc | 1492 | 果岭裙 | ✅ | — | 高 |
| Fairway.drc | 1470 | 球道(带条纹遮罩) | ✅ | — | 高 |
| TreeArea.drc | 1444 | 树林区面 | ✅ | — | 中 |
| Lake.drc | 1099 | 湖/水域 | ✅ | ✅ | 高 |
| LakeSide.drc | 993 | 湖岸带 | ✅ | — | 中 |
| **Cartpath.drc** | 565 | **球车道** | ✅ | — | 中(可当 OB/硬地参考) |
| **VfxStream.drc** | 97 | 溪流特效 | — | — | 低 |
| **VfxOcean.drc** | 59 | 海洋特效 | — | — | 低 |
| **Ocean.drc** | 59 | **海洋水面** | — | **❌ 漏检** | **中·59 洞海水障碍应纳入** |
| **OceanSide.drc** | 59 | 海岸带 | — | ❌ | 中 |
| **Beach.drc** | 59 | **沙滩** | — | ❌ | 中(等同大沙坑) |
| **Cliff.drc** | 59 | 悬崖 | — | — | 低 |
| **CliffUV2.drc** | 59 | 悬崖(第二 UV 组) | — | — | 低 |
| **Bridge.drc** | 21 | 桥 | — | — | 低 |
| **VfxGreenB.drc** | 11 | 果岭特效层 B | — | — | 低 |

> **障碍检测漏洞**:59 个海滨洞的 Ocean/Beach 完全不进 `route_hazards`(只查 Lake/Bunker)
> → 海水/沙滩水障碍被漏报。

### B.2 hole.json 字段

每洞元数据。**大字段变体 3 种**(1357 洞标准 / 27 洞带 Expanded / 135 洞精简)。
在用:TeeLocations、Doglegs.Line、RefLat/RefLon(`course_prep.py` / `hole_render.py`)。

| 字段 | 类型 | 含义 | 样本值 | 现在用在哪 | 可能用在哪 | 建议 |
|---|---|---|---|---|---|---|
| HoleNumber | int | 洞号 | `1` | **在用** | — | 高 |
| GlobalId | int | gid | `2625` | **在用** | — | 高 |
| Version | int | 资产版本 | `450` | 未用 | — | 低 |
| RefLat / RefLon | float | **投影原点(WGS84)** | `33.948625 / -117.334576` | **在用** 世界↔本地投影(`course_prep._your_shots`) | — | 高·核心 |
| TeeLocations[] | list | 发球台点 `{Sets:[序号], X, Y}` | `{Sets:[6], X:47.4, Y:36}` | **在用** 蓝 tee 起点(`_blue_tee`) | 多 tee 路线 | 高 |
| Doglegs[].Line[] | list | **打球中线(dogleg 折线)** `{X,Y}` | 7 点折线 | **在用** 路线派生(`derive_route`) | — | 高·核心 |
| **ElevationMinimum** | float | **本洞绝对海拔下限(米)** | `304.727` | **未用** | 绝对高程参照 | 中 |
| **ElevationMaximum** | float | 绝对海拔上限(米) | `325.835` | **未用** | 同上 | 中 |
| **ElevationRange** | float | 海拔跨度(米) | `21.108`(山地场达 151.7) | **未用**(但网格 y 已可直接算) | 山地/平地判定 | 中 |
| **DEMProviderId** | int | DEM 数据源 id | `0`(全 corpus 恒 0) | 未用 | 高程来源追溯 | 低 |
| Biome | string | 生物群系(影响配色) | `"Savanna"`(Tropical/Grassland/Savanna/Boreal) | 未用 | 底图配色自适应 | 低 |
| HasOceanFeatures | bool | 有无海洋要素 | `false`(59 洞 true) | 未用 | 触发 Ocean 障碍检测 | 中 |
| **HasTargets** | bool | 有无瞄准目标点 | `true`(1384 洞 true) | 未用 | 官方推荐落点(但资产内**未找到 target 本体**) | 中·待挖 |
| DoglegOrder | string | 狗腿方向 | `"NoOrder"`(LeftRight×11) | 未用 | 左/右狗腿提示 | 低 |
| DrivingRange | bool | 是否练习场 | `false`(全 false) | 未用 | 过滤练习场 | 低 |
| Name | null | 洞名 | `null`(全 null) | 未用 | — | 低 |
| CourseGenVersion | int | 生成器版本 | `22`(22/24/26/28/29) | 未用 | 资产兼容 | 低 |
| **Expanded*(27 洞)** | — | 扩展 DEM 组:`ExpandedElevationMin/Max/Range`+`ExpandedDEMProviderId`;`Expanded30m*`(30m DEM,**ProviderId=1** 疑 SRTM30) | `Expanded30mElevationRange=208.9` | 未用 | 洞外地形/远景高程 | 低 |

### B.3 foliage.json 字段

每项一个植被/石头实例。在用:画树点(`hole_render.py:158-169`,`x/z/s`)。

| 字段 | 类型 | 含义 | 样本值 | 现在用在哪 | 可能用在哪 | 建议 |
|---|---|---|---|---|---|---|
| foliage[] | list | 小植被实例(草丛等) | 6120 条(id=5 最多) | **在用**(每 3 个画 1 点) | — | 中 |
| trees[] | list | 乔木实例 | id=2 最多 | **在用**(画树+阴影) | — | 中 |
| rocks[] | list | 石头实例 | **全空** | 未用 | — | 低 |
| ├ x, z | float | 本地平面坐标(米) | `-100.479, 22.619` | **在用** | — | 高 |
| ├ y | float | **高程(米)** | `8.57` | 未用(画 2D 忽略) | 3D 场景 | 低 |
| ├ s | float | 缩放/大小 | `0.8` | **在用**(树冠半径) | — | 中 |
| ├ qx/qy/qz/qw | float | **朝向四元数** | `-0.076/-0.191/-0.016/-0.979` | 未用 | 3D 摆放 | 低 |
| └ id | int | 模型/树种 id | `4001`(树种 2/3/5…) | 未用 | 按树种配色 | 低 |

### B.4 Terrain.webp

| 项 | 值/说明 |
|---|---|
| 类型 | **切线空间法线贴图**(1024×1024 RGB,肉眼确认蓝紫色主调=法线编码,非照片) |
| 用途(Garmin) | 3D 地形光照/坡向着色 |
| 现在用在哪 | **未用** |
| 可能用在哪 | 逐纹素坡向 → 精细坡度可视化(但需网格 UV 才能贴回世界坐标,而 UV 被解码器丢了) |
| 建议 | 低(需先解 TEX_COORD 属性;收益边际) |

### B.5 zip 命名 / 版本后缀

- 目录 `HoleNN_<version>`,version 如 `220450`、`280630`、`290671`。
- **`_f1` 后缀**(如 39293 的 `Hole09_290671_f1`):仅见于 CGV29 少数场,资产集与常规一致但**多带 Cartpath**,
  疑与 A 层 f12 flag 关联,待验。

---

## C 层 · coursedata IMG(内嵌 Garmin DSKIMG + DEM)

匿名端点 `.../CourseViewData/coursedata/images/<release_id>/courses/<gid>`,返回 ~30–60KB protobuf,
**field 3 = 内嵌 Garmin `.img`(DSKIMG)**。下载脚本 `tools/courseview/fetch_courseview.py`。
**本机当前 data 目录无 .img 文件**(历史逆向产物),逆向解析器 `tools/courseview/parse_courseview.py`(704 行)。

| 子文件/字段 | 类型 | 含义 | 样本/证据 | 现在用在哪 | 可能用在哪 | 建议 |
|---|---|---|---|---|---|---|
| coursedata.pb field 1 | message | release 元数据 | — | 未用 | — | 低 |
| coursedata.pb field 3 | bytes | **内嵌 DSKIMG** | `IMG_RESEARCH.md:36-43` | 未用(逆向搁置) | — | 低 |
| IMG → TRE | 子文件 | 树/头/扩展类型表 | 偏移 `0x00f0` | 逆向解过多边形/线/点 | 粗矢量图层 | 低 |
| IMG → RGN | 子文件 | 几何区块 | `0x026f` | 部分解 | — | 低 |
| IMG → LBL | 子文件 | 标签 | `0x03e4` | 未解 | 点标签/名称 | 低 |
| **IMG → DEM** | 子文件 | **数字高程模型** | 偏移 `0x068d` | **完全未碰** | 第二高程源(冗余,B 层已够) | 低 |
| 扩展多边形类型码 | hex | 球道/果岭/沙坑/水的私有类型 | `0x011407` 等(语义未定) | 逆向未定 | — | 低 |

> **结论**:C 层是搁置的逆向线程。其 DEM 是**冗余的**——B 层网格 y 已直接给高程,不必再啃 IMG DEM。
> `IMG_RESEARCH.md:236-253` 的实践结论也是:精细几何用 prodgeometry,IMG 仅粗上下文。**整层低优先。**

---

## D 层 · 搜索端点(名字反查 gid)

匿名 `GET .../CourseViewData/courses?CourseName=<名字>`(≥3 ASCII 或 ≥2 CJK)。返回 protobuf,
**顶层 field 4 repeated = 每个球场记录**。解析器 `ai_caddie/courses/course_search.py:parse_course_search`。

| 子字段(f) | 类型 | 含义 | 样本 | 现在用在哪 | 可能用在哪 | 建议 |
|---|---|---|---|---|---|---|
| f7 (varint) | int | **globalId** | gid | **在用** 反查 | — | 高 |
| f12 (len) | string | 球场名 | 名字 | **在用** 模糊匹配 | — | 高 |
| f13 (varint) | int | 洞数(9/18) | `9` | **在用** guard 过滤 | — | 高 |
| f16 (len) | string | 省 | 省名 | **在用** 地点 guard | — | 中 |
| f21 (len) | string | 市 | 市名 | **在用** 地点 guard | — | 中 |
| 其余子字段 | — | 坐标/国家等 | — | 未用 | 低价值 | 低 |

---

## 机会清单(按性价比排序)

| # | 机会 | 所需字段 | 难度 | 收益 |
|---|---|---|:---:|---|
| 1 | **官方 raster 当洞图底图** —— 用 A.3 `raster_url` 的 1242×1920 精绘图替换/叠加自绘洞图。与 mesh 坐标系已验证像素级对齐(早期配准残差 <0.6px),匿名下载,~130KB/洞可离线缓存 | `f7.raster_url` | **低** | **高**:观感一步对标 Garmin app |
| 2 | **解析 Tee Slope/Course Rating** —— `inspect_courseview_release` 加解 tee f2(Slope 92–150)、f3(Rating 30.1–83.5,fixed32 float) | `f6.tee.f2/f3` | **极低** | **高**:差点换算 + W4b 选 Tee 的数据地基 |
| 3 | **补女士 par/差点** —— 把 `_nested_field1` 改成按性别遍历 par(f2)/hcap(f3)的 repeated 子消息 | `f7.par/hcap` repeated | **低** | 中:女子发球台正确性 |
| 4 | **PlaysLike 坡度补偿(已落地,可扩范围)** —— B.1 网格 y=高程已被 `ai_caddie/geometry/elevation.py` 用上,tee→green Δ 实测 −31~+27yd。可扩到"球位→果岭"实时 Δ | 网格 y | 已有 | **高**:选杆级影响,已在 iOS 消费 |
| 5 | **海滨水障碍补漏** —— `route_hazards` 纳入 Ocean/Beach(59 洞)+ 可选 Cartpath/Bridge | `Ocean/Beach/Ocean*.drc` | 低 | 中:59 洞正确性 |
| 6 | **果岭宏观坡向** —— Green.drc 逐顶点 y(单果岭 ~196 顶点/28×33.5m,高差 ~0.69m)做倾向箭头/前后台阶(做不了推杆级微等高线) | `Green.drc` y | 中 | 中:调旗/攻果岭屏 |
| 7 | **九洞总 par 兜底 + IN/OUT 标签** —— 解 A 层 f5 | `f5` | 低 | 低:par 阶梯已很全 |
| 8 | **球场经纬度落地** —— f8/f9 半圆坐标 `*360/2²⁴` → 地图/天气/时区 | `f8/f9` | 低 | 低 |
| 9 | **f12 flag 定义 + `_f1` 后缀** —— 下次批量爬场时一起验(crosstab 已修正:≠"CGV≥28") | `f12` | 中 | 低 |
| 10 | **HasTargets 目标点挖掘** —— 1384 洞标 true 但资产内未见 target 本体,查是否有独立 targets 端点 | `HasTargets` + 未知端点 | 高 | 中(不确定) |
| 11 | **IMG/DEM 逆向** —— 搁置;B 层已提供高程,冗余 | C 层全部 | 高 | 低 |
| 12 | **解码器补属性** —— decode 脚本加 NORMAL/TEX_COORD/COLOR(现只解 POSITION),UV 才能贴 Terrain.webp | Draco 4 属性 | 中 | 低 |
