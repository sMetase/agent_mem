import { Card, Col, Flex, Row, Typography } from 'antd'

const { Text } = Typography

export interface LevelStat {
  label: string
  value: string
  hint?: string
  color?: string
}

interface LevelStatCardsProps {
  stats: LevelStat[]
}

export function LevelStatCards({ stats }: LevelStatCardsProps) {
  return (
    <Row gutter={[12, 12]}>
      {stats.map((stat) => (
        <Col xs={12} sm={8} xl={6} key={stat.label}>
          <Card className="console-card result-stat" variant="borderless">
            <Flex vertical gap={4}>
              <Text type="secondary">{stat.label}</Text>
              <strong style={{ color: stat.color ?? '#1677ff', fontSize: 22, lineHeight: 1.2 }}>{stat.value}</strong>
              {stat.hint ? <Text type="secondary" style={{ fontSize: 12 }}>{stat.hint}</Text> : null}
            </Flex>
          </Card>
        </Col>
      ))}
    </Row>
  )
}
