import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloudUploadOutlined,
  DownloadOutlined,
  ExclamationCircleOutlined,
  FileTextOutlined,
  RobotOutlined,
} from '@ant-design/icons'
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Flex,
  Row,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  Upload,
} from 'antd'
import { useEffect, useRef, useState } from 'react'
import type { MemoryImportRecord } from '@/api/types'
import { listAgents } from '@/api/modules/agent'
import { writeMemories } from '@/api/modules/memory'
import { createSession } from '@/api/modules/session'
import { SessionLifecyclePanel } from '@/components/business/SessionLifecyclePanel'
import { PageContainer } from '@/components/common'
import { normalizeAppConfig } from '@/utils/config'
import { buildWritePayload } from '@/pages/Ingestion/model'
import { RemoteImportPanel } from '@/pages/Ingestion/RemoteImportPanel'
import { useAppStore } from '@/store'
import { getErrorMessage } from '@/utils/error'
import {
  getIngestionActivity,
  recordIngestionImport,
  summarizeIngestionActivity,
} from '@/utils/ingestionActivity'
import type { IngestionHistoryItem, IngestionImportStatus } from '@/utils/ingestionActivity'
import { parseMemoryImportText } from '@/utils/memoryImport'

const importStatusMeta: Record<IngestionImportStatus, { label: string; color: string }> = {
  completed: { label: '已完成', color: 'success' },
  partial: { label: '部分完成', color: 'warning' },
  failed: { label: '失败', color: 'error' },
}

const importTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

const supportedExtensions = ['.json', '.jsonl', '.csv']

type ImportChannel = 'file' | 'remote'

interface AgentOption {
  value: string
  label: string
}

interface FileStats {
  parsed: number
  failed: number
  skipped: number
}

function createHistoryId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

/** 生成符合后端契约的示例 JSONL（每行一个历史会话）。 */
const sessionTemplate = [
  {
    messages: [
      { role: 'user', content: '订单 DH001 需要退货退款，运费由客户承担。' },
      { role: 'assistant', content: '好的，已为您提交退货申请，退款将在 3 个工作日内到账。' },
    ],
    session_summary: '订单 DH001 退货退款处理',
    session_time: '2026-08-01T10:30:00+08:00',
    session_source: 'openwebui',
  },
]

