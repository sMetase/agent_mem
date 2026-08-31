import {
  ApiOutlined,
  ClockCircleOutlined,
  CloudServerOutlined,
  ExclamationCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { isAxiosError } from 'axios'
import { Alert, Button, Card, Col, Flex, Input, Row, Select, Space, Table, Tag, Tooltip, Typography } from 'antd'
import type { TableColumnsType } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { getAdminApiLogs, getAdminRetrievalLogs, getHealth } from '@/api/modules/monitoring'
import type { AdminApiLogItem, AdminPageResult, AdminRetrievalLogItem, HealthResult } from '@/api/types'
import { FeedbackState, PageContainer } from '@/components/common'
import { getErrorMessage } from '@/utils/error'
import { showSuccessMessage, showWarningMessage } from '@/utils/feedback'
import {
  filterFailedApiLogs,
  getMonitoringMode,
  getResponseCodeColor,
  isFailedApiLog,
  truncateLogText,
} from './model'

const defaultPageSize = 20
const recordFailureSampleSize = 100
const dateTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
})

const monitoringMeta = {
  all: { title: '接口与运行监控', description: '集中查看后端服务连通性、真实接口日志和最近检索记录。' },
  health: { title: '接口健康检查', description: '主动检查后端服务是否可访问，并确认应用名称、接口版本和本次耗时。' },
  calls: { title: '调用状态监控', description: '查看后端记录的真实接口调用、响应状态和耗时。' },
  records: { title: '联调记录', description: '查看后端记录的真实检索请求和最近失败调用。' },
} as const

function createEmptyPage<T>(): AdminPageResult<T> {
  return { items: [], total: 0, page: 1, page_size: defaultPageSize }
}

function formatDateTime(value?: string | null) {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : dateTimeFormatter.format(date)
}

function isPermissionError(error: unknown) {
  return isAxiosError(error) && (error.response?.status === 401 || error.response?.status === 403)
}

function errorCopy(error: unknown) {
  return isPermissionError(error)
    ? { title: '需要管理员权限', description: '当前凭据无权读取后台日志，请配置管理员凭据后重试。' }
    : { title: '监控数据加载失败', description: '请检查后端连接后重试。' }
}

const apiLogColumns: TableColumnsType<AdminApiLogItem> = [
  { title: '方法', dataIndex: 'method', width: 84, render: (value: string) => <Tag>{value || '-'}</Tag> },
  { title: '请求路径', dataIndex: 'api_path', ellipsis: true, render: (value: string) => <Typography.Text code>{value || '-'}</Typography.Text> },
  {
    title: '响应码',
    dataIndex: 'response_code',
    width: 90,
    render: (value: number) => <Tag color={getResponseCodeColor(value)}>{value}</Tag>,
  },
  { title: '错误码', dataIndex: 'error_code', width: 150, ellipsis: true, render: (value?: string | null) => value || '-' },
  { title: '耗时', dataIndex: 'elapsed_ms', width: 100, render: (value?: number | null) => typeof value === 'number' ? `${value} ms` : '-' },
  { title: '时间', dataIndex: 'created_at', width: 180, render: formatDateTime },
]

const retrievalLogColumns: TableColumnsType<AdminRetrievalLogItem> = [
  { title: '请求 ID', dataIndex: 'request_id', width: 160, ellipsis: true, render: (value: string) => <Typography.Text code>{value || '-'}</Typography.Text> },
  { title: 'Agent ID', dataIndex: 'agent_id', width: 150, ellipsis: true, render: (value?: string | null) => value || '-' },
  { title: 'User ID', dataIndex: 'user_id', width: 150, ellipsis: true, render: (value?: string | null) => value || '-' },
  { title: '查询内容', dataIndex: 'query_text', ellipsis: true, render: (value?: string | null) => truncateLogText(value) },
  { title: 'Top-K', dataIndex: 'top_k', width: 80, render: (value?: number | null) => value ?? '-' },
  { title: '时间', dataIndex: 'created_at', width: 180, render: formatDateTime },
]

const failureLogColumns: TableColumnsType<AdminApiLogItem> = [
  ...apiLogColumns,
  { title: 'Trace ID', dataIndex: 'trace_id', width: 170, ellipsis: true, render: (value?: string | null) => value || '-' },
]

