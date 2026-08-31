import type { ProfileVisualData } from '@/api/types'

export type ProfileTemplateKind = 'dashboard' | 'minimal' | 'report'

export const profileTemplateMeta: Record<ProfileTemplateKind, { label: string; description: string }> = {
  dashboard: { label: '数据看板', description: '图表为主，全量可视化展示' },
  minimal: { label: '极简卡片', description: '文字 + 标签 + 数字统计，克制排版' },
  report: { label: '报告式', description: '图文混排，适合导出 / 打印' },
}

/** 后端未返回结构化画像时的演示数据（标注「演示数据」）。 */
export const demoProfileVisual: ProfileVisualData = {
  radar: [
    { dimension: '专业能力', score: 82 },
    { dimension: '沟通协作', score: 70 },
    { dimension: '决策效率', score: 65 },
    { dimension: '创新探索', score: 55 },
    { dimension: '风险意识', score: 74 },
  ],
  memoryTypeDist: [
    { type: 'fact', count: 18 },
    { type: 'preference', count: 10 },
    { type: 'task_state', count: 6 },
    { type: 'process', count: 5 },
    { type: 'correction', count: 3 },
  ],
  tags: ['BOM转换', '供应商', '交期管理', '质量追溯', '物料替代', '排产优化'],
  trend: [
    { date: '2026-08-01', count: 5 },
    { date: '2026-08-04', count: 8 },
    { date: '2026-08-08', count: 9 },
    { date: '2026-08-12', count: 6 },
    { date: '2026-08-16', count: 11 },
    { date: '2026-08-20', count: 7 },
  ],
}

/** 判断画像是否缺少可视化数据（需要演示兜底）。 */
export function needsVisualFallback(visual?: ProfileVisualData): boolean {
  if (!visual) return true
  return !visual.radar?.length
    && !visual.memoryTypeDist?.length
    && !visual.tags?.length
    && !visual.trend?.length
}

/** 解析可视化数据：后端字段缺失时用演示数据兜底，并标记 isDemo。 */
export function resolveVisual(visual?: ProfileVisualData): {
  data: ProfileVisualData
  isDemo: boolean
} {
  return needsVisualFallback(visual)
    ? { data: demoProfileVisual, isDemo: true }
    : { data: visual as ProfileVisualData, isDemo: false }
}
