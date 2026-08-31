import type { ReactNode } from 'react'
import { Empty, Space, Typography } from 'antd'

interface EmptyStateProps {
  title?: string
  description: string
  action?: ReactNode
}

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <Space orientation="vertical" size={12} style={{ display: 'flex', alignItems: 'center' }}>
      <Empty description={description} image={Empty.PRESENTED_IMAGE_SIMPLE} />
      {title ? (
        <Typography.Text strong style={{ marginTop: -12 }}>
          {title}
        </Typography.Text>
      ) : null}
      {action}
    </Space>
  )
}
