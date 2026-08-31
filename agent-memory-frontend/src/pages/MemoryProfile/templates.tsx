import { Column, Line, Radar } from '@ant-design/plots'
import {
  Card,
  Col,
  Descriptions,
  Empty,
  Flex,
  Row,
  Space,
  Statistic,
  Tag,
  Typography,
} from 'antd'
import type { MemoryProfileResult, ProfileTypeDistItem, ProfileVisualData } from '@/api/types'
import { memoryTypeLabels } from '@/constants/memory'
import type { ProfileTemplateKind } from '@/pages/MemoryProfile/visual'

const { Text, Title } = Typography

export interface ProfileTemplateProps {
  profile: MemoryProfileResult
  visual: ProfileVisualData
  userId: string
  generatedAt?: string
}

/* ------------------------------ 图表组件 ------------------------------ */

function ProfileRadarChart({ data }: { data?: ProfileVisualData['radar'] }) {
  if (!data?.length) return null
  return <Radar data={data} xField="dimension" yField="score" height={240} />
}

function TypeDistChart({ data }: { data?: ProfileTypeDistItem[] }) {
  if (!data?.length) return null
  const items = data.map((item) => ({
    type: memoryTypeLabels[item.type] ?? item.type,
    count: item.count,
  }))
  return <Column data={items} xField="type" yField="count" height={220} />
}

function TrendChart({ data }: { data?: ProfileVisualData['trend'] }) {
  if (!data?.length) return null
  return <Line data={data} xField="date" yField="count" height={200} />
}

function TagCloud({ tags }: { tags?: string[] }) {
  if (!tags?.length) return null
  return (
    <Flex wrap gap={6}>
      {tags.map((tag) => <Tag key={tag} color="blue">{tag}</Tag>)}
    </Flex>
  )
}

function PersonaSummary({ persona }: { persona?: string }) {
  if (!persona) return <Empty description="暂无画像内容（当前用户偏好/事实记忆不足）。" />
  return <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{persona}</Typography.Paragraph>
}

function totalMemories(profile: MemoryProfileResult, visual: ProfileVisualData): number {
  return profile.stats?.total_memories
    ?? visual.memoryTypeDist?.reduce((sum, item) => sum + item.count, 0)
    ?? 0
}

/* ------------------------------ 模板一：数据看板 ------------------------------ */

function DashboardTemplate({ profile, visual }: ProfileTemplateProps) {
  return (
    <Space orientation="vertical" size={14} style={{ display: 'flex' }}>
      <Card className="console-card" variant="borderless" title="画像总结">
        <PersonaSummary persona={profile.persona} />
      </Card>
      <Row gutter={[14, 14]}>
        <Col xs={24} lg={9}>
          <Card className="console-card" variant="borderless" title="画像维度评分">
            <ProfileRadarChart data={visual.radar} />
          </Card>
        </Col>
        <Col xs={24} lg={9}>
          <Card className="console-card" variant="borderless" title="记忆类型分布">
            <TypeDistChart data={visual.memoryTypeDist} />
          </Card>
        </Col>
        <Col xs={24} lg={6}>
          <Card className="console-card" variant="borderless" title="画像统计">
            <Space orientation="vertical" size={16} style={{ display: 'flex' }}>
              <Statistic title="记忆总数" value={totalMemories(profile, visual)} />
              <Statistic title="有效记忆" value={profile.stats?.active_memories ?? '—'} />
              <Statistic title="高频关键词" value={visual.tags?.length ?? 0} />
            </Space>
          </Card>
        </Col>
      </Row>
      <Row gutter={[14, 14]}>
        <Col xs={24} lg={14}>
          <Card className="console-card" variant="borderless" title="记忆时间趋势">
            <TrendChart data={visual.trend} />
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card className="console-card" variant="borderless" title="高频关键词">
            <TagCloud tags={visual.tags} />
          </Card>
        </Col>
      </Row>
    </Space>
  )
}

/* ------------------------------ 模板二：极简卡片 ------------------------------ */

function MinimalTemplate({ profile, visual }: ProfileTemplateProps) {
  return (
    <Space orientation="vertical" size={14} style={{ display: 'flex' }}>
      <Card className="console-card" variant="borderless" title="用户画像">
        <PersonaSummary persona={profile.persona} />
      </Card>
      <Card className="console-card" variant="borderless" title="记忆概览">
        <Row gutter={16}>
          <Col span={12}><Statistic title="记忆总数" value={totalMemories(profile, visual)} /></Col>
          <Col span={12}><Statistic title="有效记忆" value={profile.stats?.active_memories ?? '—'} /></Col>
        </Row>
        {visual.memoryTypeDist?.length ? (
          <Flex wrap gap={6} style={{ marginTop: 14 }}>
            {visual.memoryTypeDist.map((item) => (
              <Tag key={item.type}>{memoryTypeLabels[item.type] ?? item.type} {item.count}</Tag>
            ))}
          </Flex>
        ) : null}
      </Card>
      <Card className="console-card" variant="borderless" title="高频关键词">
        <TagCloud tags={visual.tags} />
      </Card>
    </Space>
  )
}

/* ------------------------------ 模板三：报告式（打印友好） ------------------------------ */

function ReportTemplate({ profile, visual, userId, generatedAt }: ProfileTemplateProps) {
  return (
    <Space orientation="vertical" size={14} style={{ display: 'flex' }}>
      <div>
        <Title level={4} style={{ marginBottom: 4 }}>用户画像报告</Title>
        <Text type="secondary">
          用户：{userId}
          {generatedAt ? ` · 生成时间：${generatedAt}` : ''}
          {profile.scene_id ? ` · 场景：${profile.scene_id}` : ''}
        </Text>
      </div>
      <Card variant="borderless" title="一、用户基础信息">
        <Descriptions column={{ xs: 1, sm: 2 }} size="small">
          <Descriptions.Item label="用户 ID">{userId || '-'}</Descriptions.Item>
          <Descriptions.Item label="所属场景">{profile.scene_id || '-'}</Descriptions.Item>
          <Descriptions.Item label="变更场景数">{profile.changed_scenes ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="记忆总数">{totalMemories(profile, visual)}</Descriptions.Item>
          <Descriptions.Item label="有效记忆">{profile.stats?.active_memories ?? '-'}</Descriptions.Item>
        </Descriptions>
      </Card>
      <Card variant="borderless" title="二、画像总结">
        <PersonaSummary persona={profile.persona} />
      </Card>
      <Row gutter={[14, 14]}>
        <Col xs={24} lg={12}>
          <Card variant="borderless" title="画像维度评分">
            <ProfileRadarChart data={visual.radar} />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card variant="borderless" title="记忆类型分布">
            <TypeDistChart data={visual.memoryTypeDist} />
          </Card>
        </Col>
      </Row>
      <Card variant="borderless" title="三、记忆时间趋势">
        <TrendChart data={visual.trend} />
      </Card>
      <Card variant="borderless" title="四、高频关键词">
        <TagCloud tags={visual.tags} />
      </Card>
    </Space>
  )
}

/* ------------------------------ 模板分发 ------------------------------ */

export function ProfileTemplate({ kind, ...props }: ProfileTemplateProps & { kind: ProfileTemplateKind }) {
  if (kind === 'minimal') return <MinimalTemplate {...props} />
  if (kind === 'report') return <ReportTemplate {...props} />
  return <DashboardTemplate {...props} />
}
