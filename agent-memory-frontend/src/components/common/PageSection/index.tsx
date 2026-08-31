import { Card, Grid } from 'antd'
import type { CardProps } from 'antd'

export function PageSection({ children, styles, ...props }: CardProps) {
  const screens = Grid.useBreakpoint()

  return (
    <Card
      variant="borderless"
      styles={(info) => {
        const resolvedStyles = typeof styles === 'function' ? styles(info) : styles

        return {
          ...resolvedStyles,
          body: {
            padding: screens.md === true ? 24 : 16,
            ...resolvedStyles?.body,
          },
        }
      }}
      {...props}
    >
      {children}
    </Card>
  )
}
