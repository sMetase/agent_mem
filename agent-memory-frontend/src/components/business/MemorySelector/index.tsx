import { ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { Button, Card, Empty, Flex, Input, Segmented, Space, Table, Tag, Typography } from 'antd'
import type { TableColumnsType } from 'antd'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Key } from 'react'
import type { MemoryItem } from '@/api/types'
import { listMemories } from '@/api/modules/memory'
import { useAppStore } from '@/store'
import { showErrorMessage } from '@/utils/feedback'

const { Text } = Typography

type SelectorLevel = 'user' | 'session' | 'task'

interface MemorySelectorProps {
  /** 已选记忆对象（受控） */
  value: MemoryItem[]
  /** 选中变化回调，直接返回记忆对象集合 */
  onChange: (selected: MemoryItem[]) => void
  /** 初始层级 */
  defaultLevel?: SelectorLevel
}

const levelOptions: Array<{ label: string; value: SelectorLevel }> = [
  { label: '用户级', value: 'user' },
  { label: '会话级', value: 'session' },
  { label: '任务级', value: 'task' },
]

/**
 * 记忆选择器（方案 B）：层级切换 + 列表联动勾选。
 * 供分析功能「选记忆 → 执行分析 → 展示结果」流程使用，记忆管理页与生成页可复用。
 * value/onChange 直接承载 MemoryItem[]，分析侧无需二次查库。
 */
export function MemorySelector({ value, onChange, defaultLevel = 'user' }: MemorySelectorProps) {
  const config = useAppStore((state) => state.config)
  const [level, setLevel] = useState<SelectorLevel>(defaultLevel)
  const [keyword, setKeyword] = useState('')
  const [memories, setMemories] = useState<MemoryItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<unknown>(null)

  // 缓存已加载过的记忆对象，避免跨页/跨层级勾选时对象丢失
  const cacheRef = useRef(new Map<string, MemoryItem>())

  const load = useCallback(async (nextLevel: SelectorLevel, searchKeyword: string) => {
    setLoading(true)
    setError(null)
    try {
      const result = await listMemories({
        userId: config.userId,
        memoryScope: nextLevel,
        pageSize: 100,
      })
      let items = result.items
      const normalizedKeyword = searchKeyword.trim().toLowerCase()
      if (normalizedKeyword) {
        items = items.filter((item) =>
          item.content?.toLowerCase().includes(normalizedKeyword)
          || item.memory_id?.toLowerCase().includes(normalizedKeyword)
          || item.tags?.some((tag) => tag.toLowerCase().includes(normalizedKeyword)),
        )
      }
      items.forEach((item) => cacheRef.current.set(item.memory_id, item))
      setMemories(items)
    } catch (loadError) {
      setError(loadError)
      showErrorMessage(loadError, '加载记忆失败')
    } finally {
      setLoading(false)
    }
  }, [config.userId])

  useEffect(() => {
    void load(level, keyword)
  }, [level, keyword, load])

  const handleLevelChange = (nextLevel: string | number) => {
    setLevel(nextLevel as SelectorLevel)
  }

  const handleSelectionChange = (selectedRowKeys: Key[]) => {
    const selected = selectedRowKeys
      .map((key) => cacheRef.current.get(String(key)))
      .filter((item): item is MemoryItem => Boolean(item))
    onChange(selected)
  }

  const selectedIds = useMemo(() => value.map((item) => item.memory_id), [value])

  const handleToggleAll = () => {
    const visibleIds = memories.map((memory) => memory.memory_id)
    const allSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.includes(id))
    if (allSelected) {
      onChange(value.filter((item) => !visibleIds.includes(item.memory_id)))
    } else {
      const combined = new Map<string, MemoryItem>()
      value.forEach((item) => combined.set(item.memory_id, item))
      memories.forEach((item) => combined.set(item.memory_id, item))
      onChange(Array.from(combined.values()))
    }
  }

  const allVisibleSelected = memories.length > 0 && memories.every((memory) => selectedIds.includes(memory.memory_id))

  const columns: TableColumnsType<MemoryItem> = useMemo(() => {
    const base: TableColumnsType<MemoryItem> = [
      {
        title: '记忆内容',
        dataIndex: 'content',
        ellipsis: true,
        render: (content: string) => <Text ellipsis={{ tooltip: content }}>{content}</Text>,
      },
    ]
    if (level === 'session') {
      base.splice(1, 0, { title: '会话 ID', dataIndex: 'session_id', width: 150, ellipsis: true, render: (value?: string) => value || '-' })
    }
    if (level === 'task') {
      base.splice(1, 0, { title: '任务 ID', dataIndex: 'task_id', width: 150, ellipsis: true, render: (value?: string) => value || '-' })
    }
    base.push({ title: '类型', dataIndex: 'memory_type', width: 90, render: (value?: string) => value ? <Tag>{value}</Tag> : '-' })
    base.push({
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 150,
      render: (value?: string) => value ? new Date(value).toLocaleString('zh-CN') : '-',
    })
    return base
  }, [level])

  return (
    <Card className="console-card memory-selector" title="选择记忆" variant="borderless">
      <Flex gap={10} wrap align="center" style={{ marginBottom: 12 }}>
        <Segmented size="small" value={level} options={levelOptions} onChange={handleLevelChange} />
        <Input
          size="small"
          allowClear
          prefix={<SearchOutlined />}
          placeholder="按内容、ID、标签检索"
          value={keyword}
          style={{ flex: '1 1 220px', minWidth: 0 }}
          onChange={(event) => setKeyword(event.target.value)}
          onPressEnter={() => void load(level, keyword)}
        />
        <Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={() => void load(level, keyword)} />
      </Flex>

      {error ? <Empty description="记忆加载失败，请检查后端连接。" /> : null}
      {!error ? (
        <>
          <Table<MemoryItem>
            size="small"
            rowKey="memory_id"
            loading={loading}
            dataSource={memories}
            columns={columns}
            pagination={{ pageSize: 8, showSizeChanger: false }}
            locale={{ emptyText: '当前层级暂无记忆。' }}
            rowSelection={{
              selectedRowKeys: selectedIds,
              onChange: handleSelectionChange,
            }}
          />
          <Flex justify="space-between" align="center" gap={12} style={{ marginTop: 10 }}>
            <Text type="secondary">已选择 {value.length} 条记忆</Text>
            <Space>
              <Button size="small" onClick={handleToggleAll}>
                {allVisibleSelected ? '取消全选' : '全选本页'}
              </Button>
            </Space>
          </Flex>
        </>
      ) : null}
    </Card>
  )
}
