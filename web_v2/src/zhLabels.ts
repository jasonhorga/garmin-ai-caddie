const FORM_DIRECTION_ZH: Record<string, string> = {
  improving: '进步中',
  stable: '稳定',
  declining: '下滑',
  insufficient_data: '样本不足',
}

const PHASE_ZH: Record<string, string> = {
  Tee: '开球',
  Approach: '攻果岭',
  Putting: '推杆',
  Scoring: '得分',
  'Course Management': '攻略',
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