interface HealthPanelProps {
  checking: boolean
  error: unknown
  health: HealthResult | null
  latencyMs: number | null
  checkedAt: string | null
  onRetry: () => void
}

function HealthPanel({ checking, error, health, latencyMs, checkedAt, onRetry }: HealthPanelProps) {
  const healthy = health?.status?.toLowerCase() === 'ok'
  const serviceStatus = checking && !health
    ? '检查中'
    : error
      ? '连接失败'
      : health
        ? healthy ? '运行正常' : health.status || '状态未知'
        : '尚未检查'

  return (
    <Space orientation="vertical" size={14} style={{ display: 'flex' }}>
      <Row gutter={[14, 14]}>
        <Col xs={24} md={8}>
          <Card className="console-card monitor-status" variant="borderless">
            <CloudServerOutlined />
            <div><Typography.Text type="secondary">后端服务</Typography.Text><strong>{serviceStatus}</strong><Typography.Text>{health?.app || '-'}</Typography.Text></div>
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card className="console-card monitor-status" variant="borderless">
            <ApiOutlined />
            <div><Typography.Text type="secondary">接口版本</Typography.Text><strong>{health?.version || '-'}</strong><Typography.Text>来自 /api/v1/health</Typography.Text></div>
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card className="console-card monitor-status" variant="borderless">
            <ClockCircleOutlined />
            <div><Typography.Text type="secondary">本次耗时</Typography.Text><strong>{latencyMs === null ? '-' : `${latencyMs} ms`}</strong><Typography.Text>{checkedAt ? formatDateTime(checkedAt) : '等待检查'}</Typography.Text></div>
          </Card>
        </Col>
      </Row>

      {checking && !health ? <Alert type="info" showIcon title="正在检查后端服务" description="正在请求 /api/v1/health，请稍候。" /> : null}
      {!checking && error ? (
        <Alert
          type="error"
          showIcon
          title="后端健康检查失败"
          description={getErrorMessage(error, '无法连接到后端服务。')}
          action={<Button size="small" onClick={onRetry}>重试</Button>}
        />
      ) : null}
      {!checking && !error && health ? (
        <Alert
          type={healthy ? 'success' : 'warning'}
          showIcon
          title={healthy ? '后端健康检查通过' : '后端返回非健康状态'}
          description={`应用：${health.app || '未知'}，版本：${health.version || '未知'}，状态：${health.status || '未知'}`}
        />
      ) : null}
    </Space>
  )
}

interface ApiLogsPanelProps {
  data: AdminPageResult<AdminApiLogItem>
  error: unknown
  loading: boolean
  hours: number
  apiPathDraft: string
  errorCodeDraft: string
  onHoursChange: (value: number) => void
  onApiPathDraftChange: (value: string) => void
  onErrorCodeDraftChange: (value: string) => void
  onApplyFilters: () => void
  onResetFilters: () => void
  onPageChange: (page: number, pageSize: number) => void
  onRetry: () => void
}

