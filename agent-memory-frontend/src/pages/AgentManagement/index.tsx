import { KeyOutlined, ReloadOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Descriptions, Flex, Modal, Select, Space, Table, Tag, Typography } from 'antd'
import type { TableColumnsType } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { listAgents, rotateAgentKey, updateAgent } from '@/api/modules/agent'
import { listScenes } from '@/api/modules/scene'
import type { AgentInfo } from '@/api/types'
import { FeedbackState, PageContainer, openConfirmDialog } from '@/components/common'
import { useAppStore } from '@/store'
import { showErrorMessage, showSuccessMessage } from '@/utils/feedback'

const { Text } = Typography

interface OptionItem {
  value: string
  label: string
}

interface RotatedKeyInfo {
  agentId: string
  agentName?: string
  apiKey: string
}

function formatDateTime(value?: string | null) {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}

export default function AgentManagementPage() {
  const config = useAppStore((state) => state.config)
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [sceneOptions, setSceneOptions] = useState<OptionItem[]>([])
  const [sceneFilter, setSceneFilter] = useState<string | undefined>(undefined)
  const [togglingId, setTogglingId] = useState<string | null>(null)
  const [rotatedKey, setRotatedKey] = useState<RotatedKeyInfo | null>(null)

  useEffect(() => {
    listScenes({ isActive: true })
      .then((data) => setSceneOptions(data.items.map((scene) => ({
        value: scene.scene_id,
        label: scene.scene_name ?? scene.scene_id,
      }))))
      .catch(() => setSceneOptions([]))
  }, [])

  const loadAgents = useCallback(async (nextPage = 1, nextPageSize = pageSize, sceneId?: string) => {
    setLoading(true)
    setError(null)
    try {
      const result = await listAgents({ sceneId: sceneId?.trim() || undefined, page: nextPage, pageSize: nextPageSize })
      setAgents(result.items)
      setTotal(result.total)
      setPage(result.page || nextPage)
      setPageSize(result.page_size || nextPageSize)
    } catch (loadError) {
      setAgents([])
      setError(loadError)
    } finally {
      setLoading(false)
    }
  }, [pageSize])

  useEffect(() => {
    void loadAgents(1, pageSize, sceneFilter)
  }, [sceneFilter, loadAgents, pageSize])

  const handleToggle = (agent: AgentInfo) => {
    const nextActive = agent.is_active === false
    openConfirmDialog({
      title: nextActive ? '启用这个智能体？' : '停用这个智能体？',
      content: nextActive
        ? `智能体 ${agent.agent_name ?? agent.agent_id} 启用后恢复对外服务。`
        : `智能体 ${agent.agent_name ?? agent.agent_id} 停用后数据保留，但停止对外服务。`,
      onOk: async () => {
        setTogglingId(agent.agent_id)
        try {
          await updateAgent(agent.agent_id, { is_active: nextActive })
          showSuccessMessage(nextActive ? '智能体已启用' : '智能体已停用')
          await loadAgents(page, pageSize, sceneFilter)
        } catch (toggleError) {
          showErrorMessage(toggleError, nextActive ? '启用智能体失败' : '停用智能体失败')
        } finally {
          setTogglingId(null)
        }
      },
    })
  }

  const handleRotate = (agent: AgentInfo) => {
    openConfirmDialog({
      title: '轮换 API Key？',
      content: `智能体 ${agent.agent_name ?? agent.agent_id} 的旧 Key 将立即失效，新 Key 仅显示一次。`,
      onOk: async () => {
        try {
          const result = await rotateAgentKey(agent.agent_id)
          setRotatedKey({ agentId: agent.agent_id, agentName: agent.agent_name, apiKey: result.api_key })
        } catch (rotateError) {
          showErrorMessage(rotateError, 'API Key 轮换失败')
        }
      },
    })
  }

  const handleCopyNewKey = async () => {
    if (!rotatedKey) return
    try {
      await navigator.clipboard?.writeText(rotatedKey.apiKey)
      showSuccessMessage('API Key 已复制到剪贴板')
    } catch {
      showErrorMessage(new Error('剪贴板不可用'), '复制失败，请手动选择复制')
    }
  }

  const columns: TableColumnsType<AgentInfo> = [
    { title: '智能体名称', dataIndex: 'agent_name', width: 180, ellipsis: true, render: (value?: string, record?: AgentInfo) => <Text>{value || record?.agent_id || '-'}</Text> },
    { title: '所属场景', dataIndex: 'scene_id', width: 150, ellipsis: true, render: (value?: string) => value ? <Tag color="cyan">{value}</Tag> : '-' },
    {
      title: '状态',
      dataIndex: 'is_active',
      width: 90,
      render: (value?: boolean) => (
        value === false ? <Tag color="default">已停用</Tag> : <Tag color="success">启用中</Tag>
      ),
    },
    { title: 'API Key 前缀', dataIndex: 'api_key_prefix', width: 130, render: (value?: string) => value || 'mem_****' },
    { title: 'LLM 模型', dataIndex: 'llm_model', width: 140, render: (value?: string | null) => value || <Text type="secondary">全局默认</Text> },
    { title: '创建时间', dataIndex: 'created_at', width: 170, render: formatDateTime },
    {
      title: '操作',
      key: 'action',
      width: 150,
      render: (_: unknown, agent: AgentInfo) => (
        <Space size={4}>
          <Button
            size="small"
            type={agent.is_active === false ? 'primary' : 'default'}
            loading={togglingId === agent.agent_id}
            onClick={() => handleToggle(agent)}
          >
            {agent.is_active === false ? '启用' : '停用'}
          </Button>
          <Button size="small" icon={<KeyOutlined />} onClick={() => handleRotate(agent)}>
            换 key
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <PageContainer
      title="智能体管理"
      description="查看当前用户的智能体列表，管理启停状态与 API Key。"
      extra={(
        <Space>
          <Text type="secondary">当前用户：{config.userId}</Text>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void loadAgents(page, pageSize, sceneFilter)}>刷新</Button>
        </Space>
      )}
    >
      <Alert
        type="info"
        showIcon
        title="API Key 前缀脱敏展示"
        description="列表中仅展示 Key 前缀（mem_****）；完整明文只在注册或轮换时弹窗显示一次，请妥善保存。"
        style={{ marginBottom: 14 }}
      />

      <Card className="console-card" variant="borderless">
        <Flex justify="space-between" align="center" wrap gap={12} style={{ marginBottom: 14 }}>
          <Text strong>智能体列表（{total}）</Text>
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            style={{ width: 260 }}
            placeholder={sceneOptions.length ? '按场景过滤' : '暂无可选场景'}
            value={sceneFilter}
            onChange={(value) => setSceneFilter(value)}
            options={sceneOptions}
          />
        </Flex>

        {loading ? <FeedbackState status="loading" description="正在加载智能体列表…" /> : null}
        {!loading && error ? (
          <FeedbackState
            status="error"
            title="智能体列表加载失败"
            error={error}
            action={<Button onClick={() => void loadAgents(1, pageSize, sceneFilter)}>重新加载</Button>}
          />
        ) : null}
        {!loading && !error ? (
          <Table<AgentInfo>
            rowKey="agent_id"
            dataSource={agents}
            locale={{ emptyText: '暂无已注册智能体，请先到「智能体注册接入」注册。' }}
            scroll={{ x: 1020 }}
            pagination={{
              current: page,
              pageSize,
              total,
              showSizeChanger: true,
              showTotal: (count) => `共 ${count} 个智能体`,
              onChange: (nextPage, nextPageSize) => void loadAgents(nextPage, nextPageSize, sceneFilter),
            }}
            columns={columns}
          />
        ) : null}
      </Card>

      <Modal
        open={!!rotatedKey}
        title="API Key 已轮换"
        closable={false}
        footer={[
          <Button key="copy" type="primary" onClick={() => void handleCopyNewKey()}>复制 API Key</Button>,
          <Button key="close" onClick={() => setRotatedKey(null)}>我已妥善保存</Button>,
        ]}
      >
        <Alert
          type="warning"
          showIcon
          title="新 API Key 仅显示一次"
          description="请立即复制并妥善保存；关闭弹窗后不可再次查看，旧 Key 已失效。"
          style={{ marginBottom: 16 }}
        />
        <Descriptions column={1} bordered size="small">
          <Descriptions.Item label="Agent ID">{rotatedKey?.agentId}</Descriptions.Item>
          {rotatedKey?.agentName ? <Descriptions.Item label="智能体名称">{rotatedKey.agentName}</Descriptions.Item> : null}
          <Descriptions.Item label="API Key">{rotatedKey?.apiKey}</Descriptions.Item>
        </Descriptions>
      </Modal>
    </PageContainer>
  )
}
