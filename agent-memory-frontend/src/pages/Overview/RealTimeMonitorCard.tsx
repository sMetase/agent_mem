import { ReloadOutlined } from '@ant-design/icons'
import { DualAxes } from '@ant-design/plots'
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Empty,
  Flex,
  Row,
  Segmented,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { TableColumnsType } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { getAdminApiLogs, getHealth } from '@/api/modules/monitoring'
import type { AdminApiLogItem, HealthResult } from '@/api/types'
import { formatDashboardNumber, formatDashboardPercent } from './dashboard-adapter'
import {
  buildApiPathStats,
  buildFailedCallTraces,
  buildMonitorSeries,
  monitorGranularityHours,
  monitorGranularityOptions,
} from './monitor-series'
import type {
  ApiPathStat,
  FailedCallTrace,
  MonitorGranularity,
  MonitorSeries,
} from './monitor-series'

const { Text } = Typography

const granularityLabels: Record<MonitorGranularity, string> = {
  hour: '最近 1 小时',
  day: '最近 24 小时',
  week: '最近 7 天',
}

const pathColumns: TableColumnsType<ApiPathStat> = [
  { title: '请求路径', dataIndex: 'path', ellipsis: true, render: (value: string) => <Typography.Text code ellipsis>{value}</Typography.Text> },
  { title: '调用次数', dataIndex: 'count', width: 90 },
  { title: '失败', dataIndex: 'failedCount', width: 70, render: (value: number) => value ? <Tag color="red">{value}</Tag> : <Tag color="green">0</Tag> },
  { title: '成功率', dataIndex: 'successRate', width: 90, render: (value: number | null) => value === null ? '-' : formatDashboardPercent(value) },
  { title: '最近耗时', dataIndex: 'latestElapsedMs', width: 90, render: (value?: number | null) => typeof value === 'number' ? `${value} ms` : '-' },
]

const failureColumns: TableColumnsType<FailedCallTrace> = [
  { title: '请求路径', dataIndex: 'path', ellipsis: true, render: (value: string) => <Typography.Text code ellipsis>{value}</Typography.Text> },
  { title: '状态码', dataIndex: 'responseCode', width: 80, render: (value: number) => <Tag color={value >= 500 ? 'red' : value >= 400 ? 'orange' : 'default'}>{value}</Tag> },
  { title: '错误码', dataIndex: 'errorCode', width: 140, ellipsis: true, render: (value?: string | null) => value || '-' },
  { title: 'Trace ID', dataIndex: 'traceId', width: 160, ellipsis: true, render: (value?: string | null) => value ? <Typography.Text copyable={{ text: value }} ellipsis>{value}</Typography.Text> : '-' },
]

