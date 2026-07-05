# AI Caddie · 总 Spec(唯一真源)

> 这是**唯一的、活的**产品 Spec,**就地维护**。每次改动记进下方「改动日志」,并维护「TODO」。
> 之前散落的日期文档保留作**深挖附录**(见文末「详细附录」),本文是它们的总纲 + 现状 + 日志 + 待办。
>
> **大原则(负责人 2026-07-05):数据/准备层在后端做一次,Web/iOS/手表都直接复用;组件可复用;开局时后端统一预加载。不要一端一端修。**

---

## 1. 产品与三端分工

AI Caddie — 高尔夫 AI 球童,对标 Garmin S70 范式,AI 球童做差异;**零成功率/零百分比、全码、简体中文、离线优先、不造假数据**。名字 **AI Caddie**,不显示个人名。

| 端 | 定位 | 视觉 |
|---|---|---|
| **Apple Watch** | 打球主力(原点) | 暗色图形化、大数字、地图 |
| **iOS** | 场上控制台 + 纯手机整场 | **打球屏暗色图形化**(贴手表);**其余(首页/复盘/备战/统计/球包/设置)浅色 iOS 原生** |
| **Web** | 复盘 / 备战 / 统计 / 球包(不打实时局) | 桌面工作台、亮色、暗色导航栏 |

**北极星**:手表是原点 · 打球暗·复盘亮 · 数字是主角 · 同物同形 · Garmin 语法+Apple 语感。

## 2. 设计系统(详见 §附录 design-system)

- **色彩**:品牌/动作绿白名单三处;**to-par 成绩色 = 赤橙黄绿青蓝紫,Par 绿**,+ 圈/方/三角形状冗余(色盲);双面双值 hex;course palette 一套三端共享。
- **洞图渲染标准(锁定)= 精致写实 topo(自绘)**:填满整幅(0.64 竖幅、洞居中)、太阳 SE/影 NW、无 AO、干净割草亮带、物种树、果岭目标环 + 旗、只画本洞连通水、超采样细描边;**不烘打球线/码数/tee**(那是矢量叠加层)。原型 `assets/hole-render-topo-prototype.py`,生产 `ai_caddie/geometry/topo_render.py`。

## 3. 架构(详见 §附录 unified-spec 附录 C)

- **服务器 = 唯一真源 + 唯一位图渲染器**:预渲成品 topo 位图(缓存)+ 客户端叠薄矢量层(路线/落点/距离/球)。**手表永不渲 3D**。Web 大屏可 WebGL。
- **数据/准备层后端做一次、三端复用**:洞图渲染+缓存+预热、球杆解析、shot-map 数据 —— 后端产出,Web/iOS/手表直接消费;**开局(round-start)后端统一预加载**。
- 授权红线:Garmin 官方 raster 签名 ≠ 商用,产品底图用自绘 topo。
- 存储非约束(几万球场 ~100–175GB);选场/开局预取离线包。

## 4. 现状(2026-07-05)

- **Web 全套重做 + 真 topo 球道图**:已上真站 `/me`。
- **iOS 全主屏重皮**:打球暗 + 其余浅,进 integration/v2(TestFlight 门控)。
- **topo 渲染管线**:端点 `GET /api/v2/courses/{gid}/holes/{hole}/topo.png`(渲一次缓存)+ `POST …/topo/prewarm`,三端球道图拉真图。
- 正在修**两个共享层 bug**:topo 只填 ~35%(取景)+ 复盘球杆解析不到(clubId 对不上球包)。见 TODO。

---

## 5. 改动日志(按合并顺序)

| PR / commit | 面 | 改动 | 状态 |
|---|---|---|---|
| `9c1e93d` `501ef20` | spec | 锁定洞图渲染标准(§九)+ Q1–Q5 三模型对抗结论;归档原型 | 合并 |
| #220 | Web | P1 外壳:导航 复盘/备战/统计/球包/设置 + 暗栏 + tokens | 合并·部署 |
| #222 | Web | P2 备战工作台(接真实 course-prep) | 合并·部署 |
| #223 | Web | P3 复盘工作台(落点图 + 杆序 + 决策vs实际) | 合并·部署 |
| #224 | Web | P4 统计仪表盘(无假 SG,真实各环节失杆) | 合并·部署 |
| #225 | Web | P5 球包(gapping + 可编辑,与 iOS 同一 profile) | 合并·部署 |
| #227 | Web | 收尾:球场图隐藏/条按比例/手机标签不竖排 | 合并·部署 |
| #231 | Web | 横向记分条选洞 + 即时占位→topo 淡入 + prewarm + 预取 | 合并·部署 |
| #221 | iOS | 打球/记分屏**暗色**图形化重做 | 合并 |
| #226 | iOS | 首页/复盘**浅色** iOS 原生 | 合并 |
| #228 | iOS | 备战/统计/球包**浅色**重皮 | 合并 |
| #229 | 后端+Web | topo 渲染管线(任意洞 + 端点 + 缓存 + Web canvas 拉真图) | 合并·部署 |
| #230 | iOS | 三处洞图接 topo 端点 + 兜底 | 合并 |
| `62db4cc` | spec | 建本总 Spec(合并原 changelog) | — |

**部署**:homeserver `/me`,绿了自动部署(web build +(后端改动)`docker compose build api && up -d api`)。iOS 走 TestFlight(门控,未发)。

---

## 6. TODO

### 进行中
- [ ] **后端共享层**(PR `shared-topo-frame-club`):topo 图+矢量叠加共用「填满整幅」投影(现~35%)· 后端 clubId/clubTypeId→球包真实杆名稳健解析

### 下一步(吃后端这层)
- [ ] 各端 shot-map:落点线**加粗** + 每个落点**标球杆**(参考 Garmin,不写距离/位置)· Web + iOS
- [ ] **开局统一预热**:round-start 后端渲+缓存整场(iOS/手表也预加载);继续提速

### 尾巴
- [ ] iOS 球包做 gapping 阶梯图(现为浅色球杆列表)
- [ ] topo 底部 tee 端小缺口(装饰)

### 门控(等负责人明说)
- [ ] TestFlight · integration/v2→main · 手表重做整合

---

## 详细附录(深挖,不重复本文)
- `2026-07-02-unified-tri-surface-spec.md` — 三端统一设计 + 附录 A(Garmin 数据发现)/ B(续航竞品)/ **C(渲染与数据架构)**
- `2026-07-03-design-system.md` — 设计系统 §一 色彩 · **§九 洞图渲染标准 + 踩坑清单**
- `2026-07-02-garmin-course-data-reference.md` — Garmin 球场数据字典(4 层)
- `2026-07-03-garmin-data-to-features.md` — 数据→功能路线图
- `assets/hole-render-topo-prototype.py` — topo 渲染原型(生产版 `ai_caddie/geometry/topo_render.py`)