function ApiLogsPanel({
  data,
  error,
  loading,
  hours,
  apiPathDraft,
  errorCodeDraft,
  onHoursChange,
  onApiPathDraftChange,
  onErrorCodeDraftChange,
  onApplyFilters,
  onResetFilters,
  onPageChange,
  onRetry,
}: ApiLogsPanelProps) {
  const failedCount = data.items.filter(isFailedApiLog).length
  const copy = errorCopy(error)

  return (
    <Space orientation="vertical" size={14} style={{ display: 'flex' }}>
      <Row gutter={[14, 14]}>
        <Col xs={24} md={8}><Card className="console-card result-stat"><Typography.Text type="secondary">范围内日志总数</Typography.Text><strong>{data.total}</strong></Card></Col>
        <Col xs={24} md={8}><Card className="console-card result-stat"><Typography.Text type="secondary">当前页记录</Typography.Text><strong>{data.items.length}</strong></Card></Col>
        <Col xs={24} md={8}><Card className="console-card result-stat"><Typography.Text type="secondary">当前页失败</Typography.Text><strong style={{ color: failedCount ? '#d04a4a' : '#20a47c' }}>{failedCount}</strong></Card></Col>
      </Row>
      <Card
        className="console-card"
        title="接口调用记录"
        variant="borderless"
      >
        <Flex gap={8} wrap="wrap" style={{ marginBottom: 16 }}>
          <Select
            aria-label="时间范围"
            value={hours}
            style={{ width: 130 }}
            options={[
              { label: '最近 1 小时', value: 1 },
              { label: '最近 24 小时', value: 24 },
              { label: '最近 7 天', value: 168 },
              { label: '最近 30 天', value: 720 },
            ]}
            onChange={onHoursChange}
          />
          <Input aria-label="请求路径筛选" value={apiPathDraft} placeholder="请求路径" style={{ width: 210, maxWidth: '100%' }} onChange={(event) => onApiPathDraftChange(event.target.value)} />
          <Input aria-label="错误码筛选" value={errorCodeDraft} placeholder="错误码" style={{ width: 150, maxWidth: '100%' }} onChange={(event) => onErrorCodeDraftChange(event.target.value)} />
          <Button type="primary" onClick={onApplyFilters}>筛选</Button>
          <Button onClick={onResetFilters}>重置</Button>
        </Flex>
        {error ? (
          <FeedbackState status="error" title={copy.title} description={copy.description} error={isPermissionError(error) ? undefined : error} action={<Button onClick={onRetry}>重新加载</Button>} />
        ) : (
          <Table<AdminApiLogItem>
            rowKey="log_id"
            size="small"
            loading={loading}
            scroll={{ x: 980 }}
            dataSource={data.items}
            columns={apiLogColumns}
            locale={{ emptyText: loading ? '正在加载调用日志…' : '当前筛选范围内没有调用日志。' }}
            pagination={{
              current: data.page,
              pageSize: data.page_size,
              total: data.total,
              showSizeChanger: true,
              showTotal: (total) => `共 ${total} 条`,
              onChange: onPageChange,
            }}
          />
        )}
      </Card>
    </Space>
  )
}

interface RecordsPanelProps {
  retrievalData: AdminPageResult<AdminRetrievalLogItem>
  retrievalError: unknown
  failureLogs: AdminApiLogItem[]
  failureError: unknown
  loading: boolean
  onPageChange: (page: number, pageSize: number) => void
  onRetry: () => void
}

function RecordsPanel({ retrievalData, retrievalError, failureLogs, failureError, loading, onPageChange, onRetry }: RecordsPanelProps) {
  const retrievalCopy = errorCopy(retrievalError)
  const failureCopy = errorCopy(failureError)

  return (
    <Space orientation="vertical" size={14} style={{ display: 'flex' }}>
      <Row gutter={[14, 14]}>
        <Col xs={24} md={8}><Card className="console-card result-stat"><Typography.Text type="secondary">24 小时检索请求</Typography.Text><strong>{retrievalData.total}</strong></Card></Col>
        <Col xs={24} md={8}><Card className="console-card result-stat"><Typography.Text type="secondary">当前页检索记录</Typography.Text><strong>{retrievalData.items.length}</strong></Card></Col>
        <Col xs={24} md={8}><Card className="console-card result-stat"><Typography.Text type="secondary">最近 100 条内失败</Typography.Text><strong style={{ color: failureLogs.length ? '#d04a4a' : '#20a47c' }}>{failureLogs.length}</strong></Card></Col>
      </Row>

      <Card className="console-card" title="最近检索请求" variant="borderless">
        {retrievalError ? (
          <FeedbackState status="error" title={retrievalCopy.title} description={retrievalCopy.description} error={isPermissionError(retrievalError) ? undefined : retrievalError} action={<Button onClick={onRetry}>重新加载</Button>} />
        ) : (
          <Table<AdminRetrievalLogItem>
            rowKey="request_id"
            size="small"
            loading={loading}
            scroll={{ x: 980 }}
            dataSource={retrievalData.items}
            columns={retrievalLogColumns}
            locale={{ emptyText: loading ? '正在加载检索日志…' : '最近 24 小时没有检索记录。' }}
            pagination={{
              current: retrievalData.page,
              pageSize: retrievalData.page_size,
              total: retrievalData.total,
              showSizeChanger: true,
              showTotal: (total) => `共 ${total} 条`,
              onChange: onPageChange,
            }}
          />
        )}
      </Card>

      <Card className="console-card" title="最近失败调用" extra={<Typography.Text type="secondary">最近 100 条调用日志</Typography.Text>} variant="borderless">
        {failureError ? (
          <FeedbackState status="error" title={failureCopy.title} description={failureCopy.description} error={isPermissionError(failureError) ? undefined : failureError} action={<Button onClick={onRetry}>重新加载</Button>} />
        ) : (
          <Table<AdminApiLogItem>
            rowKey="log_id"
            size="small"
            loading={loading}
            pagination={false}
            scroll={{ x: 980 }}
            dataSource={failureLogs}
            columns={failureLogColumns}
            locale={{ emptyText: loading ? '正在加载失败日志…' : '最近 100 条调用日志中没有失败记录。' }}
          />
        )}
      </Card>
    </Space>
  )
}

