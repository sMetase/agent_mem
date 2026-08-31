/** 后端 5 类记忆类型（旧 decision/constraint/feedback 已废弃），中文标签为统一默认值。 */
export const memoryTypeOptions = [
  { label: '关键事实', value: 'fact' },
  { label: '用户偏好', value: 'preference' },
  { label: '任务状态', value: 'task_state' },
  { label: '过程经验', value: 'process' },
  { label: '修正反馈', value: 'correction' },
]

/** 记忆类型中文标签映射（展示用）。 */
export const memoryTypeLabels: Record<string, string> = {
  fact: '关键事实',
  preference: '用户偏好',
  task_state: '任务状态',
  process: '过程经验',
  correction: '修正反馈',
}

/** 记忆类型主题色映射（图表/徽标用）。 */
export const memoryTypeColors: Record<string, string> = {
  fact: '#2474cf',
  preference: '#4ba6a0',
  task_state: '#20a47c',
  process: '#5c9bd5',
  correction: '#d86b6b',
}
