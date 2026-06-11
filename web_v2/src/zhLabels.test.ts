import { describe, expect, it } from 'vitest'
import { phaseZh, coverageZh, stateZh, confidenceZh } from './zhLabels'

describe('phaseZh', () => {
  it('maps known phase tokens to Chinese', () => {
    expect(phaseZh('Tee')).toBe('开球')
    expect(phaseZh('Approach')).toBe('攻果岭')
    expect(phaseZh('Putting')).toBe('推杆')
    expect(phaseZh('Scoring')).toBe('得分')
  })

  it('falls back to the raw token for unknown phases', () => {
    expect(phaseZh('unknown')).toBe('unknown')
    expect(phaseZh('Short Game')).toBe('Short Game')
  })
})

describe('coverageZh', () => {
  it('maps coverage states to Chinese', () => {
    expect(coverageZh('ready')).toBe('齐全')
    expect(coverageZh('partial')).toBe('部分')
    expect(coverageZh('missing')).toBe('缺失')
  })

  it('falls back to the raw token for unknown coverage values', () => {
    expect(coverageZh('other')).toBe('other')
    expect(coverageZh('unknown')).toBe('unknown')
  })
})

describe('stateZh', () => {
  it('maps data/connector states to Chinese', () => {
    expect(stateZh('ready')).toBe('就绪')
    expect(stateZh('error')).toBe('错误')
    expect(stateZh('no_data')).toBe('无数据')
    expect(stateZh('reauth_required')).toBe('需重新登录')
    expect(stateZh('not_available')).toBe('不可用')
    expect(stateZh('degraded')).toBe('降级')
  })

  it('falls back to the raw token for unknown states', () => {
    expect(stateZh('unknown')).toBe('unknown')
    expect(stateZh('syncing')).toBe('syncing')
  })
})

describe('confidenceZh', () => {
  it('maps confidence levels to Chinese', () => {
    expect(confidenceZh('high')).toBe('高')
    expect(confidenceZh('medium')).toBe('中')
    expect(confidenceZh('low')).toBe('低')
    expect(confidenceZh('insufficient')).toBe('样本不足')
  })

  it('falls back to the raw token for unknown confidence values', () => {
    expect(confidenceZh('other')).toBe('other')
    expect(confidenceZh('none')).toBe('none')
  })
})
