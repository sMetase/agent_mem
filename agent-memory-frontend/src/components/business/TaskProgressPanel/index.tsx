import { Card, Descriptions } from 'antd'
import type { TaskProgressResult } from '@/api/types'

export function TaskProgressPanel({ progress }: { progress: TaskProgressResult | null }) {
  return (
    <Card variant="borderless" title="任务进度">
      <Descriptions column={1} size="small">
        <Descriptions.Item label="任务状态">{progress?.status ?? '未查询'}</Descriptions.Item>
        <Descriptions.Item label="已完成项">{progress?.completed_count ?? 0}</Descriptions.Item>
        <Descriptions.Item label="待办项">{progress?.pending_count ?? 0}</Descriptions.Item>
        <Descriptions.Item label="关联记忆数">
          {progress?.related_memory_count ?? 0}
        </Descriptions.Item>
      </Descriptions>
    </Card>
  )
}
