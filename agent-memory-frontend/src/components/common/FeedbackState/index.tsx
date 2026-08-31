import type { ReactNode } from 'react'
import { Result, Space, Spin, Typography } from 'antd'
import { EmptyState } from '@/components/common/EmptyState'
import { PageSection } from '@/components/common/PageSection'
import { getErrorMessage } from '@/utils/error'

type FeedbackStatus = 'loading' | 'empty' | 'error'

interface FeedbackStateProps {
  status: FeedbackStatus
  title?: string
  description?: string
  action?: ReactNode
  error?: unknown
}

export function FeedbackState({
  status,
  title,
  description,
  action,
  error,
}: FeedbackStateProps) {
  if (status === 'loading') {
    return (
      <PageSection>
        <Space
          align="center"
          orientation="vertical"
          size={12}
          style={{ display: 'flex', justifyContent: 'center', minHeight: 220 }}
        >
          <Spin size="large" />
          <Typography.Text type="secondary">
            {description ?? '正在加载内容，请稍候。'}
          </Typography.Text>
        </Space>
      </PageSection>
    )
  }

  if (status === 'empty') {
    return (
      <PageSection>
        <EmptyState
          title={title}
          description={description ?? '当前还没有可展示的数据。'}
          action={action}
        />
      </PageSection>
    )
  }

  return (
    <PageSection>
      <Result
        status="error"
        title={title ?? '加载失败'}
        subTitle={getErrorMessage(error, description ?? '请稍后重试。')}
        extra={action}
      />
    </PageSection>
  )
}
