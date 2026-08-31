import type { ReactNode } from 'react'
import { Flex, Grid, Space, Typography } from 'antd'
import { PageSection } from '@/components/common/PageSection'

interface PageContainerProps {
  title: string
  titleExtra?: ReactNode
  description?: string
  extra?: ReactNode
  children: ReactNode
}

export function PageContainer({
  title,
  titleExtra,
  description,
  extra,
  children,
}: PageContainerProps) {
  const screens = Grid.useBreakpoint()
  const isCompact = screens.md !== true

  return (
    <Space orientation="vertical" size={16} style={{ display: 'flex' }}>
      <PageSection>
        <Flex
          vertical={isCompact}
          align={isCompact ? 'stretch' : 'flex-start'}
          justify="space-between"
          gap={12}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <Typography.Title level={3} style={{ margin: 0 }}>
              <span>{title}</span>
              {titleExtra ? (
                <span style={{ display: 'inline-flex', marginInlineStart: 8, verticalAlign: 'middle' }}>
                  {titleExtra}
                </span>
              ) : null}
            </Typography.Title>
            {description ? (
              <Typography.Paragraph type="secondary" style={{ margin: '8px 0 0' }}>
                {description}
              </Typography.Paragraph>
            ) : null}
          </div>
          {extra ? <div className="page-container-extra">{extra}</div> : null}
        </Flex>
      </PageSection>
      {children}
    </Space>
  )
}
