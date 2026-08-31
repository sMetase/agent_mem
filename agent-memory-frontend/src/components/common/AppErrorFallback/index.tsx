import type { ReactNode } from 'react'
import { Result } from 'antd'
import { PageSection } from '@/components/common/PageSection'
import { getErrorMessage } from '@/utils/error'

interface AppErrorFallbackProps {
  title?: string
  subtitle?: string
  error?: unknown
  extra?: ReactNode
}

export function AppErrorFallback({
  title = '页面暂时不可用',
  subtitle,
  error,
  extra,
}: AppErrorFallbackProps) {
  return (
    <PageSection>
      <Result
        status="error"
        title={title}
        subTitle={subtitle ?? getErrorMessage(error, '请稍后重试。')}
        extra={extra}
      />
    </PageSection>
  )
}
