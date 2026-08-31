import { Button, Card, Flex, Space, Typography } from 'antd'
import type { MemoryItem } from '@/api/types'
import { StatusTag } from '@/components/common'

interface MemoryCardProps {
  memory: MemoryItem
  onEdit?: (memory: MemoryItem) => void
  onDelete?: (memory: MemoryItem) => void
}

export function MemoryCard({ memory, onEdit, onDelete }: MemoryCardProps) {
  return (
    <Card variant="borderless">
      <Space orientation="vertical" size={8} style={{ display: 'flex' }}>
        <Flex justify="space-between" align="flex-start" gap={12} wrap>
          <Space wrap>
            <StatusTag value={memory.memory_type ?? 'unknown'} />
            {memory.scene_id ? (
              <Typography.Text type="secondary">scene: {memory.scene_id}</Typography.Text>
            ) : null}
            {typeof memory.relevance_score === 'number' ? (
              <Typography.Text type="secondary">
                相关度: {(memory.relevance_score * 100).toFixed(1)}%
              </Typography.Text>
            ) : null}
          </Space>
          <Space>
            {onEdit ? <Button size="small" onClick={() => onEdit(memory)}>编辑</Button> : null}
            {onDelete ? <Button size="small" danger onClick={() => onDelete(memory)}>删除</Button> : null}
          </Space>
        </Flex>
        <Typography.Paragraph style={{ margin: 0 }}>{memory.content}</Typography.Paragraph>
        {memory.updated_at || memory.created_at ? (
          <Typography.Text type="secondary">
            {memory.updated_at ? `更新于 ${memory.updated_at}` : `创建于 ${memory.created_at}`}
          </Typography.Text>
        ) : null}
      </Space>
    </Card>
  )
}