export default function IngestionPage() {
  const { message } = App.useApp()
  const config = useAppStore((state) => state.config)
  const setConfig = useAppStore((state) => state.setConfig)
  const [channel, setChannel] = useState<ImportChannel>('file')
  const [records, setRecords] = useState<MemoryImportRecord[]>([])
  const [importing, setImporting] = useState(false)
  const [importedCount, setImportedCount] = useState(0)
  const [parsing, setParsing] = useState(false)
  const [dirMode, setDirMode] = useState(false)
  const [fileStats, setFileStats] = useState<FileStats>({ parsed: 0, failed: 0, skipped: 0 })
  const [activity, setActivity] = useState(getIngestionActivity)
  const [agentOptions, setAgentOptions] = useState<AgentOption[]>([])
  // 批量选择时 customRequest 会并发调用，用计数判断解析是否全部结束，避免高频切换 loading 态。
  const parsingCountRef = useRef(0)

  const summary = summarizeIngestionActivity(activity, config.userId)
  const recentImports = activity.imports.filter((item) => item.userId === config.userId)
  const validationRate = summary.validationPassRate === null
    ? '—'
    : `${summary.validationPassRate.toFixed(1)}%`

  useEffect(() => {
    listAgents({ isActive: true })
      .then((data) => setAgentOptions(data.items.map((agent) => ({
        value: agent.agent_id,
        label: agent.agent_name ?? agent.agent_id,
      }))))
      .catch(() => setAgentOptions([]))
  }, [])

  const resetSelection = () => {
    setRecords([])
    setFileStats({ parsed: 0, failed: 0, skipped: 0 })
  }

  const handleModeChange = (value: string | number) => {
    const nextDirMode = String(value) === 'dir'
    if (nextDirMode === dirMode) return
    setDirMode(nextDirMode)
    resetSelection()
  }

  /** 解析单个文件（customRequest 对每个文件调用一次），结果追加到会话列表。 */
  const handleFile = async (file: File) => {
    const name = file.name
    const ext = name.slice(name.lastIndexOf('.')).toLowerCase()
    if (!supportedExtensions.includes(ext)) {
      setFileStats((prev) => ({ ...prev, skipped: prev.skipped + 1 }))
      return
    }
    parsingCountRef.current += 1
    if (parsingCountRef.current === 1) setParsing(true)
    try {
      const parsed = parseMemoryImportText(name, await file.text())
      if (!parsed.length) {
        // 合法 JSON 但无会话结构（如 progress.json 元数据）→ 按「跳过」处理，不报失败。
        setFileStats((prev) => ({ ...prev, skipped: prev.skipped + 1 }))
        return
      }
      setRecords((prev) => [...prev, ...parsed])
      setFileStats((prev) => ({ ...prev, parsed: prev.parsed + 1 }))
    } catch (error) {
      // 批量导入时静默累积失败数，避免逐个 toast 刷屏。
      setFileStats((prev) => ({ ...prev, failed: prev.failed + 1 }))
      console.warn(`[ingestion] 解析失败：${name}`, error)
    } finally {
      parsingCountRef.current -= 1
      if (parsingCountRef.current === 0) setParsing(false)
    }
  }

  /** 远程拉取成功：直接用拉取到的会话作为导入数据。 */
  const handleRemoteImported = (imported: MemoryImportRecord[]) => {
    setRecords(imported)
    setFileStats({ parsed: 0, failed: 0, skipped: 0 })
  }

  const handleDownloadTemplate = () => {
    const blob = new Blob(
      [sessionTemplate.map((session) => JSON.stringify(session)).join('\n')],
      { type: 'application/x-ndjson;charset=utf-8' },
    )
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = '历史会话导入模板.jsonl'
    link.click()
    URL.revokeObjectURL(url)
  }

  /** 确保存在活动会话（memory/write 的 session_id 必填），无则自动创建并持久化。 */
  const ensureSession = async (): Promise<string> => {
    const existingSessionId = config.sessionId?.trim()
    if (existingSessionId) return existingSessionId

    const session = await createSession({
      user_id: config.userId,
      agent_id: config.agentId?.trim() || undefined,
      scene_id: config.sceneId?.trim() || undefined,
    })
    setConfig(normalizeAppConfig({ ...config, sessionId: session.session_id }))
    void message.info(`已自动创建会话：${session.session_id}`)
    return session.session_id
  }

  const handleImport = async () => {
    if (!records.length) return
    const agentId = config.agentId?.trim()
    if (!agentId) {
      void message.warning('导入前必须选择归属智能体：请先在「智能体注册接入」注册或从下方下拉选择。')
      return
    }
    setImporting(true)
    setImportedCount(0)
    const source = channel === 'remote'
      ? '远程 API 导入'
      : fileStats.parsed > 1
        ? `批量导入 ${fileStats.parsed} 个文件`
        : '文件导入'
    const totalCount = records.length
    const createdAt = new Date().toISOString()
    let successCount = 0
    let submittedCount = 0
    let status: IngestionImportStatus = 'failed'
    try {
      const sessionId = await ensureSession()
      for (let index = 0; index < records.length; index += 1) {
        const record = records[index]
        const result = await writeMemories(buildWritePayload('session', record, config.userId, config.sceneId, sessionId))
        successCount += 1
        // write 只落 L0 异步抽取，响应不含记忆明细，按 l0_count 统计已提交记录数。
        submittedCount += result.l0_count ?? result.record_ids?.length ?? 0
        setImportedCount(index + 1)
      }
      status = 'completed'
      void message.success(`成功提交 ${successCount} 条历史会话`)
      setRecords([])
      setFileStats({ parsed: 0, failed: 0, skipped: 0 })
    } catch (error) {
      status = successCount ? 'partial' : 'failed'
      void message.error(getErrorMessage(
        error,
        `已提交 ${successCount} 条历史会话，后续数据处理失败`,
      ))
    } finally {
      const historyItem: IngestionHistoryItem = {
        id: createHistoryId(),
        userId: config.userId,
        agentId: config.agentId || undefined,
        mode: 'session',
        source,
        totalCount,
        successCount,
        resultCount: submittedCount,
        status,
        createdAt,
      }
      setActivity(recordIngestionImport(activity, historyItem))
      setImporting(false)
    }
  }

  return (
    <PageContainer
      title="智能体接入与记忆数据写入"
      titleExtra={(
        <Tooltip
          placement="right"
          trigger={['hover', 'focus']}
          title={(
            <span>
              <strong>当前用户的本地真实统计</strong>
              <br />
              以下指标和最近导入批次由当前浏览器根据实际解析与写入结果计算，不代表后台全局统计。
            </span>
          )}
        >
          <button
            type="button"
            aria-label="查看本地统计口径说明"
            style={{
              alignItems: 'center',
              background: 'transparent',
              border: 0,
              color: '#8c8c8c',
              cursor: 'help',
              display: 'inline-flex',
              fontSize: 16,
              padding: 0,
            }}
          >
            <ExclamationCircleOutlined />
          </button>
        </Tooltip>
      )}
      description="批量接收历史会话数据（文件导入 / 远程 API 导入），确认后写入记忆生成流水线。"
      extra={<Tag color="blue">当前用户：{config.userId}</Tag>}
    >
      <Row gutter={[14, 14]}>
        {[
          {
            title: '已选智能体',
            value: config.agentId ? '1' : '0',
            note: config.agentId ? `Agent ID：${config.agentId}` : '尚未选择智能体',
            icon: <RobotOutlined />,
            color: '#1677ff',
          },
          {
            title: '今日成功处理',
            value: summary.todaySuccessCount.toLocaleString('zh-CN'),
            note: `共 ${summary.todayBatchCount} 个提交批次`,
            icon: <CloudUploadOutlined />,
            color: '#22a884',
          },
          {
            title: '当前处理批次',
            value: importing ? '1' : '0',
            note: importing ? `正在写入 ${importedCount}/${records.length}` : '当前无进行中批次',
            icon: <ClockCircleOutlined />,
            color: '#e49a28',
          },
          {
            title: '文件校验通过率',
            value: validationRate,
            note: summary.validationAttemptCount
              ? `${summary.validationSuccessCount} 成功 / ${summary.validationAttemptCount} 次`
              : '暂无本地校验记录',
            icon: <CheckCircleOutlined />,
            color: '#7b61d1',
          },
        ].map((item) => (
          <Col xs={24} sm={12} xl={6} key={item.title}>
            <Card className="console-card ingestion-stat" variant="borderless">
              <Flex align="center" gap={12}>
                <div style={{ color: item.color, background: `${item.color}15` }}>{item.icon}</div>
                <div><Typography.Text type="secondary">{item.title}</Typography.Text><strong>{item.value}</strong><Typography.Text type="secondary">{item.note}</Typography.Text></div>
              </Flex>
            </Card>
          </Col>
        ))}
      </Row>

      <SessionLifecyclePanel />

      <Row gutter={[14, 14]}>
        <Col xs={24} xl={15}>
          <Card className="console-card" title="历史会话导入" variant="borderless">
            <Space orientation="vertical" size={16} style={{ display: 'flex' }}>
              <Alert
                type="info"
                showIcon
                title="支持 OpenWebUI 原始导出自动清洗"
                description="文件导入支持批量/整个文件夹；远程导入从已配置数据源拉取。前端自动清洗并逐会话预览，无需离线处理。"
              />

              <div>
                <Typography.Text strong>归属智能体</Typography.Text>
                <Typography.Paragraph type="secondary" style={{ margin: '4px 0 8px' }}>
                  写入请求会携带该智能体的身份凭据；请先注册智能体，或从下方选择已注册智能体。
                </Typography.Paragraph>
                <Select
                  style={{ width: '100%' }}
                  showSearch
                  optionFilterProp="label"
                  placeholder={agentOptions.length ? '选择导入数据的归属智能体' : '暂无可选智能体，请先注册'}
                  value={config.agentId || undefined}
                  onChange={(value) => {
                    setConfig(normalizeAppConfig({ ...config, agentId: value }))
                  }}
                  options={agentOptions}
                />
              </div>

              <Segmented
                block
                className="import-channel-segmented"
                value={channel}
                disabled={importing || parsing}
                options={[
                  { label: '文件导入', value: 'file' },
                  { label: '远程 API 导入', value: 'remote' },
                ]}
                onChange={(value) => setChannel(String(value) as ImportChannel)}
              />

              {channel === 'file' ? (
                <>
                  <Segmented
                    block
                    value={dirMode ? 'dir' : 'file'}
                    disabled={importing || parsing}
                    options={[
                      { label: '单文件 / 多选文件', value: 'file' },
                      { label: '整个文件夹', value: 'dir' },
                    ]}
                    onChange={handleModeChange}
                  />

                  <Upload.Dragger
                    accept=".json,.jsonl,.csv"
                    multiple={!dirMode}
                    directory={dirMode}
                    disabled={importing || parsing}
                    showUploadList={false}
                    customRequest={(options) => {
                      const file = options.file
                      if (typeof file === 'string' || !(file instanceof File)) return
                      void handleFile(file)
                    }}
                  >
                    <p className="ant-upload-drag-icon"><CloudUploadOutlined /></p>
                    <p className="ant-upload-text">
                      {dirMode
                        ? '点击选择要导入的文件夹（自动扫描 .json / .jsonl / .csv）'
                        : '拖拽或点击选择 JSON / JSONL / CSV 文件（可多选）'}
                    </p>
                    <p className="ant-upload-hint">OpenWebUI 导出的 conversation-*.json 会自动清洗为会话结构</p>
                  </Upload.Dragger>
                </>
              ) : (
                <RemoteImportPanel onImported={handleRemoteImported} />
              )}

              <Flex justify="space-between" align="center" wrap gap={12}>
                <Space wrap>
                  {records.length || fileStats.parsed || fileStats.failed ? (
                    <Typography.Text>
                      {parsing ? '正在解析文件…' : ''}
                      {records.length ? `已解析 ${records.length} 条会话` : '尚未获取数据'}
                      {channel === 'file' && fileStats.parsed ? `（${fileStats.parsed} 个文件）` : ''}
                      {channel === 'file' && fileStats.failed ? `，${fileStats.failed} 个失败` : ''}
                      {channel === 'file' && fileStats.skipped ? `，${fileStats.skipped} 个跳过（非支持格式）` : ''}
                    </Typography.Text>
                  ) : <Typography.Text>尚未选择文件</Typography.Text>}
                  <Button icon={<DownloadOutlined />} onClick={handleDownloadTemplate}>下载模板（JSONL）</Button>
                  {records.length ? <Button onClick={resetSelection}>清空选择</Button> : null}
                </Space>
                <Button
                  type="primary"
                  icon={<FileTextOutlined />}
                  disabled={!records.length}
                  loading={importing}
                  onClick={() => void handleImport()}
                >
                  {importing ? `正在写入 ${importedCount}/${records.length}` : '校验并写入'}
                </Button>
              </Flex>

              {records.length ? (
                <Table<MemoryImportRecord & { __rowKey: string }>
                  size="small"
                  pagination={{ pageSize: 10, showSizeChanger: false }}
                  rowKey={(record) => record.__rowKey}
                  dataSource={records.map((record, index) => ({ ...record, __rowKey: String(index) }))}
                  columns={[
                    {
                      title: '会话摘要',
                      dataIndex: 'session_summary',
                      ellipsis: true,
                      render: (value: string | undefined, record) => value || record.content.slice(0, 60) || '-',
                    },
                    {
                      title: '消息数',
                      key: 'messageCount',
                      width: 90,
                      render: (_value: unknown, record) => record.messages?.length ?? 1,
                    },
                    {
                      title: '会话时间',
                      dataIndex: 'session_time',
                      width: 170,
                      render: (value?: string) => value || '-',
                    },
                    {
                      title: '来源',
                      dataIndex: 'session_source',
                      width: 110,
                      render: (value?: string) => <Tag>{value || 'frontend_file_import'}</Tag>,
                    },
                  ]}
                />
              ) : null}
            </Space>
          </Card>
        </Col>
        <Col xs={24} xl={9}>
          <Card className="console-card" title="数据格式说明" variant="borderless">
            <Space orientation="vertical" size={14}>
              <div>
                <Tag color="green">历史会话</Tag>
                <Typography.Text>每行一个会话：messages + session_summary + session_time + session_source</Typography.Text>
              </div>
              <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
                messages 为 <code>{'{role, content}'}</code> 数组；role 合法值 user/assistant/system/tool/agent；
                content 为纯文本（去掉一切元数据）。
              </Typography.Paragraph>
              <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
                <strong>OpenWebUI 导出</strong>：上传原始 conversation-*.json（含 history.messages），
                前端按 parentId 树序还原对话顺序并清洗后写入，无需离线处理。
              </Typography.Paragraph>
              <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
                <strong>远程 API 导入</strong>：在「外部数据源管理」维护接入源后，此处可「立即拉取并导入」；
                真实定时拉取需后端采集任务（见《后端改造清单0824》）。
              </Typography.Paragraph>
              <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
                写入走异步链路（<code>interaction_type=session</code>），提交后由后端 L1 异步抽取记忆，
                列表/检索通常秒级到几十秒后可见。
              </Typography.Paragraph>
            </Space>
          </Card>
        </Col>
      </Row>

      <Card className="console-card" title="最近导入批次" variant="borderless">
        <Table
          size="small"
          pagination={false}
          rowKey="id"
          dataSource={recentImports}
          locale={{ emptyText: '当前用户在本浏览器暂无导入记录' }}
          columns={[
            { title: '数据来源', dataIndex: 'source' },
            {
              title: '数据类型',
              dataIndex: 'mode',
              render: () => <Tag color="green">历史会话</Tag>,
            },
            {
              title: '成功/总数',
              render: (_value: unknown, item: IngestionHistoryItem) => `${item.successCount}/${item.totalCount}`,
            },
            { title: '已提交记录数', dataIndex: 'resultCount' },
            {
              title: '处理状态',
              dataIndex: 'status',
              render: (value: IngestionImportStatus) => (
                <Tag color={importStatusMeta[value].color}>{importStatusMeta[value].label}</Tag>
              ),
            },
            {
              title: '提交时间',
              dataIndex: 'createdAt',
              render: (value: string) => importTimeFormatter.format(new Date(value)),
            },
          ]}
        />
      </Card>
    </PageContainer>
  )
}
