const ISSUE_LABELS: Record<string, string> = {
  approach_short: '攻果岭偏短',
  tee_right: '开球偏右',
  tee_left: '开球偏左',
  three_putt: '三推',
  short_game: '短杆',
  penalty: '罚杆',
  double_or_worse: '双柏忌或更差',
  missing_shots: '缺少击球数据',
}

export function issueLabel(token: string): string {
  return ISSUE_LABELS[token] ?? token
}