export function RealTimeMonitorCard() {
  const [granularity, setGranularity] = useState<MonitorGranularity>('day')
  const [series, setSeries] = useState<MonitorSeries | null>(null)
  const [pathStats, setPathStats] = useState<ApiPathStat[]>([])
  const [failures, setFailures] = useState<FailedCallTrace[]>([])
  const [health, setHealth] = useState<HealthResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<unknown>(null)

  const load = useCallback(async (nextGranularity = granularity) => {
    setLoading(true)
    setError(null)
    try {
      // 后端 admin/api-logs 单页上限 100；循环分页拉取窗口内全量日志再聚合。
      const pageSize = 100
      const items: AdminApiLogItem[] = []
      let page = 1
      for (;;) {
        const result = await getAdminApiLogs({
          hours: monitorGranularityHours[nextGranularity],
          page,
          pageSize,
        })
        items.push(...result.items)
        if (result.items.length < pageSize || page * pageSize >= result.total) break
        page += 1
      }
      setSeries(buildMonitorSeries(items, nextGranularity))
      setPathStats(buildApiPathStats(items))
      setFailures(buildFailedCallTraces(items))
    } catch (loadError) {
      setSeries(null)
      setError(loadError)
    } finally {
      setLoading(false)
    }
  }, [granularity])

  const loadHealth = useCallback(async () => {
    try {
      setHealth(await getHealth())
    } catch {
      setHealth(null)
    }
  }, [])

  useEffect(() => {
    void load()
    void loadHealth()
  }, [load, loadHealth])

  const handleGranularityChange = (value: string | number) => {
    const nextGranularity = value as MonitorGranularity
    setGranularity(nextGranularity)
    void load(nextGranularity)
  }

  const handleRefresh = () => {
    void load()
    void loadHealth()
  }

  const hasData = Boolean(series && series.points.some((point) => point.count > 0))

  const chartData = (series?.points ?? []).map((point) => ({
    time: point.time,
    count: point.count,
    rate: point.rate === null ? 0 : Number((point.rate * 100).toFixed(1)),
  }))

  const healthHealthy = health?.status?.toLowerCase() === 'ok'

  return (
    <Card
      className="console-card dashboard-panel"
      title="接口调用实时监控"
      extra={(
        <Space wrap>
          <Segmented
            size="small"
            value={granularity}
            options={monitorGranularityOptions}
            onChange={handleGranularityChange}
          />
          <Button
            size="small"
            type="text"
            icon={<ReloadOutlined />}
            loading={loading}
            onClick={handleRefresh}
          />
        </Space>
      )}
      variant="borderless"
    >
      {error ? (
        <Alert
          type="warning"
          showIcon
          message="接口调用数据加载失败"
          description="实时监控看板暂时无法获取调用日志，请检查后端连接。"
          action={<Button size="small" onClick={handleRefresh}>重试</Button>}
        />
      ) : null}

      {!error && loading ? (
        <div className="monitor-chart-loading">
          <Text type="secondary">正在聚合 {granularityLabels[granularity]} 接口调用…</Text>
        </div>
      ) : null}

      {!error && !loading && !hasData ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={`${granularityLabels[granularity]}暂无接口调用记录。`} />
      ) : null}

      {!error && !loading && hasData && series ? (
        <Space orientation="vertical" size={12} style={{ display: 'flex' }}>
          <Row gutter={[12, 12]}>
            <Col xs={12} md={3}><Card className="console-card result-stat" variant="borderless">
              <Text type="secondary">后端状态</Text>
              <Space size={6}>
                <Badge status={healthHealthy ? 'success' : health === null ? 'default' : 'error'} />
                <strong style={{ color: healthHealthy ? '#20a47c' : health === null ? '#8b99aa' : '#d04a4a' }}>
                  {health === null ? '未检测' : healthHealthy ? (health.app || '正常') : health.status || '异常'}
                </strong>
              </Space>
            </Card></Col>
            <Col xs={12} md={3}><Card className="console-card result-stat" variant="borderless"><Text type="secondary">总调用</Text><strong>{formatDashboardNumber(series.totalCalls)}</strong></Card></Col>
            <Col xs={12} md={3}><Card className="console-card result-stat" variant="borderless"><Text type="secondary">失败调用</Text><strong style={{ color: series.failedCalls ? '#d04a4a' : '#20a47c' }}>{series.failedCalls}</strong></Card></Col>
            <Col xs={12} md={3}><Card className="console-card result-stat" variant="borderless"><Text type="secondary">成功率</Text><strong style={{ color: '#20a47c' }}>{series.successRate === null ? '--' : formatDashboardPercent(series.successRate)}</strong></Card></Col>
            <Col xs={24} md={12}>
              <Flex justify="flex-end" align="center" gap={10} wrap>
                <Tag color="blue">调用频次</Tag>
                <Tag color="green">成功率 %</Tag>
              </Flex>
            </Col>
          </Row>
          <DualAxes
            height={240}
            data={chartData}
            xField="time"
            children={[ // oxlint-disable-line react/no-children-prop -- DualAxes 图表配置属性，并非 React 子元素
              {
                type: 'line',
                data: chartData.map((item) => ({ time: item.time, value: item.count })),
                xField: 'time',
                yField: 'value',
                colorField: () => '调用频次',
                style: { stroke: '#1677ff', lineWidth: 2 },
                scale: {
                  y: { key: 'countScale' },
                },
                axis: {
                  y: { title: '调用频次' },
                },
              },
              {
                type: 'line',
                data: chartData.map((item) => ({ time: item.time, value: item.rate })),
                xField: 'time',
                yField: 'value',
                colorField: () => '成功率',
                style: { stroke: '#20a47c', lineWidth: 2 },
                scale: {
                  y: { key: 'rateScale' },
                },
                axis: {
                  y: { title: '成功率 (%)' },
                },
              },
            ]}
          />

          <Row gutter={[12, 12]}>
            <Col xs={24} xl={12}>
              <Card className="console-card" title="请求路径调用统计" size="small" variant="borderless">
                <Table<ApiPathStat>
                  size="small"
                  rowKey="path"
                  pagination={false}
                  dataSource={pathStats}
                  columns={pathColumns}
                  locale={{ emptyText: '暂无接口调用记录。' }}
                />
              </Card>
            </Col>
            <Col xs={24} xl={12}>
              <Card className="console-card" title={`失败调用追溯${failures.length ? `（${failures.length}）` : ''}`} size="small" variant="borderless">
                {failures.length ? (
                  <Table<FailedCallTrace>
                    size="small"
                    rowKey={(record) => `${record.path}-${record.traceId ?? record.createdAt ?? record.responseCode}`}
                    pagination={false}
                    dataSource={failures}
                    columns={failureColumns}
                  />
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前窗口无失败调用。" />
                )}
              </Card>
            </Col>
          </Row>
        </Space>
      ) : null}
    </Card>
  )
}
