import { Skeleton } from 'antd'
import { PageSection } from '@/components/common/PageSection'

interface LoadingBlockProps {
  rows?: number
}

export function LoadingBlock({ rows = 4 }: LoadingBlockProps) {
  return (
    <PageSection>
      <Skeleton active paragraph={{ rows }} />
    </PageSection>
  )
}
