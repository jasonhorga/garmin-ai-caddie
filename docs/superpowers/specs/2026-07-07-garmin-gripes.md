# Garmin 高尔夫(手表 + App/网页)用户抱怨与改进意见汇编(2026-07-07)

> 目的:系统扒一遍真实用户对 Garmin 高尔夫这一整套(手表 + App + 网页)**都抱怨什么、最想改什么、也别漏了真正喜欢什么**,拿它定我们(AI 球童)的差异化和优先级。研究由强模型全网查证(不 spawn 子 agent),信号强弱按"多来源/多人=强"标注,诚实缺口见文末 §E。
>
> **一句话总印象(最强信号,多来源反复出现):Garmin 硬件最好、App 最差;Arccos / Shot Scope 更好用、数据更多、更新更勤。**

## 0. 先纠错:能不能在"两杆之间"干净插一杆?——能

**负责人对,我错了。** 当前 Garmin Golf App 加杆步骤(官方):打开 App → Activity → 选记分卡 → **View Shot Maps** → 点"加杆"图标 → 在洞地图上点这一杆要放的位置 → 弹窗补用杆等 → Save。编辑已有杆:点该杆 → 改用杆 / 标 OOB / 删除 → Save;另有 shot list 可重排杆序。**不需要删掉后面的杆再重输**——我之前引的"删光重输"是 2018–19 年 S40/S60 **手表端**的旧限制。

但它的编辑**当前仍痛**,这几条才是真机会:
- **整洞的杆全删光 → 这个洞变"砖",App 和网页都加不回**。官方社区忠告"别全删,先加对的再删错的"。—— 最大的坑。
- 手动加的杆**位置只是近似**(系统不知道那杆精确 GPS);**跨洞移动一杆**没有原生功能,只能"从错洞删、在对洞手动加"。
- **近期(2026-01, iOS)重排回归 bug**:shot list 里拖一杆,松手弹回;编辑落点约 **60–75% 概率报 "Unable to save"**。
- 手表**打球中**的 Add Shot 是"从当前站位补一杆",不是按位置回插;按位置编辑发生在赛后 App。

**给我们的启示**:Garmin 能插杆,但"删空整洞即变砖 + 落点只能近似 + 重排易 bug + 频繁保存失败"让编辑依旧被骂 clunky。**我们要赢的不是"能不能插",是"干净、可靠、永不变砖、一键删误杆"。**

## A. 手表(Approach S 系列、Fenix/Epix/Venu 高尔夫模式)

- **A1 自动记杆(强)**:只记满杆,**推杆/切杆/小 wedge 记不到** + **误记错序** + **无一键删误杆**;补短杆要**另买 CT10**。反复诉求:打完弹"好球/推杆/失误/半挥"标签、**当场改这一杆距离**(而非赛后进 App)。
- **A2 打球中补杆(中)**:漏记想补时手表已跳记分模式,流程不顺;putts 灰掉加不了(多为老帖,长期痛点)。
- **A3 球杆管理 UX(中,可直接抄改)**:球杆**按字母排不按 loft 排**;用昵称就**不显示杆型简写(7i/4W/PW/D)**、近名难分;最下方杆只露一半易误选;要"用力按"才算滑动;大字号挤版。剔除一杆坏距离数据要**翻遍所有记分卡逐洞找**(有人花一小时);诉求="My Bag 点某杆→列所有距离→点一条跳该洞→直接删"(5+ 附议,Garmin 未实现)。
- **A4 触屏/雨天/手套(中)**:雨天、袖口摩擦误触/冻屏,手套误触;S70 触屏"不如 Apple Watch 跟手",地图平移缩放靠滑块+两个键"烦"。
- **A5 电池(个别)**:S70 续航评测普遍正面;S62 个别机异常掉电,更像单机/设置问题。
- **A6 距离/PlaysLike(碎片化)**:距离精度是**被夸最多**的(见 §C);抱怨在**按机型阉割**(无气压计就没风力版 PlaysLike;风力需联网,场上连不上报错),"同名功能不同表不一样"令人困惑。
- **A7 型号碎片化(结构性)**:S12 无触屏/无 AutoShot(只能手动 Measure Shot,"总忘触发");Fenix/Epix/Venu 高尔夫模式与 S70 重合约 99.9%,抱怨更多落在订阅墙/屏幕观感/触屏。

