import { isAxiosError } from 'axios'
import { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Card, Descriptions, Form, Input, Space, Table, Tag, Typography } from 'antd'
import type { TableColumnsType } from 'antd'
import { createScene, disableScene, listScenes, updateScene } from '@/api/modules/scene'
import type { SceneCreatePayload, SceneInfo } from '@/api/types'
import { FeedbackState, PageContainer, openConfirmDialog } from '@/components/common'
import { useAppStore } from '@/store'
import { normalizeAppConfig } from '@/utils/config'
import { showErrorMessage, showSuccessMessage, showWarningMessage } from '@/utils/feedback'

function formatDateTime(value?: string | null) {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}

export default function SceneManagementPage() {
  const appConfig = useAppStore((state) => state.config)
  const setConfig = useAppStore((state) => state.setConfig)
  const [creating, setCreating] = useState(false)
  const [form] = Form.useForm<SceneCreatePayload>()

  const [scenes, setScenes] = useState<SceneInfo[]>([])
  const [scenesLoading, setScenesLoading] = useState(false)
  const [scenesError, setScenesError] = useState<unknown>(null)
  const [scenesPage, setScenesPage] = useState(1)
  const [scenesPageSize, setScenesPageSize] = useState(20)
  const [scenesTotal, setScenesTotal] = useState(0)
  const [disablingId, setDisablingId] = useState<string | null>(null)
  const [enablingId, setEnablingId] = useState<string | null>(null)

  const loadScenes = useCallback(async (page = 1, pageSize = 20) => {
    setScenesLoading(true)
    setScenesError(null)
    try {
      const result = await listScenes({ page, pageSize })
      setScenes(result.items)
      setScenesTotal(result.total)
      setScenesPage(result.page || page)
      setScenesPageSize(result.page_size || pageSize)
    } catch (error) {
      setScenes([])
      setScenesError(error)
    } finally {
      setScenesLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadScenes()
  }, [loadScenes])

  const handleCreate = async (values: SceneCreatePayload) => {
    setCreating(true)
    try {
      const result = await createScene(values)
      if (result.scene_id) {
        setConfig(normalizeAppConfig({ ...appConfig, sceneId: result.scene_id }))
      }
      form.resetFields()
      showSuccessMessage(result.scene_id ? `场景已创建并启用：${result.scene_id}` : '场景创建成功。')
      await loadScenes(1, scenesPageSize)
    } catch (error) {
      // 后端已加同名校验：409 → 提示「已存在同名场景」。
      if (isAxiosError(error) && error.response?.status === 409) {
        showWarningMessage('已存在同名场景，请更换名称后重试')
      } else {
        showErrorMessage(error, '场景创建失败')
      }
    } finally {
      setCreating(false)
    }
  }

  const handleDisable = (scene: SceneInfo) => {
    openConfirmDialog({
      title: '停用这个场景？',
      content: `场景 ${scene.scene_id} 停用后数据保留，但该场景下的智能体会停止对外服务。`,
      onOk: async () => {
        setDisablingId(scene.scene_id)
        try {
          await disableScene(scene.scene_id)
          showSuccessMessage(`场景已停用：${scene.scene_id}`)
          await loadScenes(scenesPage, scenesPageSize)
        } catch (error) {
          showErrorMessage(error, '停用场景失败')
        } finally {
          setDisablingId(null)
        }
      },
    })
  }

  const handleEnable = async (scene: SceneInfo) => {
    setEnablingId(scene.scene_id)
    try {
      await updateScene(scene.scene_id, { is_active: true })
      showSuccessMessage(`场景已启用：${scene.scene_id}`)
      await loadScenes(scenesPage, scenesPageSize)
    } catch (error) {
      showErrorMessage(error, '启用场景失败')
    } finally {
      setEnablingId(null)
    }
  }

  const columns: TableColumnsType<SceneInfo> = [
    { title: 'Scene ID', dataIndex: 'scene_id', width: 180, ellipsis: true, render: (value: string) => <Typography.Text code>{value}</Typography.Text> },
    { title: '场景名称', dataIndex: 'scene_name', width: 160, render: (value?: string) => value || '-' },
    { title: '场景说明', dataIndex: 'description', ellipsis: true, render: (value?: string) => value || '-' },
    {
      title: '状态',
      dataIndex: 'is_active',
      width: 90,
      render: (value?: boolean) => (
        value === false
          ? <Tag color="default">已停用</Tag>
          : <Tag color="success">启用中</Tag>
      ),
    },
    { title: '创建时间', dataIndex: 'created_at', width: 170, render: formatDateTime },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_: unknown, scene: SceneInfo) => (
        <Space size={4}>
          <Button
            size="small"
            disabled={appConfig.sceneId === scene.scene_id}
            onClick={() => {
              setConfig(normalizeAppConfig({ ...appConfig, sceneId: scene.scene_id }))
              showSuccessMessage(`已切换当前场景：${scene.scene_id}`)
            }}
          >
            {appConfig.sceneId === scene.scene_id ? '当前场景' : '设为当前'}
          </Button>
          {scene.is_active === false ? (
            <Button
              size="small"
              type="primary"
              loading={enablingId === scene.scene_id}
              onClick={() => void handleEnable(scene)}
            >
              启用
            </Button>
          ) : (
            <Button
              size="small"
              danger
              loading={disablingId === scene.scene_id}
              onClick={() => handleDisable(scene)}
            >
              停用
            </Button>
          )}
        </Space>
      ),
    },
  ]

  return (
    <PageContainer
      title="场景标识配置"
      description="使用 Scene ID 隔离不同业务场景中的智能体、任务和记忆数据。"
    >
      <Alert
        type="info"
        showIcon
        title="场景用于数据隔离"
        description="生产线、客服、物流等不同业务建议分别创建场景，后续写入和检索都会携带对应 Scene ID。"
      />
      <Card variant="borderless" title="当前启用场景">
        <Descriptions column={1}>
          <Descriptions.Item label="Scene ID">{appConfig.sceneId || '尚未配置'}</Descriptions.Item>
        </Descriptions>
      </Card>
      <Card variant="borderless" title="创建业务场景">
        <Form<SceneCreatePayload> form={form} layout="vertical" onFinish={(values) => void handleCreate(values)}>
          <Form.Item name="scene_name" label="场景名称" rules={[{ required: true, whitespace: true }]}>
            <Input placeholder="例如：生产线异常处理" />
          </Form.Item>
          <Form.Item name="description" label="场景说明">
            <Input.TextArea rows={4} placeholder="说明该场景中的智能体和记忆用途" />
          </Form.Item>
          <Space>
            <Button type="primary" htmlType="submit" loading={creating}>创建并启用场景</Button>
            <Button loading={scenesLoading} onClick={() => void loadScenes(scenesPage, scenesPageSize)}>刷新列表</Button>
          </Space>
        </Form>
      </Card>

      <Card
        variant="borderless"
        title={`已创建场景（${scenesTotal}）`}
      >
        {scenesLoading ? <FeedbackState status="loading" description="正在加载场景列表…" /> : null}
        {!scenesLoading && scenesError ? (
          <FeedbackState
            status="error"
            title="场景列表加载失败"
            error={scenesError}
            action={<Button onClick={() => void loadScenes(1, scenesPageSize)}>重新加载</Button>}
          />
        ) : null}
        {!scenesLoading && !scenesError ? (
          <Table<SceneInfo>
            rowKey="scene_id"
            dataSource={scenes}
            locale={{ emptyText: '暂无已创建场景，请在上方表单创建第一个业务场景。' }}
            scroll={{ x: 860 }}
            pagination={{
              current: scenesPage,
              pageSize: scenesPageSize,
              total: scenesTotal,
              showSizeChanger: true,
              showTotal: (total) => `共 ${total} 个场景`,
              onChange: (page, pageSize) => void loadScenes(page, pageSize),
            }}
            columns={columns}
          />
        ) : null}
      </Card>
    </PageContainer>
  )
}
