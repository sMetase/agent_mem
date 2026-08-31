import {
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  ReloadOutlined,
  SyncOutlined,
} from '@ant-design/icons'
import {
  Button,
  Card,
  Col,
  Flex,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { TableColumnsType } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import type { MemoryItem, MemoryLevel, MemoryStatsResult } from '@/api/types'
import {
  deleteMemory,
  getMemoryStats,
  listMemories,
  updateMemory,
} from '@/api/modules/memory'
import { FeedbackState, PageContainer, openConfirmDialog } from '@/components/common'
import { LevelStatCards, MemorySearchBar } from '@/pages/Memory/components'
import type { MemoryAdvancedFilters } from '@/pages/Memory/components/MemorySearchBar'
import type { LevelStat } from '@/pages/Memory/components/LevelStatCards'
import { useAppStore, useMemoryStore } from '@/store'
import { showErrorMessage, showSuccessMessage, showWarningMessage } from '@/utils/feedback'
import type { MemoryScope } from '@/pages/Memory/types'

interface MemoryEditValues {
  content: string
  summary?: string
  status?: string
  importance?: number
  confidence?: number
  tags?: string
}

const memoryCountFormatter = new Intl.NumberFormat('zh-CN')
const memoryRatioFormatter = new Intl.NumberFormat('zh-CN', {
  style: 'percent',
  maximumFractionDigits: 1,
})

const memoryLevelCards: Array<{
  level: MemoryLevel
  title: string
  description: string
  color: string
}> = [
  { level: 'user', title: '用户级记忆', description: '用户偏好与稳定事实', color: '#1677ff' },
  { level: 'session', title: '会话级记忆', description: '历史会话摘要与上下文', color: '#20a47c' },
  { level: 'task', title: '任务级记忆', description: '目标、进展与执行结果', color: '#e49a28' },
  { level: 'agent', title: '智能体级记忆', description: '智能体能力、流程与状态经验', color: '#7b61d1' },
]

const scopeMeta: Record<MemoryScope, { title: string; description: string; tableTitle: string }> = {
  all: {
    title: '多层记忆管理',
    description: '统一管理用户、会话、任务和智能体级记忆，支持检索、修正、归档与删除。',
    tableTitle: '全部记忆单元',
  },
  user: {
    title: '用户级记忆',
    description: '集中维护当前用户的长期偏好、稳定事实、习惯和约束条件。',
    tableTitle: '用户级记忆列表',
  },
  session: {
    title: '会话级记忆',
    description: '按会话组织历史对话摘要、关键事实和上下文线索。',
    tableTitle: '会话级记忆列表',
  },
  task: {
    title: '任务级记忆',
    description: '按任务组织目标、执行进展、结果和待办事项。',
    tableTitle: '任务级记忆列表',
  },
  agent: {
    title: '智能体级记忆',
    description: '按智能体组织能力、流程与状态经验。',
    tableTitle: '智能体级记忆列表',
  },
}

function getMemoryScope(pathname: string): MemoryScope {
  if (pathname.endsWith('/user')) return 'user'
  if (pathname.endsWith('/session')) return 'session'
  if (pathname.endsWith('/task')) return 'task'
  if (pathname.endsWith('/agent')) return 'agent'
  return 'all'
}

function isSameDay(value: string | undefined, now: Date) {
  if (!value) return false
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return false
  return date.toDateString() === now.toDateString()
}

function formatDateTime(value?: string | null) {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}

export default function MemoryPage() {
  const [editForm] = Form.useForm<MemoryEditValues>()
  const { pathname } = useLocation()
  const scope = getMemoryScope(pathname)
  const pageMeta = scopeMeta[scope]
  const config = useAppStore((state) => state.config)
  const memories = useMemoryStore((state) => state.memories)
  const setMemories = useMemoryStore((state) => state.setMemories)

  const [keyword, setKeyword] = useState('')
  const [advanced, setAdvanced] = useState<MemoryAdvancedFilters>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [editingMemory, setEditingMemory] = useState<MemoryItem | null>(null)
  const [viewingMemory, setViewingMemory] = useState<MemoryItem | null>(null)
  const [saving, setSaving] = useState(false)
  const [listPage, setListPage] = useState(1)
  const [listPageSize, setListPageSize] = useState(20)
  const [listTotal, setListTotal] = useState(0)
  const [memoryStats, setMemoryStats] = useState<MemoryStatsResult | null>(null)
  const [statsLoading, setStatsLoading] = useState(false)
  const [statsError, setStatsError] = useState<unknown>(null)
  const [selectedMemoryIds, setSelectedMemoryIds] = useState<string[]>([])

  useEffect(() => {
    setSelectedMemoryIds([])
    setAdvanced({})
    setKeyword('')
    setListPage(1)
  }, [scope])

  useEffect(() => {
    setSelectedMemoryIds([])
  }, [config.userId])

  const visibleMemories = memories
  const visibleMemoryIds = useMemo(
    () => visibleMemories.map((memory) => memory.memory_id),
    [visibleMemories],
  )
  const allVisibleSelected = visibleMemoryIds.length > 0
    && visibleMemoryIds.every((memoryId) => selectedMemoryIds.includes(memoryId))

  const loadMemories = useCallback(async (page = 1, pageSize = 20, filters?: MemoryAdvancedFilters) => {
    setLoading(true)
    setError(null)
    try {
      const activeFilters = filters ?? advanced
      const result = await listMemories({
        userId: config.userId,
        memoryScope: scope === 'all' || scope === 'agent' ? undefined : scope,
        sessionId: activeFilters.sessionId?.trim() || undefined,
        taskId: activeFilters.taskId?.trim() || undefined,
        agentId: activeFilters.agentId?.trim() || undefined,
        sceneId: activeFilters.sceneId?.trim() || undefined,
        memoryType: activeFilters.memoryType?.trim() || undefined,
        timeStart: activeFilters.timeRange?.[0]?.startOf('day').toISOString(),
        timeEnd: activeFilters.timeRange?.[1]?.endOf('day').toISOString(),
        page,
        pageSize,
      })

      // 类型/场景/智能体/时间范围下沉后端 list 过滤；关键词/标签为前端二次过滤（后端 list 不支持）。
      let items = result.items
      const normalizedKeyword = keyword.trim().toLowerCase()
      if (normalizedKeyword) {
        items = items.filter((item) =>
          item.content?.toLowerCase().includes(normalizedKeyword)
          || item.memory_id?.toLowerCase().includes(normalizedKeyword)
          || item.tags?.some((tag) => tag.toLowerCase().includes(normalizedKeyword)),
        )
      }
      if (activeFilters.tags?.trim()) {
        const tagSet = activeFilters.tags.split(/[,，]/).map((tag) => tag.trim().toLowerCase()).filter(Boolean)
        if (tagSet.length) {
          items = items.filter((item) => item.tags?.some((tag) => tagSet.includes(tag.toLowerCase())))
        }
      }

      setMemories(items)
      setListPage(result.page || page)
      setListPageSize(result.page_size || pageSize)
      setListTotal(result.total)
    } catch (loadError) {
      setError(loadError)
    } finally {
      setLoading(false)
    }
  }, [advanced, config.userId, keyword, scope, setMemories])

  const loadMemoryStats = useCallback(async () => {
    setStatsLoading(true)
    setStatsError(null)
    try {
      setMemoryStats(await getMemoryStats(config.userId))
    } catch (loadError) {
      setMemoryStats(null)
      setStatsError(loadError)
    } finally {
      setStatsLoading(false)
    }
  }, [config.userId])

  useEffect(() => {
    const requests: Promise<void>[] = [loadMemories(1, 20)]
    requests.push(loadMemoryStats())
    void Promise.all(requests)
  }, [loadMemories, loadMemoryStats])

  const handleRefresh = async () => {
    await Promise.all([loadMemories(listPage, listPageSize), loadMemoryStats()])
  }

  const handleSearch = () => {
    void loadMemories(1, listPageSize)
  }

  const handleReset = () => {
    setKeyword('')
    setAdvanced({})
    void loadMemories(1, listPageSize)
  }

  const handleEdit = (memory: MemoryItem) => {
    setEditingMemory(memory)
    editForm.setFieldsValue({
      content: memory.content,
      summary: memory.summary,
      status: memory.status || 'active',
      importance: memory.importance,
      confidence: memory.confidence,
      tags: memory.tags?.join(', '),
    })
  }

  const handleSave = async () => {
    if (!editingMemory) return
    let values: MemoryEditValues
    try {
      values = await editForm.validateFields()
    } catch {
      return
    }
    const tags = values.tags?.split(/[,，]/).map((tag) => tag.trim()).filter(Boolean)
    setSaving(true)
    try {
      await updateMemory({
        memory_id: editingMemory.memory_id,
        content: values.content.trim(),
        summary: values.summary?.trim() || undefined,
        status: values.status,
        importance: values.importance,
        confidence: values.confidence,
        tags,
      })
      setMemories(memories.map((memory) =>
        memory.memory_id === editingMemory.memory_id
          ? {
              ...memory,
              content: values.content.trim(),
              summary: values.summary?.trim() || undefined,
              status: values.status,
              importance: values.importance,
              confidence: values.confidence,
              tags,
              updated_at: new Date().toISOString(),
            }
          : memory,
      ))
      setEditingMemory(null)
      showSuccessMessage('记忆已更新')
    } catch (saveError) {
      showErrorMessage(saveError, '更新记忆失败')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = (memory: MemoryItem) => {
    openConfirmDialog({
      title: '删除这条记忆？',
      content: memory.content,
      onOk: async () => {
        await deleteMemory(memory.memory_id, '用户在前端删除')
        setMemories(memories.filter((item) => item.memory_id !== memory.memory_id))
        setSelectedMemoryIds((ids) => ids.filter((id) => id !== memory.memory_id))
        setListTotal((total) => Math.max(0, total - 1))
        showSuccessMessage('记忆已删除')
      },
    })
  }

  const handleUpdateSingle = async (memory: MemoryItem) => {
    try {
      const result = await listMemories({
        userId: config.userId,
        memoryScope: memory.memory_scope === 'agent' ? undefined : memory.memory_scope,
        page: 1,
        pageSize: 100,
      })
      const latest = result.items.find((item) => item.memory_id === memory.memory_id)
      if (latest) {
        setMemories(memories.map((item) => (item.memory_id === latest.memory_id ? latest : item)))
        showSuccessMessage('记忆已同步最新状态')
      } else {
        showWarningMessage('该记忆已不存在或已变更')
      }
    } catch (syncError) {
      showErrorMessage(syncError, '同步记忆失败')
    }
  }

  const handleDeleteSelected = () => {
    if (!selectedMemoryIds.length) return
    openConfirmDialog({
      title: `删除选中的 ${selectedMemoryIds.length} 条记忆？`,
      content: '选中的记忆将被软删除并从向量索引中移除，操作完成后不能在当前列表中继续检索。',
      onOk: async () => {
        const results = await Promise.allSettled(selectedMemoryIds.map((memoryId) =>
          deleteMemory(memoryId, '用户在前端批量删除'),
        ))
        const succeededIds = selectedMemoryIds.filter((_, index) => results[index].status === 'fulfilled')
        const failedCount = selectedMemoryIds.length - succeededIds.length

        setMemories(memories.filter((memory) => !succeededIds.includes(memory.memory_id)))
        setSelectedMemoryIds((ids) => ids.filter((id) => !succeededIds.includes(id)))
        setListTotal((total) => Math.max(0, total - succeededIds.length))

        if (failedCount) {
          showWarningMessage(`成功删除 ${succeededIds.length} 条，${failedCount} 条删除失败`)
        } else {
          showSuccessMessage(`已删除 ${succeededIds.length} 条记忆`)
        }
      },
    })
  }

  const handleToggleSelectAll = () => {
    if (allVisibleSelected) {
      setSelectedMemoryIds((ids) => ids.filter((id) => !visibleMemoryIds.includes(id)))
      return
    }
    setSelectedMemoryIds((ids) => Array.from(new Set([...ids, ...visibleMemoryIds])))
  }

  const columns: TableColumnsType<MemoryItem> = (() => {
    const renderActionColumn = (_: unknown, memory: MemoryItem) => (
      <Flex gap={4}>
        <Button type="text" size="small" icon={<EyeOutlined />} aria-label="查看" onClick={() => setViewingMemory(memory)} />
        <Button type="text" size="small" icon={<EditOutlined />} aria-label="修改" onClick={() => handleEdit(memory)} />
        <Button type="text" danger size="small" icon={<DeleteOutlined />} aria-label="删除" onClick={() => handleDelete(memory)} />
        <Button type="text" size="small" icon={<SyncOutlined />} aria-label="更新" onClick={() => void handleUpdateSingle(memory)} />
      </Flex>
    )

    const baseColumns: TableColumnsType<MemoryItem> = []
    if (scope === 'user') {
      baseColumns.push(
        { title: '用户 ID', dataIndex: 'user_id', width: 140, ellipsis: true, render: () => <Typography.Text>{config.userId}</Typography.Text> },
        { title: '记忆内容摘要', dataIndex: 'content', ellipsis: true, width: 320 },
        { title: '记忆标签', dataIndex: 'tags', width: 160, render: (value?: string[]) => value?.length ? <Space size={4} wrap>{value.slice(0, 3).map((tag) => <Tag key={tag}>{tag}</Tag>)}</Space> : '-' },
        { title: '创建时间', dataIndex: 'created_at', width: 160, render: formatDateTime },
        { title: '最后更新时间', dataIndex: 'updated_at', width: 160, render: formatDateTime },
      )
    } else if (scope === 'session') {
      baseColumns.push(
        { title: '会话 ID', dataIndex: 'session_id', width: 150, ellipsis: true, render: (value?: string) => value || '-' },
        { title: '所属用户 ID', dataIndex: 'user_id', width: 130, ellipsis: true, render: () => <Typography.Text>{config.userId}</Typography.Text> },
        { title: '会话主题摘要', dataIndex: 'content', ellipsis: true, width: 300 },
        { title: '创建时间', dataIndex: 'created_at', width: 160, render: formatDateTime },
        { title: '结束时间', dataIndex: 'updated_at', width: 160, render: formatDateTime },
      )
    } else if (scope === 'task') {
      baseColumns.push(
        { title: '任务 ID', dataIndex: 'task_id', width: 150, ellipsis: true, render: (value?: string) => value || '-' },
        { title: '所属会话 ID', dataIndex: 'session_id', width: 150, ellipsis: true, render: (value?: string) => value || '-' },
        { title: '任务主题', dataIndex: 'content', ellipsis: true, width: 300 },
        { title: '任务状态', dataIndex: 'status', width: 100, render: (value?: string) => <Tag color={value === 'archived' ? 'default' : 'success'}>{value || 'active'}</Tag> },
        { title: '创建时间', dataIndex: 'created_at', width: 160, render: formatDateTime },
      )
    } else if (scope === 'agent') {
      baseColumns.push(
        { title: '智能体 ID', dataIndex: 'agent_id', width: 150, ellipsis: true, render: (value?: string) => value || '-' },
        { title: '记忆内容摘要', dataIndex: 'content', ellipsis: true, width: 320 },
        { title: '记忆类型', dataIndex: 'memory_type', width: 110, render: (value?: string) => value ? <Tag color="blue">{value}</Tag> : '-' },
        { title: '创建时间', dataIndex: 'created_at', width: 160, render: formatDateTime },
        { title: '最后更新时间', dataIndex: 'updated_at', width: 160, render: formatDateTime },
      )
    } else {
      baseColumns.push(
        { title: '记忆内容', dataIndex: 'content', ellipsis: true, width: 300 },
        { title: '层级', dataIndex: 'memory_scope', width: 100, render: (value?: string) => value ? <Tag color="blue">{value}</Tag> : '-' },
        { title: '类型', dataIndex: 'memory_type', width: 100, render: (value?: string) => value ? <Tag>{value}</Tag> : '-' },
        { title: '标签', dataIndex: 'tags', width: 160, render: (value?: string[]) => value?.length ? <Space size={4} wrap>{value.slice(0, 3).map((tag) => <Tag key={tag}>{tag}</Tag>)}</Space> : '-' },
        { title: '更新时间', dataIndex: 'updated_at', width: 160, render: formatDateTime },
      )
    }
    baseColumns.push({ title: '操作', key: 'action', fixed: 'right', width: 150, render: renderActionColumn })
    return baseColumns
  })()

  const buildLevelStats = useCallback((): LevelStat[] => {
    const now = new Date()
    if (scope === 'user') {
      return [
        { label: '总记忆条数', value: memoryCountFormatter.format(listTotal), color: '#1677ff' },
        { label: '今日新增记忆数', value: memoryCountFormatter.format(memories.filter((m) => isSameDay(m.created_at, now)).length), color: '#e49a28' },
      ]
    }
    if (scope === 'session') {
      const totalSessions = new Set(memories.map((m) => m.session_id).filter(Boolean)).size
      return [
        { label: '总会话数', value: memoryCountFormatter.format(totalSessions), color: '#1677ff' },
        { label: '活跃会话数', value: memoryCountFormatter.format(totalSessions), color: '#20a47c' },
        { label: '今日新增会话数', value: memoryCountFormatter.format(memories.filter((m) => isSameDay(m.created_at, now) && m.session_id).length), color: '#e49a28' },
      ]
    }
    if (scope === 'task') {
      const tasks = new Set(memories.map((m) => m.task_id).filter(Boolean))
      const inProgress = memories.filter((m) => m.task_id && m.status === 'active').length > 0 ? Math.min(tasks.size, memories.filter((m) => m.status === 'active').length) : 0
      return [
        { label: '总任务数', value: memoryCountFormatter.format(tasks.size), color: '#1677ff' },
        { label: '进行中任务数', value: memoryCountFormatter.format(inProgress), color: '#e49a28' },
        { label: '已完成任务数', value: memoryCountFormatter.format(memories.filter((m) => m.task_id && m.status === 'archived').length), color: '#20a47c' },
      ]
    }
    if (scope === 'agent') {
      const agentCount = new Set(memories.map((m) => m.agent_id).filter(Boolean)).size
      return [
        { label: '总智能体记忆数', value: memoryCountFormatter.format(listTotal), color: '#7b61d1' },
        { label: '覆盖智能体数', value: memoryCountFormatter.format(agentCount), color: '#1677ff' },
        { label: '今日新增记忆数', value: memoryCountFormatter.format(memories.filter((m) => isSameDay(m.created_at, now)).length), color: '#e49a28' },
      ]
    }
    return []
  }, [listTotal, memories, scope])

  const levelStats = scope === 'all' ? [] : buildLevelStats()

  return (
    <PageContainer
      title={pageMeta.title}
      description={pageMeta.description}
      extra={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => void handleRefresh()} loading={loading || statsLoading}>刷新</Button>
        </Space>
      }
    >
      {scope === 'all' ? (
        <Row gutter={[12, 12]}>
          {memoryLevelCards.map(({ level, title, description, color }) => {
            const stats = memoryStats?.level_distribution?.find((item) => item.level === level)
            const detail = statsLoading
              ? '正在统计…'
              : statsError || !stats
                ? '统计暂不可用'
                : `${memoryCountFormatter.format(stats.count)} 条`
            const value = statsLoading || statsError || !stats
              ? '--'
              : memoryRatioFormatter.format(stats.ratio)

            return <Col xs={24} sm={12} xl={6} key={level}>
              <Card className="console-card memory-level-card" variant="borderless">
                <span style={{ background: color }} />
                <div>
                  <Typography.Text strong>{title}</Typography.Text>
                  <Typography.Text type="secondary">{description}</Typography.Text>
                  <Typography.Text type="secondary">{detail}</Typography.Text>
                </div>
                <strong style={{ color }}>{value}</strong>
              </Card>
            </Col>
          })}
        </Row>
      ) : (
        <LevelStatCards stats={levelStats} />
      )}

      <MemorySearchBar
        scope={scope}
        keyword={keyword}
        loading={loading}
        advanced={advanced}
        onKeywordChange={setKeyword}
        onAdvancedChange={setAdvanced}
        onSearch={handleSearch}
        onReset={handleReset}
      />

      {loading ? <FeedbackState status="loading" description="正在加载记忆库…" /> : null}
      {!loading && error ? <FeedbackState status="error" title="记忆加载失败" error={error} action={<Button onClick={() => void loadMemories(1, listPageSize)}>重新加载</Button>} /> : null}
      {!loading && !error ? (
        <Card
          className="console-card"
          title={`${pageMeta.tableTitle}（${listTotal}）`}
          variant="borderless"
        >
          <Table<MemoryItem>
            rowKey="memory_id"
            dataSource={visibleMemories}
            rowSelection={{
              selectedRowKeys: selectedMemoryIds,
              preserveSelectedRowKeys: true,
              onChange: (selectedRowKeys) => setSelectedMemoryIds(selectedRowKeys.map(String)),
            }}
            locale={{ emptyText: '暂无记忆，请先从“记忆数据导入”页面写入数据。' }}
            scroll={{ x: 980 }}
            pagination={{
              current: listPage,
              pageSize: listPageSize,
              total: listTotal,
              showSizeChanger: true,
              showTotal: (total) => `共 ${total} 条`,
              onChange: (page, pageSize) => void loadMemories(page, pageSize),
            }}
            columns={columns}
          />
          {selectedMemoryIds.length > 0 ? (
            <Flex className="memory-delete-toolbar" justify="space-between" align="center" wrap gap={12}>
              <Typography.Text type="secondary">已选择 {selectedMemoryIds.length} 条记忆</Typography.Text>
              <Space>
                <Button onClick={handleToggleSelectAll} disabled={!visibleMemoryIds.length}>
                  {allVisibleSelected ? '取消全选' : '全部选中'}
                </Button>
                <Button type="primary" danger icon={<DeleteOutlined />} onClick={handleDeleteSelected} disabled={!selectedMemoryIds.length}>
                  删除所选记忆
                </Button>
              </Space>
            </Flex>
          ) : null}
        </Card>
      ) : null}

      <Modal title="查看记忆" open={!!viewingMemory} footer={null} onCancel={() => setViewingMemory(null)} width={640}>
        {viewingMemory ? (
          <Flex vertical gap={10}>
            <Typography.Text strong>记忆内容</Typography.Text>
            <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{viewingMemory.content}</Typography.Paragraph>
            {viewingMemory.summary ? <Typography.Paragraph type="secondary" style={{ margin: 0 }}>摘要：{viewingMemory.summary}</Typography.Paragraph> : null}
            <Space wrap>
              <Tag color="blue">ID：{viewingMemory.memory_id}</Tag>
              {viewingMemory.memory_scope ? <Tag>层级：{viewingMemory.memory_scope}</Tag> : null}
              {viewingMemory.memory_type ? <Tag>类型：{viewingMemory.memory_type}</Tag> : null}
              {viewingMemory.status ? <Tag>状态：{viewingMemory.status}</Tag> : null}
              {viewingMemory.scene_id ? <Tag>场景：{viewingMemory.scene_id}</Tag> : null}
              {viewingMemory.importance !== undefined ? <Tag>重要性：{viewingMemory.importance}</Tag> : null}
              {viewingMemory.confidence !== undefined ? <Tag>置信度：{viewingMemory.confidence}</Tag> : null}
            </Space>
            <Typography.Text type="secondary">创建时间：{formatDateTime(viewingMemory.created_at)}</Typography.Text>
            <Typography.Text type="secondary">更新时间：{formatDateTime(viewingMemory.updated_at)}</Typography.Text>
          </Flex>
        ) : null}
      </Modal>

      <Modal title="编辑记忆" open={!!editingMemory} okText="保存" cancelText="取消" confirmLoading={saving} onOk={() => void handleSave()} onCancel={() => setEditingMemory(null)} width={680}>
        <Form<MemoryEditValues> form={editForm} layout="vertical">
          <Form.Item name="content" label="记忆内容" rules={[{ required: true, whitespace: true, message: '请输入记忆内容' }]}>
            <Input.TextArea rows={5} />
          </Form.Item>
          <Form.Item name="summary" label="摘要">
            <Input.TextArea rows={2} placeholder="可选的记忆摘要" />
          </Form.Item>
          <Row gutter={12}>
            <Col span={8}>
              <Form.Item name="status" label="状态">
                <Select options={[
                  { value: 'active', label: '有效' },
                  { value: 'archived', label: '已归档' },
                  { value: 'deleted', label: '已删除' },
                ]} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="importance" label="重要性">
                <InputNumber min={0} max={1} step={0.1} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="confidence" label="置信度">
                <InputNumber min={0} max={1} step={0.1} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="tags" label="标签">
            <Input placeholder="多个标签使用逗号分隔" />
          </Form.Item>
        </Form>
      </Modal>
    </PageContainer>
  )
}