## B. App / 网页(Garmin Golf app + Garmin Connect)

- **B1 逐杆编辑**:见 §0(能插杆,但删空变砖 / 落点近似 / 重排 bug / 频繁 "Unable to save" / 跨洞移动手动)——**当前仍痛**。
- **B2 统计深度(最响最普遍)**:采了和 Arccos 一样的数据却几乎**不分析**——俱乐部统计不能按场次/杆数筛、无开球左右命中、无 GIR 方向、无可视 shot map、**无 strokes gained**;赛后无平均开球距离、无 SG、无按 par 分类得分、无差点对标;球场/球员统计无 par 均分、无逐洞、无按洞型/进攻距离/地形分类、对标基准不可选、无趋势线。用户原话"烂到不能再烂""图形原始、啥也说明不了",转投 Arccos。**Strokes Gained**:Garmin 的极其基础、"borderline meaningless";三大诉求=记第一推离洞距离、一键标旗位、可对标多档差点(pro/scratch/5/10/15)。Garmin 2+ 年前回"在路线图上",至今没兑现。
- **B3 简单统计缺失 + putts 手动补(强,"数据明明有")**:不给逐洞均值/Birdies/Par5 Avg/Average Putts;总 putts 不合计、要逐洞手补;疑似故意留给付费版。
- **B4 同步/丢卡(中,周期性)**:记分卡不上传、**更新后所有卡消失**(均值还在卡没了)、卡卡在手表里——常在版本更新后爆发。
- **B5 球场地图过时/更新慢(长期系统性)**:用地图数据非实地测绘、**季度更新**;球场改造后可能"18 洞错 12 洞",主场"基本没用"。
- **B6 界面/改版副作用(中)**:近年更新被批"选项太多、改错要点很多次、别乱动没坏的";**注意 Garmin 近期确实重做了 App 首页与导航**,纯"找不到"类可能已缓解,但**深度/统计类抱怨改版后依旧**。
- **B7 差点(强,预期错配)**:App 里是**"预测/理论差点"不是 WHS**,数值常离谱(官方 35.5 显 24.4、出现 -5.4),疑用旧"上限 36"体系,**无法对接官方 WHS**。3+ 年多人、无正式修复。
- **B8 社交/比赛(中)**:有周赛榜/自建比赛/live scoring/赛中聊天;但**无好友记分动态流**,比赛分数偶尔不上传。
- **B9 订阅墙(强,触及品牌根基)**:果岭等高线 + Enhanced CourseView 高清图要 **Garmin Golf 会员 ~$9.99/月**,评测嫌"这么贵的表还月付";大背景是 Garmin 把更多功能塞进 **Connect+ 订阅**引发反弹(媒体点名 "enshittification")——而 **"无订阅"当初正是大家选 Garmin 的核心原因**。既是警示也是机会。

## C. 用户真正喜欢 / 千万别破坏(我们至少不能输)

- **GPS 距离精度**(F/M/B、hazard、layup、手动挪旗)——夸最多、几乎零抱怨。**信任底座。**
- 硬件做工/耐用;续航(MIP 超长、S70 也够);
- **核心 GPS + 记分免订阅、一次买断**(品牌起家卖点,正被订阅墙侵蚀);
- **简单直觉**(非科技玩家几分钟上手,一屏给关键码数);
- S70 AMOLED 亮屏 + **好看的球洞图**("目前高尔夫表里最好看的地图");
- 预装约 43,000 球场、自动更新、离线可用;场外智能手表/健康(甩开纯高尔夫竞品);
- AutoShot 对满杆记得挺准(问题只在短杆);一账户汇聚所有 Garmin 设备数据。

## D. Top 10 最痛/最想要(排序,给差异化用)

