// recentForm direction vocabulary: _improvement_direction emits
// improving/declining/flat/insufficient_data; club distance trends reuse the
// key with stable (history_stats.py). Unknown tokens fall through raw.
const FORM_DIRECTION_ZH: Record<string, string> = {
  improving: '进步中',
  stable: '稳定',
  declining: '下滑',
  flat: '持平',
  insufficient_data: '样本不足',
}

// Shot miss bearings (teeDirection/approachMiss dominantMiss, sandbox
// acceptableMiss.direction). The decision engine also ships looser tokens
// (away_from_known_risks / wide_side / history_* — decision.py:3119-3152);
// those pass through RAW rather than guessing a translation.
const MISS_DIRECTION_ZH: Record<string, string> = {
  left: '偏左',
  right: '偏右',
  short: '偏短',
  long: '偏长',
}

// Issue-taxonomy phases (ai_caddie/issue_taxonomy.py) + scoring phases.
// 攻略 means "guide" — Course Management is 场上决策, never 攻略.
const PHASE_ZH: Record<string, string> = {
  Tee: '开球',
  Approach: '攻果岭',
  Putting: '推杆',
  Scoring: '得分',
  'Course Management': '场上决策',
  'Short Game': '短杆',
  Penalty: '罚杆',
  'Club Confidence': '球杆信心',
  'Data Quality': '数据质量',
  Trend: '趋势',
}

const COVERAGE_ZH: Record<string, string> = {
  ready: '齐全',
  good: '良好',
  partial: '部分',
  missing: '缺失',
}

const STATE_ZH: Record<string, string> = {
  ready: '就绪',
  error: '错误',
  no_data: '无数据',
  reauth_required: '需重新登录',
  not_available: '不可用',
  degraded: '降级',
}

const CONFIDENCE_ZH: Record<string, string> = {
  high: '高',
  medium: '中',
  low: '低',
  insufficient: '样本不足',
}

const DATA_MODE_ZH: Record<string, string> = {
  local: '本地',
  fixture: '示例',
}

export function formDirectionZh(raw: string): string {
  return FORM_DIRECTION_ZH[raw] ?? raw
}

export function missDirectionZh(raw: string): string {
  return MISS_DIRECTION_ZH[raw] ?? raw
}

export function phaseZh(raw: string): string {
  return PHASE_ZH[raw] ?? raw
}

export function coverageZh(raw: string): string {
  return COVERAGE_ZH[raw] ?? raw
}

export function stateZh(raw: string): string {
  return STATE_ZH[raw] ?? raw
}

export function confidenceZh(raw: string): string {
  return CONFIDENCE_ZH[raw] ?? raw
}

export function dataModeZh(raw: string): string {
  return DATA_MODE_ZH[raw] ?? raw
}

// Garmin club nicknames carry a literal trailing 退役 marker for retired
// clubs ("48° 退役") which reads broken — render as 「48°(已退役)」.
export function clubLabelZh(raw: string): string {
  const match = /^(.+?)[\s·]*退役$/.exec(raw)
  if (!match || !match[1].trim()) return raw
  return `${match[1].trim()}(已退役)`
}

// dataQuality finding labels — the full history_stats _data_quality
// vocabulary (history_stats.py:3232-3508) for header chips and 数据健康 rows.
const QUALITY_LABEL_ZH: Record<string, string> = {
  shots: '击球数据',
  shot_rows: '击球明细',
  putts: '推杆数据',
  geometry: '几何覆盖',
  reports: '报告覆盖',
  rating_slope: '评级/坡度',
  club_samples: '球杆样本',
  decision_audits: '决策审计',
  annotations: '标注',
  corrections: '订正',
  weather: '天气数据',
}

export function qualityLabelZh(raw: string): string {
  return QUALITY_LABEL_ZH[raw] ?? raw
}

// DataQualityBadge labels (server_v2/history_overview.py _quality_badges /
// _round_badges) for round-card and overview badge chips.
const BADGE_LABEL_ZH: Record<string, string> = {
  shots: '击球',
  'shot rows': '击球明细',
}

export function badgeLabelZh(raw: string): string {
  return BADGE_LABEL_ZH[raw] ?? raw
}

// 备战 tips 依据 keys (ai_caddie/prep_tips.py basis vocabulary). Unknown
// machine keys map to null so they are hidden instead of rendered raw.
const TIP_BASIS_ZH: Record<string, string> = {
  'course.teeDirection': '你在本场的开球倾向',
  'course.approachMiss': '你在本场的攻果岭落点',
  'course.prepHoles': '球场洞表(长度与HCP)',
}

const PAR_LABEL_ZH: Record<string, string> = { par3: '三杆洞', par4: '四杆洞', par5: '五杆洞' }

export function tipBasisZh(raw: string): string | null {
  if (TIP_BASIS_ZH[raw]) return TIP_BASIS_ZH[raw]
  const courseParScoring = /^course\.parScoring\.(par[345])$/.exec(raw)
  if (courseParScoring) return `你在本场的${PAR_LABEL_ZH[courseParScoring[1]]}成绩`
  const profilePar = /^playerProfile\.(par[345])_scoring_(?:strength|loss)$/.exec(raw)
  if (profilePar) return `你的${PAR_LABEL_ZH[profilePar[1]]}总体成绩`
  if (/^playerProfile\.caddieBiases\./.test(raw)) return '球童偏置记录'
  return null
}
