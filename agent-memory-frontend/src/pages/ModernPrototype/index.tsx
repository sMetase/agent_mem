import {
  ApiOutlined,
  ApartmentOutlined,
  CheckCircleFilled,
  CloudUploadOutlined,
  DatabaseOutlined,
  DownOutlined,
  FileTextOutlined,
  FilterOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons'
import {
  Badge,
  Card,
  Col,
  Flex,
  Progress,
  Row,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ReactNode } from 'react'
import '@/styles/modern-tokens.css'
import './modern-prototype.css'

const { Text, Title } = Typography

interface MetricCardProps {
  title: string
  value: string
  note: string
  color: string
  icon: ReactNode
  points: number[]
}

function MiniTrend({ points, color }: { points: number[]; color: string }) {
  const max = Math.max(...points)
  const min = Math.min(...points)
  const range = max - min || 1
  const path = points
    .map((point, index) => {
      const x = (index / (points.length - 1)) * 92 + 4
      const y = 29 - ((point - min) / range) * 22
      return `${index === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`
    })
    .join(' ')

  const gradientId = `gradient-${color.replace('#', '')}`

  return (
    <svg className="modern-mini-trend" viewBox="0 0 100 34" aria-hidden="true">
      <defs>
        <linearGradient id={gradientId} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0.05" />
        </linearGradient>
      </defs>
      <path d={path} fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d={`${path} L 96 34 L 4 34 Z`} fill={`url(#${gradientId})`} />
    </svg>
  )
}

function ModernMetricCard({ title, value, note, color, icon, points }: MetricCardProps) {
  return (
    <Card className="modern-metric-card" variant="borderless">
      <Flex justify="space-between" align="flex-start" gap={12}>
        <Flex gap={14} align="center" style={{ flex: 1, minWidth: 0 }}>
          <div className="modern-metric-icon" style={{
            background: `linear-gradient(135deg, ${color}, ${color}dd)`,
          }}>
            {icon}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <Text className="modern-metric-label">{title}</Text>
            <Title level={3} className="modern-metric-value">{value}</Title>
          </div>
        </Flex>
        <div style={{ flexShrink: 0 }}>
          <MiniTrend points={points} color={color} />
        </div>
      </Flex>
      <Text className="modern-metric-note">较昨日 <span style={{ color }}>{note}</span></Text>
    </Card>
  )
}

const metrics: MetricCardProps[] = [
  { title: '接入智能体', value: '128', note: '↑ 6.67%', color: '#0284C7', icon: <RobotOutlined />, points: [4, 8, 7, 12, 10, 18, 15, 23] },
  { title: '业务场景', value: '24', note: '↑ 4.35%', color: '#2A9D6F', icon: <CloudUploadOutlined />, points: [8, 7, 11, 9, 14, 13, 18, 20] },
  { title: '记忆总量', value: '2,486,920', note: '↑ 2.84%', color: '#7C3AED', icon: <DatabaseOutlined />, points: [5, 9, 8, 14, 12, 17, 19, 27] },
  { title: '今日检索调用', value: '83,214', note: '↑ 7.96%', color: '#D97706', icon: <FilterOutlined />, points: [3, 9, 5, 11, 8, 16, 13, 21] },
  { title: '上下文返回成功率', value: '99.2%', note: '↑ 0.3%', color: '#C4612F', icon: <SafetyCertificateOutlined />, points: [10, 9, 13, 12, 15, 14, 18, 20] },
]

const flowSteps = [
  { number: '1', title: '智能体接入与记忆数据写入', description: '接入智能体，导入对话、会话与任务数据', color: '#0284C7', icon: <RobotOutlined /> },
  { number: '2', title: '多层记忆管理', description: '构建记忆模型，管理多层、多类型记忆', color: '#2A9D6F', icon: <DatabaseOutlined /> },
  { number: '3', title: '记忆生成与去重融合', description: '抽取、去重、融合，生成高质量有效记忆', color: '#7C3AED', icon: <ApartmentOutlined /> },
  { number: '4', title: '多信号融合记忆检索', description: '多信号检索与排序，精准定位相关记忆', color: '#D97706', icon: <FilterOutlined /> },
  { number: '5', title: '记忆上下文返回', description: '结构化或文本化返回，注入模型上下文', color: '#C4612F', icon: <FileTextOutlined /> },
]

const agentRows = [
  { key: '1', id: 'A-1023', scene: '物流调度智能体', status: '已接入', time: '2 分钟前', result: '已处理' },
  { key: '2', id: 'A-1008', scene: '客服助手智能体', status: '运行中', time: '5 分钟前', result: '已记录' },
  { key: '3', id: 'A-0991', scene: '订单处理智能体', status: '已接入', time: '12 分钟前', result: '已处理' },
  { key: '4', id: 'A-0887', scene: '营销推荐智能体', status: '运行中', time: '18 分钟前', result: '已记录' },
  { key: '5', id: 'A-0772', scene: '财务分析智能体', status: '正常', time: '35 分钟前', result: '已处理' },
]

const searchRows = [
  { key: '1', type: '历史决策', content: '物流任务的分流确认', score: '0.96', time: '2026-07-16 10:42' },
  { key: '2', type: '用户偏好', content: '优先使用轻量检索策略', score: '0.92', time: '2026-07-16 09:11' },
  { key: '3', type: '任务状态', content: '运输异常处置记录', score: '0.88', time: '2026-07-15 19:46' },
]

const pipelineStages = [
  { label: '原始输入', description: '对话与任务数据', icon: <ApiOutlined />, color: '#0284C7' },
  { label: '语义抽取', description: '偏好、事实、状态', icon: <FilterOutlined />, color: '#2A9D6F' },
  { label: '结构生成', description: '统一记忆单元', icon: <FileTextOutlined />, color: '#7C3AED' },
  { label: '去重识别', description: '相似与冲突检测', icon: <SafetyCertificateOutlined />, color: '#D97706' },
  { label: '融合整理', description: '更新、合并、过滤', icon: <ApartmentOutlined />, color: '#2A9D6F' },
  { label: '有效入库', description: '结构库与向量库', icon: <DatabaseOutlined />, color: '#C4612F' },
]

export default function ModernPrototypePage() {
  return (
    <div className="modern-prototype-page">
      <div className="modern-page-header">
        <div className="modern-eyebrow">MODERN DESIGN SYSTEM PROTOTYPE</div>
        <Title level={1} className="modern-page-title">
          系统<em>总览</em>
        </Title>
        <Text className="modern-page-subtitle">
          面向多智能体业务的记忆管理控制台 · 基于2026年设计趋势的现代化视觉方案
        </Text>
      </div>

      <Space orientation="vertical" size={18} style={{ display: 'flex' }}>
        <div className="modern-metric-grid">
          {metrics.map((metric) => (
            <ModernMetricCard key={metric.title} {...metric} />
          ))}
        </div>

        <Card className="modern-card" title="功能总览" variant="borderless">
          <div className="modern-flow-grid">
            {flowSteps.map((step, index) => (
              <div className="modern-flow-item-wrap" key={step.number}>
                <div className="modern-flow-item" style={{
                  borderColor: `${step.color}40`,
                  background: `linear-gradient(135deg, ${step.color}08, ${step.color}03)`,
                }}>
                  <span className="modern-flow-number" style={{ background: step.color }}>{step.number}</span>
                  <div className="modern-flow-icon" style={{ color: step.color }}>{step.icon}</div>
                  <div>
                    <Text strong>{step.title}</Text>
                    <Text type="secondary">{step.description}</Text>
                  </div>
                </div>
                {index < flowSteps.length - 1 ? (
                  <svg className="modern-flow-arrow" viewBox="0 0 24 24" fill="none">
                    <path d="M5 12h14m0 0l-6-6m6 6l-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                ) : null}
              </div>
            ))}
          </div>
        </Card>

        <Row gutter={[16, 16]}>
          <Col xs={24} xl={10}>
            <Card className="modern-card modern-dashboard-panel" title="智能体接入与数据写入" variant="borderless">
              <Table
                size="small"
                pagination={false}
                dataSource={agentRows}
                columns={[
                  { title: 'Agent ID', dataIndex: 'id', width: 84 },
                  { title: '场景', dataIndex: 'scene' },
                  { title: '接入状态', dataIndex: 'status', render: (value: string) => <Tag color={value === '运行中' ? 'processing' : 'success'}>{value}</Tag> },
                  { title: '最近写入', dataIndex: 'time' },
                  { title: '结果', dataIndex: 'result', render: (value: string) => <Text style={{ color: 'var(--modern-success)' }}>{value}</Text> },
                ]}
              />
            </Card>
          </Col>
          <Col xs={24} md={12} xl={6}>
            <Card className="modern-card modern-dashboard-panel" title="多层记忆管理" variant="borderless">
              <Space orientation="vertical" size={10} style={{ display: 'flex' }}>
                {[
                  ['用户级记忆', '用户偏好、稳定事实', '#0284C7'],
                  ['会话级记忆', '上下文、会话摘要', '#2A9D6F'],
                  ['任务级记忆', '目标、进展、待办、结果', '#D97706'],
                  ['智能体状态记忆', '历史操作、流程轨迹', '#7C3AED'],
                ].map(([title, description, color]) => (
                  <div className="modern-memory-layer" key={title}>
                    <span style={{ background: color }} />
                    <div><Text strong>{title}</Text><Text type="secondary">{description}</Text></div>
                  </div>
                ))}
                <Flex wrap gap={6} className="modern-memory-type-tags">
                  <Tag color="blue">用户偏好</Tag><Tag color="green">关键事实</Tag><Tag color="gold">任务状态</Tag><Tag color="purple">历史决策</Tag>
                </Flex>
              </Space>
            </Card>
          </Col>
          <Col xs={24} md={12} xl={8}>
            <Card className="modern-card modern-dashboard-panel" title="记忆生成与去重融合" variant="borderless">
              <div className="modern-pipeline-workflow">
                {[pipelineStages.slice(0, 3), pipelineStages.slice(3)].map((stages, laneIndex) => (
                  <div className="modern-pipeline-lane-wrap" key={laneIndex === 0 ? 'generation' : 'governance'}>
                    <div className="modern-pipeline-lane-label">{laneIndex === 0 ? '生成阶段' : '治理阶段'}</div>
                    <div className="modern-pipeline-lane">
                      {stages.map((stage, index) => (
                        <div className="modern-pipeline-stage-wrap" key={stage.label}>
                          <div className="modern-pipeline-stage" style={{
                            borderColor: `${stage.color}30`,
                            background: `linear-gradient(180deg, ${stage.color}10, ${stage.color}02)`,
                          }}>
                            <span style={{ color: stage.color }}>{stage.icon}</span>
                            <Text strong>{stage.label}</Text>
                            <Text type="secondary">{stage.description}</Text>
                          </div>
                          {index < stages.length - 1 ? (
                            <div className="modern-pipeline-connector">
                              <div className="modern-pulse-dot" />
                            </div>
                          ) : null}
                        </div>
                      ))}
                    </div>
                    {laneIndex === 0 ? <div className="modern-pipeline-turn"><DownOutlined /></div> : null}
                  </div>
                ))}
              </div>
              <div className="modern-pipeline-metrics">
                <div><Text type="secondary">今日生成</Text><strong>12,480</strong></div>
                <div><Text type="secondary">去重率</Text><strong style={{ color: 'var(--modern-success)' }}>31%</strong></div>
                <div><Text type="secondary">融合成功率</Text><strong style={{ color: 'var(--modern-warning)' }}>94%</strong></div>
                <div><Text type="secondary">低价值过滤</Text><strong>2,103</strong></div>
              </div>
            </Card>
          </Col>
        </Row>

        <Row gutter={[16, 16]}>
          <Col xs={24} xl={10}>
            <Card className="modern-card modern-dashboard-panel" title="多信号融合检索" variant="borderless">
              <Flex gap={8} wrap className="modern-search-summary">
                <Tag color="blue">语义向量</Tag><Tag color="cyan">关键词</Tag><Tag color="gold">元数据过滤</Tag><Tag color="purple">融合排序</Tag><Tag>Top-K 3</Tag>
              </Flex>
              <Table
                size="small"
                pagination={false}
                dataSource={searchRows}
                columns={[
                  { title: '类型', dataIndex: 'type', render: (value: string) => <Badge color="var(--modern-primary)" text={value} /> },
                  { title: '记忆摘要', dataIndex: 'content' },
                  { title: '相关度', dataIndex: 'score', width: 70 },
                  { title: '时间', dataIndex: 'time', width: 138 },
                ]}
              />
            </Card>
          </Col>
          <Col xs={24} xl={7}>
            <Card className="modern-card modern-dashboard-panel" title="上下文返回预览" variant="borderless">
              <Flex gap={8} className="modern-context-tabs"><Text strong>JSON 返回</Text><Text type="secondary">文本片段返回</Text></Flex>
              <pre className="modern-context-code">{`{
  "memory_context": "用户偏好高可靠方案",
  "user_id": "U-2048",
  "scene": "物流调度",
  "score": 0.96,
  "status": "active"
}`}</pre>
            </Card>
          </Col>
          <Col xs={24} xl={7}>
            <Row gutter={[16, 16]}>
              <Col xs={24} sm={12} xl={24}>
                <Card className="modern-card modern-compact-chart" title="记忆增长趋势（近 7 天）" variant="borderless">
                  <div className="modern-line-chart"><MiniTrend points={[4, 7, 8, 12, 16, 21, 29]} color="var(--modern-primary)" /></div>
                </Card>
              </Col>
              <Col xs={24} sm={12} xl={24}>
                <Card className="modern-card modern-compact-chart" title="最近告警与任务" variant="borderless">
                  <Space orientation="vertical" size={9} style={{ display: 'flex' }}>
                    <Flex justify="space-between"><Text><Badge status="warning" /> 检索响应时间短时升高</Text><Text type="secondary">2 分钟前</Text></Flex>
                    <Flex justify="space-between"><Text><Badge status="processing" /> 记忆批量导入任务执行中</Text><Text type="secondary">15 分钟前</Text></Flex>
                    <Flex justify="space-between"><Text><CheckCircleFilled style={{ color: 'var(--modern-success)' }} /> 智能体 A-0772 配置已同步</Text><Text type="secondary">1 小时前</Text></Flex>
                  </Space>
                </Card>
              </Col>
            </Row>
          </Col>
        </Row>

        <Row gutter={[16, 16]}>
          <Col xs={24} lg={12}>
            <Card className="modern-card modern-compact-chart" title="检索方式占比（今日）" variant="borderless">
              {[['语义向量检索', 48.6, 'var(--modern-info)'], ['关键词检索', 24.1, 'var(--modern-success)'], ['元数据过滤', 15.3, 'var(--modern-warning)'], ['融合检索', 12, 'var(--modern-primary)']].map(([label, percent, color]) => (
                <Flex key={String(label)} align="center" gap={12} className="modern-bar-line">
                  <Text>{label}</Text>
                  <Progress percent={Number(percent)} showInfo={false} strokeColor={String(color)} />
                  <Text>{percent}%</Text>
                </Flex>
              ))}
            </Card>
          </Col>
        </Row>
      </Space>
    </div>
  )
}