1. **App 统计太浅**——SG 残缺、不能按不同差点对标、俱乐部统计不能剔异常、缺方向/趋势/按洞型分析。("采了不分析",最响)
2. **逐杆编辑既烂又危险**——删空整洞变砖、加杆落点近似、跨洞移动手动、重排 bug、频繁 "Unable to save"。
3. **简单统计缺失 + putts 逐洞手补**(数据明明有)。
4. **短杆/推杆记不到 + 误记错序 + 无一键删误杆**(还得另买 CT10)。
5. **订阅墙蔓延**(果岭图月付 + Connect+),侵蚀"无订阅"起家卖点。
6. **差点不是 WHS、是"预测差点"、数值离谱、无法对接官方**。
7. **球场地图过时/更新慢**。
8. **手表打球中操作摩擦**(球杆不按 loft 排、昵称遮杆型、雨天误触、大字号挤版、地图缩放笨)。
9. **同步/可靠性**(丢卡、更新后卡消失、总数不合计)。
10. **社交/比赛弱**(无好友记分动态流、分数偶尔不上传)。

**我们(AI 球童)的差异化落点**:把 #1/#2/#3/#4/#6 做成"一键、干净、可信"的赛后逐杆复盘 + 真·可对标的 strokes gained + 不用买传感器也能补短杆的编辑;把 #5 做成"核心不收订阅"的明确承诺;同时**守住 §C 的距离精度与简单直觉**,别把易用性做没了。

## E. 诚实标注

- **普遍且当前**:App 统计浅、SG 弱、简单统计缺、逐杆编辑 clunky、AutoShot 短杆漏、订阅墙、差点困惑——信号最强。
- **周期性/版本相关**:同步丢卡、tally 不合计、重排 bug——随补丁时好时坏;iOS 重排 bug 是 2026-01 新回归,可能已在修。
- **个别/单机**:S62 掉电/冻屏——勿过度外推。
- **可能已部分缓解**:App 首页/导航近期重做过,"找不到"类 UI 抱怨可能改善;但"深度不足"核心抱怨依旧。
- **来源缺口**:本轮 **Reddit 抓取被屏蔽**,r/GolfGadgets 等仅经二手源(MyGolfSpy 论坛/评测站)反映;Wareable/MyGolfSpy/TechRadar 的 S70 评测正文 403。要补 Reddit 一手帖需在能直连的环境再跑一轮。

---

**主要出处**(节选):
- 加杆步骤(官方)— https://support.garmin.com/en-US/?faq=imh6LzeTWZ0TeykxOaeUX5
- 删空整洞变砖 — https://forums.garmin.com/outdoor-recreation/golf/f/approach-s60/226486/is-there-anyway-to-add-shots-to-a-hole-when-there-are-none
- 统计不如 Arccos(对照清单)— https://forums.garmin.com/apps-software/mobile-apps-web/f/garmin-golf-android/412939/lack-of-features-and-stats-in-garmin-golf-compared-to-arccos
- Strokes Gained 严重不足 — https://forums.garmin.com/outdoor-recreation/golf/f/approach-s70/348645/strokes-gained-data-severely-lacking-vs-arccos---any-updates-planned
- 缺陷/bug 清单 v2.13.1(30+ 条)— https://forums.garmin.com/apps-software/mobile-apps-web/f/garmin-golf-android/338216/functional-blockers-bugs-and-missing-features-as-of-2-13-1
- "The app is awful" — https://forums.garmin.com/apps-software/mobile-apps-web/f/garmin-golf-ios/382438/the-app-is-awful
- 差点非 WHS — https://forums.garmin.com/apps-software/mobile-apps-web/f/garmin-golf-android/318986/garmin-can-you-please-fix-the-handicap-calculation-in-the-golf-app
- 订阅墙/enshittification — https://www.techdirt.com/2025/05/12/garmin-ceo-hints-more-paywalls-and-enshittification-are-coming-falsely-claims-users-love-it/
- CT10 vs Arccos(硬件最好App最差)— https://outofboundsgolf.com/ct10-vs-arccos/
