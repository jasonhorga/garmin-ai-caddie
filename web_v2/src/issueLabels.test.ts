import { describe, expect, it } from 'vitest'
import { issueLabel } from './issueLabels'

// Full backend issue-token vocabulary: ai_caddie/issue_taxonomy.py plus the
// manual-annotation extras (tee_left/tee_right/short_game/penalty) that the
// frontend already labelled. Every token must render golf Chinese — raw
// English tokens on the 强弱分析 page were a visual-acceptance finding.
const EXPECTED: Record<string, string> = {
  approach_short: '攻果岭偏短',
  approach_long: '攻果岭偏长',
  approach_left: '攻果岭偏左',
  approach_right: '攻果岭偏右',
  tee_right: '开球偏右',
  tee_left: '开球偏左',
  tee_miss: '开球失误',
  tee_position_bad: '开球落点差',
  fairway_missed_left: '未上球道(偏左)',
  fairway_missed_right: '未上球道(偏右)',
  three_putt: '三推',
  short_game: '短杆',
  penalty: '罚杆',
  double_or_worse: '双柏忌或更差',
  hazard_result: '落入障碍区',
  ob: '出界(OB)',
  water: '下水',
  bunker: '沙坑救球',
  rough: '长草脱困',
  wrong_club: '选杆失误',
  poor_lie: '球位不佳',
  wind: '受风影响',
  slope: '坡位影响',
  blocked_view: '视线受阻',
  recovery_failed: '脱困失败',
  too_aggressive: '打法过于激进',
  too_conservative: '打法过于保守',
  club_uncertainty: '选杆不确定',
  low_confidence_club: '球杆样本不足',
  missing_shots: '缺少击球数据',
  missing_putt_data: '缺少推杆数据',
  missing_geometry: '缺少几何数据',
  weak_sample_size: '样本偏少',
}

describe('issueLabel', () => {
  it('covers the full backend issue-token vocabulary with golf Chinese', () => {
    for (const [token, zh] of Object.entries(EXPECTED)) {
      expect(issueLabel(token), token).toBe(zh)
    }
  })

  it('falls back to the raw token for unknown issues', () => {
    expect(issueLabel('some_future_issue')).toBe('some_future_issue')
    expect(issueLabel('')).toBe('')
  })
})
