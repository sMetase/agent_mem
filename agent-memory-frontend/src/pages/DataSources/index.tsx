import { CloudSyncOutlined, PlusOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Flex,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { TableColumnsType } from 'antd'
import { useState } from 'react'
import type { DataSourceConfig, DataSourceType } from '@/api/types'
import { PageContainer, openConfirmDialog } from '@/components/common'
import { storageKeys } from '@/constants/storage'
import { showErrorMessage, showSuccessMessage } from '@/utils/feedback'
import { loadJson, saveJson } from '@/utils/localStore'
import { parseMemoryImportText } from '@/utils/memoryImport'

const { Text } = Typography

const sourceTypeOptions = [
  { value: 'openwebui', label: 'Open-Web-UI' },
  { value: 'external_agent', label: '外部智能体' },
]

const sourceTypeLabels: Record<DataSourceType, string> = {
  openwebui: 'Open-Web-UI',
  external_agent: '外部智能体',
}

function createId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

function formatTime(value?: string) {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}

interface DataSourceFormValues {
  name: string
  sourceType: DataSourceType
  baseUrl: string
  apiKey?: string
}

export default function DataSourcesPage() {
  const [form] = Form.useForm<DataSourceFormValues>()
  const [sources, setSources] = useState<DataSourceConfig[]>(() => loadJson<DataSourceConfig[]>(storageKeys.dataSources, []))
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<DataSourceConfig | null>(null)
  const [pullingId, setPullingId] = useState<string | null>(null)

  const persist = (next: DataSourceConfig[]) => {
    setSources(next)
    saveJson(storageKeys.dataSources, next)
  }

  const openAdd = () => {
    setEditing(null)
    form.resetFields()
    setModalOpen(true)
  }

  const openEdit = (source: DataSourceConfig) => {
    setEditing(source)
    form.setFieldsValue(source)
    setModalOpen(true)
  }

  const handleSubmit = async () => {
    let values: DataSourceFormValues
    try {
      values = await form.validateFields()
    } catch {
      return
    }
    if (editing) {
      persist(sources.map((source) => (
        source.id === editing.id ? { ...source, ...values } : source
      )))
    } else {
      persist([...sources, {
        id: createId(),
        ...values,
        apiKey: values.apiKey?.trim() || undefined,
        isActive: true,
        createdAt: new Date().toISOString(),
      }])
    }
    setModalOpen(false)
  }

  const handleToggle = (source: DataSourceConfig) => {
    persist(sources.map((item) => (
      item.id === source.id ? { ...item, isActive: !item.isActive } : item
    )))
  }

  const handleDelete = (source: DataSourceConfig) => {
    openConfirmDialog({
      title: '删除这个数据源？',
      content: `数据源「${source.name}」将从本地移除。`,
      onOk: () => {
        persist(sources.filter((item) => item.id !== source.id))
      },
    })
  }

  /** 立即拉取：前端直接请求接入源，解析 OpenWebUI 格式对话（受 CORS 限制；真实定时拉取需后端 worker）。 */
  const handlePull = async (source: DataSourceConfig) => {
    setPullingId(source.id)
    let result: 'success' | 'failed' = 'failed'
    let count = 0
    try {
      const response = await fetch(source.baseUrl, {
        headers: source.apiKey ? { Authorization: `Bearer ${source.apiKey}` } : undefined,
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data: unknown = await response.json()
      const records = parseMemoryImportText('remote.json', JSON.stringify(data))
      count = records.length
      if (count) {
        result = 'success'
      }
    } catch (error) {
      showErrorMessage(error, `${source.name} 拉取失败（跨域或网络错误）`)
    } finally {
      persist(sources.map((item) => (
        item.id === source.id
          ? { ...item, lastPullAt: new Date().toISOString(), lastResult: result, lastPullCount: count }
          : item
      )))
      setPullingId(null)
    }
    if (result === 'success') {
      showSuccessMessage(`${source.name} 拉取成功：${count} 个会话`)
    }
  }

  const columns: TableColumnsType<DataSourceConfig> = [
    { title: '名称', dataIndex: 'name', ellipsis: true, render: (value?: string) => value || '-' },
    {
      title: '类型',
      dataIndex: 'sourceType',
      width: 130,
      render: (value: DataSourceType) => <Tag color={value === 'openwebui' ? 'blue' : 'purple'}>{sourceTypeLabels[value] ?? value}</Tag>,
    },
    { title: '接入地址', dataIndex: 'baseUrl', ellipsis: true, render: (value?: string) => value || '-' },
    {
      title: '状态',
      dataIndex: 'isActive',
      width: 80,
      render: (value: boolean, record: DataSourceConfig) => (
        <Switch checked={value} onChange={() => handleToggle(record)} />
      ),
    },
    { title: '最近拉取', dataIndex: 'lastPullAt', width: 160, render: formatTime },
    {
      title: '上次结果',
      dataIndex: 'lastResult',
      width: 110,
      render: (value?: string, record?: DataSourceConfig) => (
        value === 'success'
          ? <Tag color="success">成功（{record?.lastPullCount ?? '-'}）</Tag>
          : value === 'failed'
            ? <Tag color="error">失败</Tag>
            : <Tag>未拉取</Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_: unknown, record: DataSourceConfig) => (
        <Space size={4}>
          <Button
            size="small"
            icon={<CloudSyncOutlined />}
            loading={pullingId === record.id}
            onClick={() => void handlePull(record)}
          >
            立即拉取
          </Button>
          <Button size="small" onClick={() => openEdit(record)}>编辑</Button>
          <Button size="small" danger onClick={() => handleDelete(record)}>删除</Button>
        </Space>
      ),
    },
  ]

  return (
    <PageContainer
      title="外部数据源管理"
      description="管理多条远程对话数据源（Open-Web-UI / 外部智能体），供「远程 API 导入」拉取使用。"
    >
      <Card className="console-card" variant="borderless">
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 14 }}
          title="配置保存在当前浏览器"
          description="「立即拉取」由浏览器直接请求接入源，受跨域（CORS）限制；真实定时拉取需后端采集任务（见《后端改造清单0824》）。"
        />
        <Flex justify="space-between" align="center" wrap gap={12} style={{ marginBottom: 14 }}>
          <Text type="secondary">共 {sources.length} 个数据源（{sources.filter((item) => item.isActive).length} 个启用）</Text>
          <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>新增数据源</Button>
        </Flex>
        <Table<DataSourceConfig>
          size="small"
          rowKey="id"
          dataSource={sources}
          locale={{ emptyText: '暂无数据源，点击「新增数据源」添加。' }}
          scroll={{ x: 900 }}
          pagination={false}
          columns={columns}
        />
      </Card>

      <Modal
        open={modalOpen}
        title={editing ? '编辑数据源' : '新增数据源'}
        okText="保存"
        cancelText="取消"
        onOk={() => void handleSubmit()}
        onCancel={() => setModalOpen(false)}
        width={560}
      >
        <Form<DataSourceFormValues> form={form} layout="vertical" preserve={false}>
          <Form.Item name="name" label="数据源名称" rules={[{ required: true, whitespace: true, message: '请输入数据源名称' }]}>
            <Input placeholder="例如：Open-Web-UI 生产环境" />
          </Form.Item>
          <Form.Item name="sourceType" label="数据源类型" rules={[{ required: true }]}>
            <Select options={sourceTypeOptions} />
          </Form.Item>
          <Form.Item name="baseUrl" label="接入地址" rules={[{ required: true, whitespace: true, message: '请输入接入地址' }]}>
            <Input placeholder="http://10.0.0.5:8080/api/…（返回 OpenWebUI 导出 JSON）" />
          </Form.Item>
          <Form.Item name="apiKey" label="API Key（可选）">
            <Input.Password placeholder="访问该数据源所需的 API Key" />
          </Form.Item>
        </Form>
      </Modal>
    </PageContainer>
  )
}
