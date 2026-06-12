import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { CorrectionsPage } from './CorrectionsPage'
import type { AnnotationCreateRequest, AnnotationCreateResponse, AnnotationKind, AnnotationTargetType } from '../types'

function responseFor(request: AnnotationCreateRequest): AnnotationCreateResponse {
  return {
    schema: 'ai-caddie-annotation-create-v1',
    annotation: {
      id: `ann-${request.kind}`,
      createdAt: '2026-05-25T10:40:00Z',
      targetType: request.targetType,
      targetId: request.targetId,
      kind: request.kind,
      payload: request.payload,
      source: 'manual',
    },
  }
}

function renderPage(
  onCreateAnnotation = vi.fn(async (request: AnnotationCreateRequest) => responseFor(request)),
  initialTarget?: { targetType: AnnotationTargetType; targetId: string },
) {
  render(
    <CorrectionsPage
      data={{ schema: 'ai-caddie-annotations-v1', total: 0, target: null, annotations: [] }}
      initialTarget={initialTarget}
      onCreateAnnotation={onCreateAnnotation}
    />,
  )
  return onCreateAnnotation
}

describe('CorrectionsPage', () => {
  it('summarizes correction impact without implying raw Garmin mutation', () => {
    render(
      <CorrectionsPage
        data={{
          schema: 'ai-caddie-annotations-v1',
          total: 4,
          target: null,
          annotations: [
            {
              id: 'ann-club',
              createdAt: '2026-05-25T10:40:00Z',
              targetType: 'shot',
              targetId: '900001:1:1',
              kind: 'club_correction',
              payload: { from: '8I', to: '7I' },
              source: 'manual',
            },
            {
              id: 'ann-score',
              createdAt: '2026-05-25T10:41:00Z',
              targetType: 'hole',
              targetId: '900001:1',
              kind: 'score_correction',
              payload: { from: 5, to: 4 },
              source: 'manual',
            },
            {
              id: 'ann-tag',
              createdAt: '2026-05-25T10:42:00Z',
              targetType: 'hole',
              targetId: '900001:1',
              kind: 'issue_tag',
              payload: { tag: 'approach_short' },
              source: 'manual',
            },
            {
              id: 'ann-note',
              createdAt: '2026-05-25T10:43:00Z',
              targetType: 'round',
              targetId: '900001',
              kind: 'round_note',
              payload: { text: 'Firm greens' },
              source: 'manual',
            },
          ],
        }}
        onCreateAnnotation={vi.fn()}
      />,
    )

    const impact = screen.getByLabelText('订正影响')
    expect(within(impact).getByRole('heading', { name: '订正影响' })).toBeInTheDocument()
    expect(within(impact).getByText('人工记录仅作为派生统计的覆盖层;Garmin 原始快照保持不变。')).toBeInTheDocument()
    expect(within(impact).getByText('批注总数')).toBeInTheDocument()
    expect(within(impact).getByText('统计覆盖')).toBeInTheDocument()
    expect(within(impact).getByText('订正')).toBeInTheDocument()
    expect(within(impact).getByText('只追加审计日志')).toBeInTheDocument()
    expect(within(impact).getByText('原始事实不可变')).toBeInTheDocument()
    expect(within(impact).getByText('历史统计使用显式覆盖')).toBeInTheDocument()
    expect(within(screen.getByLabelText('订正目标分布')).getByText('hole 2')).toBeInTheDocument()
    expect(within(screen.getByLabelText('订正目标分布')).getByText('round 1')).toBeInTheDocument()
    expect(within(screen.getByLabelText('订正目标分布')).getByText('shot 1')).toBeInTheDocument()
    expect(within(screen.getByLabelText('订正类型分布')).getByText('球杆订正 1')).toBeInTheDocument()
    expect(within(screen.getByLabelText('订正类型分布')).getByText('问题标签 1')).toBeInTheDocument()
    expect(within(screen.getByLabelText('订正类型分布')).getByText('球局备注 1')).toBeInTheDocument()
    expect(within(screen.getByLabelText('订正类型分布')).getByText('成绩订正 1')).toBeInTheDocument()
  })

  it.each([
    {
      option: '球位订正',
      targetType: 'shot',
      targetId: '900001:1:1',
      kind: 'lie_correction',
      fill: async () => {
        await userEvent.type(screen.getByLabelText('原记录球位'), 'rough')
        await userEvent.type(screen.getByLabelText('订正后球位'), 'fairway')
      },
      payload: { from: 'rough', to: 'fairway' },
    },
    {
      option: '罚杆订正',
      targetType: 'hole',
      targetId: '900001:2',
      kind: 'penalty_correction',
      fill: async () => {
        await userEvent.type(screen.getByLabelText('罚杆数'), '1')
        await userEvent.type(screen.getByLabelText('罚杆原因'), 'water')
      },
      payload: { strokes: 1, reason: 'water' },
    },
    {
      option: '天气备注',
      targetType: 'hole',
      targetId: '900001:7',
      kind: 'weather_context_note',
      fill: async () => {
        await userEvent.type(screen.getByLabelText('备注'), 'Strong headwind')
      },
      payload: { text: 'Strong headwind' },
    },
    {
      option: '策略备注',
      targetType: 'decision',
      targetId: '900001:7:2',
      kind: 'strategy_note',
      fill: async () => {
        await userEvent.type(screen.getByLabelText('备注'), 'Layup was smarter')
      },
      payload: { text: 'Layup was smarter' },
    },
    {
      option: '球童反馈',
      targetType: 'decision',
      targetId: '900001:7:2',
      kind: 'caddie_feedback',
      fill: async () => {
        await userEvent.selectOptions(screen.getByLabelText('反馈评价'), 'too_aggressive')
        await userEvent.type(screen.getByLabelText('备注'), 'Water was too close')
      },
      payload: { rating: 'too_aggressive', note: 'Water was too close' },
    },
    {
      option: '移除问题标签',
      targetType: 'hole',
      targetId: '900001:7',
      kind: 'issue_tag_removed',
      fill: async () => {
        await userEvent.type(screen.getByLabelText('问题标签'), 'approach_short')
      },
      payload: { tag: 'approach_short' },
    },
  ])('submits $option payloads', async ({ option, targetType, targetId, kind, fill, payload }) => {
    const onCreateAnnotation = renderPage()

    expect(screen.getByRole('option', { name: option })).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('目标类型'), targetType)
    await userEvent.type(screen.getByLabelText('目标编号'), targetId)
    await userEvent.selectOptions(screen.getByLabelText('订正类型'), kind)
    await fill()
    await userEvent.click(screen.getByRole('button', { name: '保存批注' }))

    expect(onCreateAnnotation).toHaveBeenCalledWith({
      targetType: targetType as AnnotationTargetType,
      targetId,
      kind: kind as AnnotationKind,
      payload,
    })
  })

  it.each([
    ['club_correction', '球杆订正需要同时填写原记录与订正后的球杆。'],
    ['issue_tag', '问题标签操作需要填写标签。'],
    ['note', '备注需先填写内容再保存。'],
  ])('prevents empty %s annotation payloads', async (kind, message) => {
    const onCreateAnnotation = renderPage()

    await userEvent.type(screen.getByLabelText('目标编号'), '900001:7')
    await userEvent.selectOptions(screen.getByLabelText('订正类型'), kind)
    await userEvent.click(screen.getByRole('button', { name: '保存批注' }))

    expect(onCreateAnnotation).not.toHaveBeenCalled()
    expect(screen.getByRole('status')).toHaveTextContent(message)
  })

  it('prevents non-numeric score corrections before calling the API', async () => {
    const onCreateAnnotation = renderPage()

    await userEvent.type(screen.getByLabelText('目标编号'), '900001:7')
    await userEvent.selectOptions(screen.getByLabelText('订正类型'), 'score_correction')
    await userEvent.type(screen.getByLabelText('原记录成绩'), 'four')
    await userEvent.type(screen.getByLabelText('订正后成绩'), '5')
    await userEvent.click(screen.getByRole('button', { name: '保存批注' }))

    expect(onCreateAnnotation).not.toHaveBeenCalled()
    expect(screen.getByRole('status')).toHaveTextContent('成绩订正需要数字形式的原记录与订正后成绩。')
  })

  it('labels issue tag removal records in annotation history', () => {
    render(
      <CorrectionsPage
        data={{
          schema: 'ai-caddie-annotations-v1',
          total: 1,
          target: null,
          annotations: [
            {
              id: 'ann-remove',
              createdAt: '2026-05-25T10:40:00Z',
              targetType: 'hole',
              targetId: '900001:7',
              kind: 'issue_tag_removed' as AnnotationKind,
              payload: { tag: 'approach_short' },
              source: 'manual',
            },
          ],
        }}
        onCreateAnnotation={vi.fn()}
      />,
    )

    expect(screen.getByRole('heading', { name: '移除问题标签' })).toBeInTheDocument()
    expect(screen.getByText('approach_short')).toBeInTheDocument()
  })

  it('prefills a source-bound target and keeps it after saving', async () => {
    const onCreateAnnotation = renderPage(undefined, { targetType: 'hole', targetId: '900001:7' })

    expect(screen.getByLabelText('目标类型')).toHaveValue('hole')
    expect(screen.getByLabelText('目标编号')).toHaveValue('900001:7')

    await userEvent.selectOptions(screen.getByLabelText('订正类型'), 'note')
    await userEvent.type(screen.getByLabelText('备注'), 'Pin was back right')
    await userEvent.click(screen.getByRole('button', { name: '保存批注' }))

    expect(onCreateAnnotation).toHaveBeenCalledWith({
      targetType: 'hole',
      targetId: '900001:7',
      kind: 'hole_note',
      payload: { text: 'Pin was back right' },
    })
    expect(screen.getByLabelText('目标类型')).toHaveValue('hole')
    expect(screen.getByLabelText('目标编号')).toHaveValue('900001:7')
  })

  it('restores the source-bound target type when saving after local target edits', async () => {
    const onCreateAnnotation = renderPage(undefined, { targetType: 'hole', targetId: '900001:7' })

    await userEvent.selectOptions(screen.getByLabelText('目标类型'), 'shot')
    await userEvent.clear(screen.getByLabelText('目标编号'))
    await userEvent.type(screen.getByLabelText('目标编号'), '900001:7:1')
    await userEvent.selectOptions(screen.getByLabelText('订正类型'), 'note')
    await userEvent.type(screen.getByLabelText('备注'), 'Pin was back right')
    await userEvent.click(screen.getByRole('button', { name: '保存批注' }))

    expect(onCreateAnnotation).toHaveBeenCalledWith({
      targetType: 'shot',
      targetId: '900001:7:1',
      kind: 'shot_note',
      payload: { text: 'Pin was back right' },
    })
    expect(screen.getByLabelText('目标类型')).toHaveValue('hole')
    expect(screen.getByLabelText('目标编号')).toHaveValue('900001:7')
  })
})
