# 三端重做 · 改动日志 + TODO

> 规则(负责人 2026-07-05 定):**每一次改动都记进这份日志;同时一直维护下方 TODO。**
> 配套 spec:`2026-07-02-unified-tri-surface-spec.md`(附录 C 架构)、`2026-07-03-design-system.md`(§一 色彩/§九 洞图渲染标准)。
> 大原则(负责人):**数据/准备层在后端做一次,Web/iOS/手表都直接复用;组件可复用;开局时后端统一预加载。不要一端一端修。**

---

## 改动日志(按合并顺序)

| PR / commit | 面 | 改动 | 状态 |
|---|---|---|---|
| `9c1e93d` `501ef20` | spec | 锁定洞图渲染标准(写实 topo,§九)+ Q1–Q5 三模型对抗结论进 spec;归档原型 `assets/hole-render-topo-prototype.py` | 合并(spec 分支) |
| #220 | Web | P1 外壳:导航模型 复盘/备战/统计/球包/设置 + 暗色 nav rail + 设计 tokens(styles.css) | 合并 + 部署 |
| #222 | Web | P2 备战工作台(PrepWorkbench/HoleCanvas/Inspector,接真实 course-prep) | 合并 + 部署 |
| #223 | Web | P3 复盘工作台(ReviewWorkbench,落点图 + 杆序 + 决策vs实际 + 圈方成绩;移除旧 HomeOverview) | 合并 + 部署 |
| #224 | Web | P4 统计仪表盘(StatsDashboard;无假 SG,用真实各环节失杆 + 真实时间窗) | 合并 + 部署 |
| #225 | Web | P5 球包(BagPage,gapping 阶梯 + 可编辑;与 iOS 同一份 club profile;砍无数据列) | 合并 + 部署 |
| #227 | Web | 收尾:球场分布图 <3 场时隐藏、强弱分析条按比例、手机"球局"不竖排 | 合并 + 部署 |
| #231 | Web | 横向记分条选洞(备战/复盘)+ 即时占位→topo 交叉淡入 + `POST …/topo/prewarm` 预热 + 相邻洞预取 | 合并 + 部署 |
| #221 | iOS | 打球/记分屏 **暗色**图形化重做(CurrentHoleView + LivePlayPanel;贴手表) | 合并 |
| #226 | iOS | 首页/复盘 **浅色** iOS 原生(HubReviewStyle + ScoreChip 圈方) | 合并 |
| #228 | iOS | 备战/统计/球包 **浅色**重皮 | 合并 |
| #229 | 后端+Web | topo 渲染管线:`geometry/topo_render.py`(任意洞)+ 端点 `GET …/courses/{gid}/holes/{hole}/topo.png`(渲一次缓存)+ Web canvas 拉真图 | 合并 + 部署 |
| #230 | iOS | 三处洞图(实战/备战/复盘)接 topo 端点 + 无几何/无网兜底 | 合并 |

**部署**:homeserver `/me`,绿了自动部署(web 构建 +（后端改动时）`docker compose build api && up -d api`)。iOS 走 TestFlight(负责人门控,未发)。

---

## TODO

### 进行中
- [ ] **地基·后端共享层**(PR `superpowers/shared-topo-frame-club`):
  - [ ] topo 洞图**填满整幅** bug(现在只填 ~35%):topo 图 + 矢量叠加共用同一个"填满整幅"投影(既填满又对齐)
  - [ ] **球杆解析** bug(复盘杆找不到):后端按 clubId/clubTypeId → 我们球包真实杆名稳健解析(先查 clubId 到底怎么对不上),clubName 一填三端都有杆

### 下一步(吃地基这层数据)
- [ ] 各端 **shot-map UI**:落点线**加粗** + 每个落点**标球杆**(参考 Garmin,不写距离/位置)—— Web + iOS 都做,复用后端解析好的杆
- [ ] **开局统一预热**:round-start 时后端把整场洞图渲+缓存(iOS/手表也预加载),不只 Web;继续提速

### 尾巴(小)
- [ ] iOS 球包做成 gapping 阶梯图(现在是浅色球杆列表,能用)
- [ ] topo 底部 tee 端小缺口(走廊裁切,装饰性)

### 门控(等负责人明说,不擅自做)
- [ ] 发 TestFlight(iOS 上架)
- [ ] integration/v2 → main(真·生产)
- [ ] 手表重做整合(另一条线)