export default function MonitoringPage() {
  const { pathname } = useLocation()
  const mode = getMonitoringMode(pathname)
  const pageMeta = monitoringMeta[mode]

  const [checkingHealth, setCheckingHealth] = useState(false)
  const [health, setHealth] = useState<HealthResult | null>(null)
  const [healthError, setHealthError] = useState<unknown>(null)
  const [healthLatencyMs, setHealthLatencyMs] = useState<number | null>(null)
  const [healthCheckedAt, setHealthCheckedAt] = useState<string | null>(null)

  const [apiLogs, setApiLogs] = useState<AdminPageResult<AdminApiLogItem>>(() => createEmptyPage())
  const [apiLogsLoading, setApiLogsLoading] = useState(false)
  const [apiLogsError, setApiLogsError] = useState<unknown>(null)
  const [apiHours, setApiHours] = useState(24)
  const [apiPathDraft, setApiPathDraft] = useState('')
  const [errorCodeDraft, setErrorCodeDraft] = useState('')
  const [apiPath, setApiPath] = useState('')
  const [errorCode, setErrorCode] = useState('')

  const [retrievalLogs, setRetrievalLogs] = useState<AdminPageResult<AdminRetrievalLogItem>>(() => createEmptyPage())
  const [retrievalError, setRetrievalError] = useState<unknown>(null)
  const [failureLogs, setFailureLogs] = useState<AdminApiLogItem[]>([])
  const [failureError, setFailureError] = useState<unknown>(null)
  const [recordsLoading, setRecordsLoading] = useState(false)

  const checkHealth = useCallback(async (notify = false) => {
    setCheckingHealth(true)
    setHealthError(null)
    const startedAt = performance.now()
    try {
      const result = await getHealth()
      setHealth(result)
      setHealthLatencyMs(Math.max(0, Math.round(performance.now() - startedAt)))
      setHealthCheckedAt(new Date().toISOString())
      if (notify) {
        if (result.status?.toLowerCase() === 'ok') showSuccessMessage('后端健康检查通过')
        else showWarningMessage('后端返回非健康状态')
      }
    } catch (error) {
      setHealth(null)
      setHealthLatencyMs(null)
      setHealthCheckedAt(new Date().toISOString())
      setHealthError(error)
    } finally {
      setCheckingHealth(false)
    }
  }, [])

  const loadApiLogs = useCallback(async (page = 1, pageSize = defaultPageSize) => {
    setApiLogsLoading(true)
    setApiLogsError(null)
    try {
      const result = await getAdminApiLogs({
        hours: apiHours,
        page,
        pageSize,
        apiPath,
        errorCode,
      })
      setApiLogs(result)
    } catch (error) {
      setApiLogsError(error)
    } finally {
      setApiLogsLoading(false)
    }
  }, [apiHours, apiPath, errorCode])

  const loadRecords = useCallback(async (page = 1, pageSize = defaultPageSize) => {
    setRecordsLoading(true)
    setRetrievalError(null)
    setFailureError(null)
    const [retrievalResult, apiResult] = await Promise.allSettled([
      getAdminRetrievalLogs({ hours: 24, page, pageSize }),
      getAdminApiLogs({ hours: 24, page: 1, pageSize: recordFailureSampleSize }),
    ])

    if (retrievalResult.status === 'fulfilled') setRetrievalLogs(retrievalResult.value)
    else setRetrievalError(retrievalResult.reason)

    if (apiResult.status === 'fulfilled') setFailureLogs(filterFailedApiLogs(apiResult.value.items))
    else setFailureError(apiResult.reason)

    setRecordsLoading(false)
  }, [])

  useEffect(() => {
    if (mode === 'all' || mode === 'health') void checkHealth()
  }, [checkHealth, mode])

  useEffect(() => {
    if (mode === 'all' || mode === 'calls') void loadApiLogs()
  }, [loadApiLogs, mode])

  useEffect(() => {
    if (mode === 'all' || mode === 'records') void loadRecords()
  }, [loadRecords, mode])

  const refreshAll = useCallback(() => {
    if (mode === 'all' || mode === 'health') void checkHealth(true)
    if (mode === 'all' || mode === 'calls') void loadApiLogs(apiLogs.page, apiLogs.page_size)
    if (mode === 'all' || mode === 'records') void loadRecords(retrievalLogs.page, retrievalLogs.page_size)
  }, [apiLogs.page, apiLogs.page_size, checkHealth, loadApiLogs, loadRecords, mode, retrievalLogs.page, retrievalLogs.page_size])

  const refreshLoading = checkingHealth || apiLogsLoading || recordsLoading
  const showHealth = mode === 'all' || mode === 'health'
  const showCalls = mode === 'all' || mode === 'calls'
  const showRecords = mode === 'all' || mode === 'records'

  return (
    <PageContainer
      title={pageMeta.title}
      titleExtra={mode === 'calls' ? (
        <Tooltip
          trigger={['hover', 'focus']}
          title={(
            <>
              <div style={{ fontWeight: 600 }}>真实调用日志</div>
              <div>以下数据来自后端 /api/v1/admin/api-logs；统计范围和分页均以接口返回为准。</div>
            </>
          )}
        >
          <span
            aria-label="调用日志说明"
            role="img"
            tabIndex={0}
            style={{ color: '#1677ff', cursor: 'help', display: 'inline-flex', fontSize: 16 }}
          >
            <ExclamationCircleOutlined aria-hidden />
          </span>
        </Tooltip>
      ) : undefined}
      description={pageMeta.description}
      extra={<Button type="primary" icon={<ReloadOutlined />} loading={refreshLoading} onClick={refreshAll}>刷新数据</Button>}
    >
      <Space orientation="vertical" size={18} style={{ display: 'flex' }}>
        {showHealth ? <HealthPanel checking={checkingHealth} error={healthError} health={health} latencyMs={healthLatencyMs} checkedAt={healthCheckedAt} onRetry={() => void checkHealth(true)} /> : null}
        {showCalls ? (
          <ApiLogsPanel
            data={apiLogs}
            error={apiLogsError}
            loading={apiLogsLoading}
            hours={apiHours}
            apiPathDraft={apiPathDraft}
            errorCodeDraft={errorCodeDraft}
            onHoursChange={(value) => {
              setApiHours(value)
              setApiLogs((current) => ({ ...current, page: 1 }))
            }}
            onApiPathDraftChange={setApiPathDraft}
            onErrorCodeDraftChange={setErrorCodeDraft}
            onApplyFilters={() => {
              setApiPath(apiPathDraft.trim())
              setErrorCode(errorCodeDraft.trim())
              setApiLogs((current) => ({ ...current, page: 1 }))
            }}
            onResetFilters={() => {
              setApiPathDraft('')
              setErrorCodeDraft('')
              setApiPath('')
              setErrorCode('')
              setApiHours(24)
              setApiLogs((current) => ({ ...current, page: 1 }))
            }}
            onPageChange={(page, pageSize) => void loadApiLogs(page, pageSize)}
            onRetry={() => void loadApiLogs(apiLogs.page, apiLogs.page_size)}
          />
        ) : null}
        {showRecords ? (
          <RecordsPanel
            retrievalData={retrievalLogs}
            retrievalError={retrievalError}
            failureLogs={failureLogs}
            failureError={failureError}
            loading={recordsLoading}
            onPageChange={(page, pageSize) => void loadRecords(page, pageSize)}
            onRetry={() => void loadRecords(retrievalLogs.page, retrievalLogs.page_size)}
          />
        ) : null}
      </Space>
    </PageContainer>
  )
}
