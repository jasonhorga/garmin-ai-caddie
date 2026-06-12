import { describe, expect, it } from 'vitest'
import { phaseZh, coverageZh, stateZh, confidenceZh, dataModeZh, clubLabelZh, qualityLabelZh, tipBasisZh, formDirectionZh, missDirectionZh, badgeLabelZh } from './zhLabels'

describe('phaseZh', () => {
  it('maps known phase tokens to Chinese', () => {
    expect(phaseZh('Tee')).toBe('开球')
    expect(phaseZh('Approach')).toBe('攻果岭')
    expect(phaseZh('Putting')).toBe('推杆')
    expect(phaseZh('Scoring')).toBe('得分')
    // 攻略 means "guide" — the Course Management phase reads as 场上决策.
    expect(phaseZh('Course Management')).toBe('场上决策')
    expect(phaseZh('Short Game')).toBe('短杆')
    expect(phaseZh('Penalty')).toBe('罚杆')
    expect(phaseZh('Club Confidence')).toBe('球杆信心')
    expect(phaseZh('Data Quality')).toBe('数据质量')
    expect(phaseZh('Trend')).toBe('趋势')
  })

  it('falls back to the raw token for unknown phases', () => {
    expect(phaseZh('unknown')).toBe('unknown')
    expect(phaseZh('Recovery')).toBe('Recovery')
  })
})

describe('clubLabelZh', () => {
  it('rewrites the trailing 退役 marker as a (已退役) suffix', () => {
    expect(clubLabelZh('48° 退役')).toBe('48°(已退役)')
    expect(clubLabelZh('4I 退役')).toBe('4I(已退役)')
    expect(clubLabelZh('5H退役')).toBe('5H(已退役)')
  })

  it('leaves ordinary club names untouched', () => {
    expect(clubLabelZh('1D')).toBe('1D')
    expect(clubLabelZh('48°')).toBe('48°')
    expect(clubLabelZh('退役')).toBe('退役')
  })
})

describe('qualityLabelZh', () => {
  it('maps data-quality finding labels to Chinese', () => {
    expect(qualityLabelZh('geometry')).toBe('几何覆盖')
    expect(qualityLabelZh('reports')).toBe('报告覆盖')
    expect(qualityLabelZh('shots')).toBe('击球数据')
  })

  it('covers the full history_stats _data_quality label vocabulary', () => {
    expect(qualityLabelZh('shot_rows')).toBe('击球明细')
    expect(qualityLabelZh('rating_slope')).toBe('评级/坡度')
    expect(qualityLabelZh('club_samples')).toBe('球杆样本')
    expect(qualityLabelZh('decision_audits')).toBe('决策审计')
    expect(qualityLabelZh('weather')).toBe('天气数据')
    expect(qualityLabelZh('putts')).toBe('推杆数据')
    expect(qualityLabelZh('annotations')).toBe('标注')
    expect(qualityLabelZh('corrections')).toBe('订正')
  })

  it('falls back to the raw label for unknown findings', () => {
    expect(qualityLabelZh('mystery')).toBe('mystery')
  })
})

describe('badgeLabelZh', () => {
  it('maps DataQualityBadge labels (history_overview badges) to Chinese', () => {
    expect(badgeLabelZh('shots')).toBe('击球')
    expect(badgeLabelZh('shot rows')).toBe('击球明细')
  })

  it('falls back to the raw label for unknown badges', () => {
    expect(badgeLabelZh('weather')).toBe('weather')
  })
})

describe('formDirectionZh', () => {
  it('maps the full _improvement_direction vocabulary to Chinese', () => {
    expect(formDirectionZh('improving')).toBe('进步中')
    expect(formDirectionZh('declining')).toBe('下滑')
    expect(formDirectionZh('flat')).toBe('持平')
    expect(formDirectionZh('stable')).toBe('稳定')
    expect(formDirectionZh('insufficient_data')).toBe('样本不足')
  })

  it('falls back to the raw token for unknown directions', () => {
    expect(formDirectionZh('volatile')).toBe('volatile')
  })
})

describe('missDirectionZh', () => {
  it('maps the four miss bearings to Chinese', () => {
    expect(missDirectionZh('left')).toBe('偏左')
    expect(missDirectionZh('right')).toBe('偏右')
    expect(missDirectionZh('short')).toBe('偏短')
    expect(missDirectionZh('long')).toBe('偏长')
  })

  it('passes looser engine tokens through raw rather than guessing', () => {
    expect(missDirectionZh('away_from_known_risks')).toBe('away_from_known_risks')
    expect(missDirectionZh('wide_side')).toBe('wide_side')
  })
})

describe('tipBasisZh', () => {
  it('maps the prep-tips basis key vocabulary to Chinese', () => {
    expect(tipBasisZh('course.teeDirection')).toBe('你在本场的开球倾向')
    expect(tipBasisZh('course.approachMiss')).toBe('你在本场的攻果岭落点')
    expect(tipBasisZh('course.parScoring.par3')).toBe('你在本场的三杆洞成绩')
    expect(tipBasisZh('course.parScoring.par4')).toBe('你在本场的四杆洞成绩')
    expect(tipBasisZh('course.parScoring.par5')).toBe('你在本场的五杆洞成绩')
    expect(tipBasisZh('playerProfile.par5_scoring_loss')).toBe('你的五杆洞总体成绩')
    expect(tipBasisZh('playerProfile.par3_scoring_strength')).toBe('你的三杆洞总体成绩')
    expect(tipBasisZh('playerProfile.caddieBiases.protect_left_tee_miss')).toBe('球童偏置记录')
    expect(tipBasisZh('course.prepHoles')).toBe('球场洞表(长度与HCP)')
  })

  it('returns null for unknown machine keys so raw keys never render', () => {
    expect(tipBasisZh('course.unknownThing')).toBeNull()
    expect(tipBasisZh('playerProfile.other_signal')).toBeNull()
    expect(tipBasisZh('')).toBeNull()
  })
})

describe('coverageZh', () => {
  it('maps coverage states to Chinese', () => {
    expect(coverageZh('ready')).toBe('齐全')
    expect(coverageZh('good')).toBe('良好')
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

describe('dataModeZh', () => {
  it('maps snapshot data modes to Chinese', () => {
    expect(dataModeZh('local')).toBe('本地')
    expect(dataModeZh('fixture')).toBe('示例')
  })

  it('falls back to the raw token for unknown data modes', () => {
    expect(dataModeZh('garmin')).toBe('garmin')
    expect(dataModeZh('unknown')).toBe('unknown')
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
