import { CloudSyncOutlined } from '@ant-design/icons'
import { Alert, App, Button, Select, Space, Typography } from 'antd'
import { useEffect, useState } from 'react'
import type { DataSourceConfig, MemoryImportRecord } from '@/api/types'
import { storageKeys } from '@/constants/storage'
import { getErrorMessage } from '@/utils/error'
import { loadJson } from '@/utils/localStore'
import { parseMemoryImportText } from '@/utils/memoryImport'

interface RemoteImportPanelProps {
  onImported: (records: MemoryImportRecord[]) => void
}

const sourceTypeLabels: Record<DataSourceConfig['sourceType'], string> = {
  openwebui: 'Open-Web-UI',
  external_agent: '外部智能体',
}

/** 远程 API 导入：从已配置数据源拉取对话并清洗。浏览器直连受 CORS 限制；真实定时拉取需后端 worker。 */
export function RemoteImportPanel({ onImported }: RemoteImportPanelProps) {
  const { message } = App.useApp()
  const [sources, setSources] = useState<DataSourceConfig[]>([])
  const [selectedId, setSelectedId] = useState<string | undefined>(undefined)
  const [pulling, setPulling] = useState(false)

  useEffect(() => {
    setSources(loadJson<DataSourceConfig[]>(storageKeys.dataSources, []))
  }, [])

  const handlePull = async () => {
    const source = sources.find((item) => item.id === selectedId)
    if (!source) {
      void message.warning('请先选择数据源')
      return
    }
    if (!source.isActive) {
      void message.warning('该数据源已停用，请先在「外部数据源管理」启用')
      return
    }
    setPulling(true)
    try {
      const response = await fetch(source.baseUrl, {
        headers: source.apiKey ? { Authorization: `Bearer ${source.apiKey}` } : undefined,
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data: unknown = await response.json()
      const records = parseMemoryImportText('remote.json', JSON.stringify(data))
      if (!records.length) throw new Error('未解析到会话数据（接口需返回 OpenWebUI 导出 JSON）')
      onImported(records)
      void message.success(`拉取成功：${records.length} 个会话`)
    } catch (error) {
      void message.error(`拉取失败：${getErrorMessage(error, '跨域或网络错误')}`)
    } finally {
      setPulling(false)
    }
  }

  return (
    <Space orientation="vertical" size={14} style={{ display: 'flex' }}>
      <Alert
        type="info"
        showIcon
        title="远程 API 拉取"
        description="从已配置的外部数据源（Open-Web-UI / 外部智能体）抓取对话并清洗导入。浏览器直连受跨域（CORS）限制；真实定时拉取需后端采集任务。"
      />
      <div>
        <Typography.Text strong>选择数据源</Typography.Text>
        <Typography.Paragraph type="secondary" style={{ margin: '4px 0 8px' }}>
          数据源在「外部数据源管理」页维护。
        </Typography.Paragraph>
        <Space.Compact style={{ width: '100%' }}>
          <Select
            style={{ width: '100%' }}
            showSearch
            optionFilterProp="label"
            value={selectedId}
            placeholder={sources.length ? '选择数据源' : '暂无数据源，请先到「外部数据源管理」添加'}
            onChange={setSelectedId}
            options={sources.map((source) => ({
              value: source.id,
              label: `${source.name}（${sourceTypeLabels[source.sourceType] ?? source.sourceType}）`,
            }))}
          />
          <Button type="primary" icon={<CloudSyncOutlined />} loading={pulling} onClick={() => void handlePull()}>
            立即拉取并导入
          </Button>
        </Space.Compact>
      </div>
    </Space>
  )
}
