import {
  CloudUploadOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  FilterOutlined,
  PlusOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Badge,
  Card,
  Col,
  Empty,
  Flex,
  Row,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import type { CSSProperties, ReactNode } from 'react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { getAdminDashboard, getAdminStats } from '@/api/modules/admin'
import { memoryTypeColors, memoryTypeLabels } from '@/constants/memory'
import { getAdminApiLogs } from '@/api/modules/monitoring'
import type {
  AdminDashboardResult,
  AdminRecentAgentItem,
  AdminRecentTaskItem,
  AdminStatsResult,
} from '@/api/types'
import { formatDashboardNumber, formatDashboardPercent, getAlertPresentationStatus, getAgentResultLabel, getAgentSceneLabel, serializeLatestContext } from './dashboard-adapter'
import { RealTimeMonitorCard } from './RealTimeMonitorCard'

const { Text, Title } = Typography

const dateTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

interface MetricCardProps {
  title: string
  value: string
  color: string
  icon: ReactNode
}

interface AgentTableRow {
  key: string
  id: string
  scene: string
  status: string
  statusColor: 'default' | 'processing' | 'success' | 'warning' | 'error'
  time: string
  result: string
}

function formatDateTime(value?: string | null) {
  if (!value) return '未返回'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : dateTimeFormatter.format(date)
}

function formatMetricValue(value: number | null | undefined, loading: boolean, formatter: (value: number | null | undefined) => string) {
  if (loading && value == null) return '加载中…'
  return formatter(value)
}

function MiniTrend({ points, color }: { points?: number[]; color: string }) {
  const validPoints = points?.filter((point) => Number.isFinite(point)) ?? []
  if (validPoints.length < 2) {
    return <Text type="secondary" className="mini-trend-empty">暂无趋势数据</Text>
  }

  const max = Math.max(...validPoints)
  const min = Math.min(...validPoints)
  const range = max - min || 1
  const path = validPoints
    .map((point, index) => {
      const x = (index / (validPoints.length - 1)) * 92 + 4
      const y = 29 - ((point - min) / range) * 22
      return `${index === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`
    })
    .join(' ')

  return (
    <svg className="mini-trend" viewBox="0 0 100 34" aria-label="趋势图">
      <path d={path} fill="none" stroke={color} strokeWidth="2.2" strokeLinecap="round" />
      <path d={`${path} L 96 34 L 4 34 Z`} fill={color} opacity="0.08" />
    </svg>
  )
}

function MetricCard({ title, value, color, icon }: MetricCardProps) {
  return (
    <Card
      className="console-card metric-card"
      variant="borderless"
      style={{ '--metric-color': color } as CSSProperties}
    >
      <Flex gap={14} align="center" className="metric-card-content">
        <div className="metric-icon" style={{ color, background: `${color}16` }}>{icon}</div>
        <div className="metric-copy">
          <Text type="secondary" className="metric-label">{title}</Text>
          <Title level={3} className="metric-value">{value}</Title>
        </div>
      </Flex>
      <span className="metric-card-accent" aria-hidden="true" />
    </Card>
  )
}

const flowSteps = [
  { number: '1', title: '智能体接入与记忆数据写入', description: '接入智能体，导入对话、会话与任务数据', color: '#1677ff', icon: <RobotOutlined /> },
  { number: '2', title: '多层记忆管理', description: '构建记忆模型，管理多层、多类型记忆', color: '#20a47c', icon: <DatabaseOutlined /> },
  { number: '3', title: '记忆上下文返回', description: '结构化或文本化返回，注入模型上下文', color: '#2471cf', icon: <FileTextOutlined /> },
]

function agentStatus(value?: string | null) {
  const normalized = value?.toLowerCase()
  if (normalized === 'active') return { label: '运行中', color: 'processing' as const }
  if (normalized === 'inactive' || normalized === 'disabled') return { label: '已停用', color: 'default' as const }
  if (normalized === 'error' || normalized === 'failed') return { label: '异常', color: 'error' as const }
  return { label: value?.trim() || '未返回', color: 'default' as const }
}

function taskStatusLabel(value?: string | null) {
  if (value === 'pending') return '待处理'
  if (value === 'in_progress') return '执行中'
  if (value === 'completed') return '已完成'
  return value?.trim() || '未返回'
}

function alertStatusLabel(value: ReturnType<typeof getAlertPresentationStatus>) {
  if (value === 'current') return { label: '当前告警', color: 'red' as const }
  if (value === 'resolved') return { label: '已恢复', color: 'green' as const }
  return { label: '历史告警', color: 'orange' as const }
}

function isFailedApiLog(log: { response_code: number; error_code?: string | null }) {
  return log.response_code >= 400 || Boolean(log.error_code)
}

function buildAgentRows(agents: AdminRecentAgentItem[]): AgentTableRow[] {
  return agents.map((agent, index) => {
    const status = agentStatus(agent.status)
    return {
      key: agent.agent_id || String(index),
      id: agent.agent_id || '未返回',
      scene: getAgentSceneLabel(agent),
      status: status.label,
      statusColor: status.color,
      time: formatDateTime(agent.last_write_at),
      result: getAgentResultLabel(agent),
    }
  })
}

const agentColumns = [
  {
    title: 'Agent ID',
    dataIndex: 'id',
    width: 250,
    render: (value: string) => (
      <Tooltip title={value === '未返回' ? '后端未返回 Agent ID' : value}>
        <Typography.Text ellipsis={{ tooltip: value }} copyable={value === '未返回' ? false : { text: value }}>
          {value}
        </Typography.Text>
      </Tooltip>
    ),
  },
  {
    title: '场景',
    dataIndex: 'scene',
    width: 210,
    render: (value: string) => <Typography.Text type={value === '未返回' ? 'secondary' : undefined}>{value}</Typography.Text>,
  },
  {
    title: '接入状态',
    dataIndex: 'status',
    width: 110,
    render: (value: string, row: AgentTableRow) => <Tag color={row.statusColor}>{value}</Tag>,
  },
  { title: '最近写入', dataIndex: 'time', width: 170 },
  {
    title: '结果',
    dataIndex: 'result',
    width: 150,
    render: (value: string) => <Typography.Text type={value === '未返回' ? 'secondary' : undefined}>{value}</Typography.Text>,
  },
]

interface OverviewLoadState {
  statsError: unknown
  dashboardError: unknown
  apiLogsError: unknown
}

export default function OverviewPage() {
  const [stats, setStats] = useState<AdminStatsResult | null>(null)
  const [dashboard, setDashboard] = useState<AdminDashboardResult | null>(null)
  const [currentApiLogs, setCurrentApiLogs] = useState<Array<{ response_code: number; error_code?: string | null }> | null>(null)
  const [loadState, setLoadState] = useState<OverviewLoadState>({ statsError: null, dashboardError: null, apiLogsError: null })
  const [loading, setLoading] = useState(true)

  const loadOverview = useCallback(async () => {
    setLoading(true)
    setLoadState({ statsError: null, dashboardError: null, apiLogsError: null })

    const [statsResult, dashboardResult, apiLogsResult] = await Promise.allSettled([
      getAdminStats(),
      getAdminDashboard({ hours: 24, trendDays: 7 }),
      getAdminApiLogs({ hours: 1, page: 1, pageSize: 20 }),
    ])

    if (statsResult.status === 'fulfilled') setStats(statsResult.value)
    else setLoadState((current) => ({ ...current, statsError: statsResult.reason }))

    if (dashboardResult.status === 'fulfilled') setDashboard(dashboardResult.value)
    else setLoadState((current) => ({ ...current, dashboardError: dashboardResult.reason }))

    if (apiLogsResult.status === 'fulfilled') setCurrentApiLogs(apiLogsResult.value.items)
    else setLoadState((current) => ({ ...current, apiLogsError: apiLogsResult.reason }))

    setLoading(false)
  }, [])

  useEffect(() => {
    void loadOverview()
  }, [loadOverview])

  const summary = dashboard?.summary
  const memoryTotal = summary?.memory_count
  const memoryTrend = dashboard?.memory_trend ?? []
  const latestMemoryTrend = memoryTrend.at(-1)
  const latestAdded = latestMemoryTrend?.added
  const hasLatestAdded = latestAdded !== undefined && latestAdded !== null
  const memoryDistribution = dashboard?.memory_type_distribution ?? []
  const agentRows = useMemo(() => buildAgentRows(dashboard?.recent_agents ?? []), [dashboard])
  const contextPreview = serializeLatestContext(dashboard?.latest_context)
  const hasLoadError = Boolean(loadState.statsError || loadState.dashboardError || loadState.apiLogsError)
  const currentFailureCount = currentApiLogs?.filter(isFailedApiLog).length ?? 0
  const currentStatus = currentApiLogs === null
    ? { badge: 'default' as const, label: '当前状态待确认' }
    : currentFailureCount > 0
      ? { badge: 'error' as const, label: `最近 1 小时有 ${currentFailureCount} 次失败调用` }
      : { badge: 'success' as const, label: '最近 1 小时未发现失败调用' }

  const metrics: MetricCardProps[] = [
    {
      title: '接入智能体',
      value: formatMetricValue(summary?.agent_count ?? stats?.total_agents, loading, formatDashboardNumber),
      color: '#1677ff',
      icon: <RobotOutlined />,
    },
    {
      title: '业务场景',
      value: formatMetricValue(summary?.scene_count, loading, formatDashboardNumber),
      color: '#22a884',
      icon: <CloudUploadOutlined />,
    },
    {
      title: '记忆总量',
      value: formatMetricValue(memoryTotal, loading, formatDashboardNumber),
      color: '#7b61d1',
      icon: <DatabaseOutlined />,
    },
    {
      title: '近 24 小时检索调用',
      value: formatMetricValue(summary?.retrieval_count, loading, formatDashboardNumber),
      color: '#e99a21',
      icon: <FilterOutlined />,
    },
    {
      title: '上下文返回成功率',
      value: formatMetricValue(summary?.context_success_rate, loading, formatDashboardPercent),
      color: '#246fd3',
      icon: <SafetyCertificateOutlined />,
    },
  ]

  return (
    <Space orientation="vertical" size={14} style={{ display: 'flex' }} className="overview-page">
      {!loading && hasLoadError ? (
        <Alert
          type="warning"
          showIcon
          message="部分总览数据加载失败"
          description="页面仅展示已成功返回的数据；请检查管理员权限和后端聚合接口。"
        />
      ) : null}

      <div className="metric-grid">
        {metrics.map((metric) => <MetricCard key={metric.title} {...metric} />)}
      </div>

      <RealTimeMonitorCard />

      <Card className="console-card" title="功能总览" variant="borderless">
        <div className="flow-grid">
          {flowSteps.map((step, index) => (
            <div className="flow-item-wrap" key={step.number}>
              <div className="flow-item" style={{ borderColor: `${step.color}55`, background: `${step.color}08` }}>
                <span className="flow-number" style={{ background: step.color }}>{step.number}</span>
                <div className="flow-icon" style={{ color: step.color }}>{step.icon}</div>
                <div>
                  <Text strong>{step.title}</Text>
                  <Text type="secondary">{step.description}</Text>
                </div>
              </div>
              {index < flowSteps.length - 1 ? <span className="flow-arrow">→</span> : null}
            </div>
          ))}
        </div>
      </Card>

      <Row gutter={[12, 12]}>
        <Col xs={24}>
          <Card className="console-card dashboard-panel" title="智能体接入与数据写入" variant="borderless">
            <div className="overview-table-scroll">
              <Table<AgentTableRow>
                className="overview-agent-table"
                size="small"
                pagination={false}
                loading={loading}
                dataSource={agentRows}
                columns={agentColumns}
                tableLayout="fixed"
                scroll={{ x: 890 }}
                locale={{ emptyText: loading ? '正在加载智能体记录…' : '暂未返回智能体记录。' }}
              />
            </div>
          </Card>
        </Col>
      </Row>

      <Row gutter={[12, 12]}>
        <Col xs={24} xl={12}>
          <Card className="console-card dashboard-panel" title="多层记忆管理" variant="borderless">
            {memoryDistribution.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂未返回记忆类型分布。" />
            ) : (
              <Space orientation="vertical" size={10} style={{ display: 'flex' }}>
                {memoryDistribution.slice(0, 7).map((item) => (
                  <div className="memory-distribution-row" key={item.memory_type}>
                    <Flex justify="space-between" gap={10}>
                      <Text>{memoryTypeLabels[item.memory_type] ?? item.memory_type}</Text>
                      <Text type="secondary">{formatDashboardNumber(item.count)} · {formatDashboardPercent(item.ratio)}</Text>
                    </Flex>
                    <div className="memory-distribution-track">
                      <span style={{ width: `${Math.max(0, Math.min(100, item.ratio * 100))}%`, background: memoryTypeColors[item.memory_type] ?? '#7b61d1' }} />
                    </div>
                  </div>
                ))}
              </Space>
            )}
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card className="console-card dashboard-panel" title="记忆增长趋势（近 7 天）" variant="borderless">
            <div className="overview-trend-main">
              <div className="overview-trend-total">
                <div className="overview-trend-eyebrow">
                  <span className="overview-trend-eyebrow-dot" aria-hidden="true" />
                  <Text>累计记忆总量</Text>
                </div>
                <Title level={2} className="overview-trend-total-value">
                  {formatMetricValue(memoryTotal, loading, formatDashboardNumber)}
                </Title>
                <Text type="secondary" className="overview-trend-date">
                  {latestMemoryTrend?.date ? `统计截至 ${latestMemoryTrend.date}` : '暂无趋势日期'}
                </Text>
              </div>
              <div className="overview-trend-chart" aria-label="近 7 天记忆累计趋势">
                <Flex justify="space-between" align="center" className="overview-trend-chart-heading">
                  <Text strong>累计趋势</Text>
                  <Text type="secondary">近 7 天</Text>
                </Flex>
                <MiniTrend points={memoryTrend.map((item) => item.total)} color="#2676ce" />
              </div>
            </div>
            <div className="overview-trend-divider" aria-hidden="true" />
            <div className={`overview-trend-addition${hasLatestAdded ? '' : ' is-empty'}`}>
              <div className="overview-trend-addition-icon" aria-hidden="true">
                <PlusOutlined />
              </div>
              <div className="overview-trend-addition-copy">
                <Text strong className="overview-trend-addition-label">最近一天新增</Text>
                <Text type="secondary" className="overview-trend-addition-meta">
                  {hasLatestAdded && latestMemoryTrend?.date ? `统计日 ${latestMemoryTrend.date}` : '后端暂未返回新增量'}
                </Text>
              </div>
              <div className="overview-trend-addition-value" aria-label="最近一天新增记忆条数">
                <strong>{hasLatestAdded ? formatDashboardNumber(latestAdded) : '—'}</strong>
                {hasLatestAdded ? <span>条</span> : null}
              </div>
            </div>
          </Card>
        </Col>
      </Row>

      <Row gutter={[12, 12]}>
        <Col xs={24} xl={12}>
          <Card className="console-card dashboard-panel" title="上下文返回预览" variant="borderless">
            {contextPreview ? (
              <pre className="context-code">{contextPreview}</pre>
            ) : (
              <div className="context-contract-empty">
                <FileTextOutlined />
                <Text strong>暂无最近上下文</Text>
                <Text type="secondary">当前 Dashboard 响应未提供 `latest_context`；前端无法从现有聚合结果还原最近一次上下文，请后端补充该字段或提供最新上下文查询接口。</Text>
              </div>
            )}
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card className="console-card dashboard-panel" title="当前状态与历史告警" variant="borderless">
            <Space orientation="vertical" size={10} style={{ display: 'flex' }}>
              <Flex align="center" gap={8}>
                <Badge status={currentStatus.badge} />
                <Text strong>{currentStatus.label}</Text>
              </Flex>
              <Text type="secondary">当前状态基于最近 1 小时接口日志；下面的记录单独标记为历史/当前，不将历史告警当作当前故障。</Text>
              {(dashboard?.recent_alerts ?? []).slice(0, 4).map((alert, index) => {
                const presentation = alertStatusLabel(getAlertPresentationStatus(alert))
                return (
                  <Flex justify="space-between" align="flex-start" gap={10} key={`${alert.trace_id ?? alert.occurred_at ?? 'alert'}-${index}`}>
                    <Flex gap={8} align="flex-start" style={{ minWidth: 0 }}>
                      <Tag color={presentation.color}>{presentation.label}</Tag>
                      <Tooltip title={alert.message}>
                        <Text ellipsis>{alert.message}</Text>
                      </Tooltip>
                    </Flex>
                    <Text type="secondary" className="overview-nowrap">{formatDateTime(alert.occurred_at)}</Text>
                  </Flex>
                )
              })}
              {(dashboard?.recent_alerts ?? []).length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无历史告警。" /> : null}
              <div className="overview-subsection-title">最近任务</div>
              {(dashboard?.recent_tasks ?? []).slice(0, 3).map((task: AdminRecentTaskItem) => (
                <Flex justify="space-between" gap={10} key={task.task_id}>
                  <Text ellipsis>{task.title || task.task_id}</Text>
                  <Tag>{taskStatusLabel(task.status)}</Tag>
                </Flex>
              ))}
              {(dashboard?.recent_tasks ?? []).length === 0 ? <Text type="secondary">暂无任务记录。</Text> : null}
            </Space>
          </Card>
        </Col>
      </Row>
    </Space>
  )
}
