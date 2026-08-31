import { isAxiosError } from 'axios'
import { CopyOutlined } from '@ant-design/icons'
import { useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Modal,
  Segmented,
  Select,
  Space,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import { registerAgent } from '@/api/modules/agent'
import { listScenes } from '@/api/modules/scene'
import type { AgentRegisterPayload, AgentCollectionConfig, SceneInfo } from '@/api/types'
import { PageContainer } from '@/components/common'
import {
  agentPlatformOptions,
  collectionModeOptions,
  getPlatformMeta,
  scheduleFrequencyOptions,
} from '@/constants/platform'
import type { AgentPlatform } from '@/constants/platform'
import { useAppStore } from '@/store'
import { normalizeAppConfig } from '@/utils/config'
import { showErrorMessage, showSuccessMessage, showWarningMessage } from '@/utils/feedback'

const { Text } = Typography

type AgentAccessTab = 'register' | 'attach'

interface AgentAttachValues extends AgentCollectionConfig {
  agentId: string
  sceneId: string
}

export default function AgentAccessPage() {
  const appConfig = useAppStore((state) => state.config)
  const setConfig = useAppStore((state) => state.setConfig)
  const [tab, setTab] = useState<AgentAccessTab>('register')
  const [registering, setRegistering] = useState(false)
  const [saving, setSaving] = useState(false)
  const [credentialToShow, setCredentialToShow] = useState<{ agentId: string; apiKey: string } | null>(null)
  const [platform, setPlatform] = useState<AgentPlatform>('dify')
  const [collectionMode, setCollectionMode] = useState<'manual' | 'scheduled'>('manual')
  const [scheduleFrequency, setScheduleFrequency] = useState<'hourly' | 'daily' | 'custom'>('hourly')
  const [sceneOptions, setSceneOptions] = useState<SceneInfo[]>([])

  // 注册表单的 Scene 从真实场景列表下拉选择，避免手填不存在的 scene_id 导致 404。
  useEffect(() => {
    listScenes({ isActive: true })
      .then((result) => setSceneOptions(result.items))
      .catch(() => setSceneOptions([]))
  }, [])

  const handleRegister = async (values: AgentRegisterPayload) => {
    setRegistering(true)
    try {
      const result = await registerAgent(values)
      setConfig(normalizeAppConfig({
        ...appConfig,
        sceneId: values.scene_id,
        agentId: result.agent_id,
        apiKey: result.api_key,
      }))
      // API Key 仅此一次明文返回：弹窗展示一次，关闭后不可再查看（轮换需走 rotate-key）。
      setCredentialToShow({ agentId: result.agent_id, apiKey: result.api_key })
      showSuccessMessage('智能体注册成功，请在弹出的窗口妥善保存 API Key。')
    } catch (error) {
      // 后端已加同名校验：409 → 提示「已存在同名智能体」。
      if (isAxiosError(error) && error.response?.status === 409) {
        showWarningMessage('已存在同名智能体，请更换名称后重试')
      } else {
        showErrorMessage(error, '智能体注册失败')
      }
    } finally {
      setRegistering(false)
    }
  }

  const handleCopyApiKey = async () => {
    if (!credentialToShow) return
    try {
      await navigator.clipboard?.writeText(credentialToShow.apiKey)
      showSuccessMessage('API Key 已复制到剪贴板')
    } catch {
      showWarningMessage('复制失败，请手动选择复制')
    }
  }

  const handleAttach = async (values: AgentAttachValues) => {
    const normalizedAgentId = values.agentId.trim()
    const normalizedSceneId = values.sceneId.trim()
    if (!normalizedAgentId) {
      showWarningMessage('请输入 Agent ID')
      return
    }
    if (!normalizedSceneId) {
      showWarningMessage('请输入所属 Scene ID')
      return
    }
    setSaving(true)
    try {
      const collectionConfig: AgentCollectionConfig = {
        platform,
        collectionMode,
        scheduleFrequency,
        customIntervalMinutes: values.customIntervalMinutes,
        apiKey: values.apiKey?.trim() || undefined,
        apiBaseUrl: values.apiBaseUrl?.trim() || undefined,
        conversationId: values.conversationId?.trim() || undefined,
        agentId: values.agentId?.trim() || undefined,
        accessKeyId: values.accessKeyId?.trim() || undefined,
        accessKeySecret: values.accessKeySecret?.trim() || undefined,
        token: values.token?.trim() || undefined,
        user: values.user?.trim() || undefined,
        userId: values.userId?.trim() || undefined,
        deviceId: values.deviceId?.trim() || undefined,
      }
      // 写入本地配置，供后续采集任务使用
      localStorage.setItem('agent-collection-config', JSON.stringify(collectionConfig))
      setConfig(normalizeAppConfig({
        ...appConfig,
        agentId: normalizedAgentId,
        sceneId: normalizedSceneId,
        apiKey: values.apiKey?.trim() || appConfig.apiKey,
      }))
      showSuccessMessage('智能体接入配置已保存，采集配置已就绪。')
    } finally {
      setSaving(false)
    }
  }

  const accessStatus = appConfig.agentId
    ? <Tag color="success">已接入</Tag>
    : <Tag color="warning">未接入</Tag>

  const platformMeta = getPlatformMeta(platform)

  return (
    <PageContainer
      title="智能体注册接入"
      description="注册新智能体或接入外部智能体数据采集，为记忆读写建立身份凭据。"
    >
      <Alert
        type="info"
        showIcon
        title="注册与接入的区别"
        description="注册用于创建全新智能体身份（自动生成 Agent ID 和 API Key）；接入用于绑定外部智能体并配置数据采集（平台来源 + 采集频次）。"
      />

      <Segmented
        block
        style={{ maxWidth: 420, margin: '16px 0' }}
        value={tab}
        options={[
          { label: '注册智能体', value: 'register' },
          { label: '接入外部智能体', value: 'attach' },
        ]}
        onChange={(value) => setTab(value as AgentAccessTab)}
      />

      <Card variant="borderless" title={(
        <Space>
          当前接入身份
          {accessStatus}
        </Space>
      )}>
        <Descriptions column={{ xs: 1, sm: 2, lg: 3 }}>
          <Descriptions.Item label="Agent ID">{appConfig.agentId || '尚未接入'}</Descriptions.Item>
          <Descriptions.Item label="Scene ID">{appConfig.sceneId || '尚未配置'}</Descriptions.Item>
          <Descriptions.Item label="凭据状态">{appConfig.apiKey ? '已保存' : '未保存'}</Descriptions.Item>
        </Descriptions>
      </Card>

      {tab === 'register' ? (
        <Card variant="borderless" title="注册新智能体">
          <Alert
            type="info"
            showIcon
            title="注册前请先准备业务场景"
            description="智能体必须归属一个 Scene ID。注册成功后，系统会自动保存返回的 Agent ID 和 API Key。"
            style={{ marginBottom: 16 }}
          />
          <Form<AgentRegisterPayload>
            layout="vertical"
            initialValues={{
              permissions: ['read', 'write'],
            }}
            onFinish={(values) => void handleRegister(values)}
          >
            <Form.Item name="agent_name" label="智能体名称" rules={[{ required: true, whitespace: true }]}>
              <Input placeholder="例如：物流调度智能体" />
            </Form.Item>
            <Form.Item
              name="scene_id"
              label="所属场景"
              rules={[{ required: true, message: '请选择智能体所属场景' }]}
              extra="数据源为「场景标识配置」中启用的场景，避免手填不存在的场景导致 404。"
            >
              <Select
                placeholder={sceneOptions.length ? '选择所属场景' : '暂无可选场景，请先到「场景标识配置」创建'}
                options={sceneOptions.map((scene) => ({
                  value: scene.scene_id,
                  label: `${scene.scene_name ?? scene.scene_id}（${scene.scene_id}）`,
                }))}
                showSearch
                optionFilterProp="label"
              />
            </Form.Item>
            <Form.Item
              name="llm_model"
              label="LLM 模型（可选）"
            >
              <Input placeholder="deepseek-chat（留空用全局默认）" />
            </Form.Item>
            <Form.Item
              name="llm_api_key"
              label="LLM API Key（可选）"
            >
              <Input.Password placeholder="留空用全局默认" />
            </Form.Item>
            <Form.Item
              name="permissions"
              label={(
                <Space size={6}>
                  记忆权限
                  <Tooltip title="read/write 权限校验后端暂未启用（治理层方案 B 下一迭代），当前为预留项，注册仍会带上默认权限。">
                    <Tag color="default">未生效</Tag>
                  </Tooltip>
                </Space>
              )}
            >
              <Checkbox.Group disabled options={[
                { label: '读取记忆', value: 'read' },
                { label: '写入记忆', value: 'write' },
              ]} />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={registering}>注册智能体</Button>
          </Form>
        </Card>
      ) : (
        <Card variant="borderless" title="接入外部智能体（数据采集入口）">
          <Alert
            type="info"
            showIcon
            title="拉取外部智能体对话历史并写入记忆库"
            description="选择接入平台并填写对应凭据，配置采集频次后，系统可拉取该平台的对话记录写入系统记忆。"
            style={{ marginBottom: 16 }}
          />
          <Form<AgentAttachValues>
            layout="vertical"
            initialValues={{
              agentId: appConfig.agentId,
              sceneId: appConfig.sceneId,
            }}
            onFinish={(values) => void handleAttach(values)}
          >
            <Form.Item label="接入平台" required>
              <Select
                value={platform}
                onChange={(value) => setPlatform(value as AgentPlatform)}
                options={agentPlatformOptions.map((option) => ({
                  value: option.value,
                  label: `${option.label}（${option.description}）`,
                }))}
              />
            </Form.Item>

            {platformMeta ? (
              <>
                <Form.Item label="平台接入说明">
                  <Text type="secondary">{platformMeta.apiNote}</Text>
                </Form.Item>
                {platformMeta.fields.map((field) => (
                  <Form.Item
                    key={field.name}
                    name={field.name}
                    label={field.label}
                    rules={field.required ? [{ required: true, whitespace: true, message: `请输入${field.label}` }] : undefined}
                  >
                    {field.secret ? <Input.Password placeholder={field.placeholder} /> : <Input placeholder={field.placeholder} />}
                  </Form.Item>
                ))}
              </>
            ) : null}

            <Form.Item label="归属智能体" required style={{ marginTop: 16 }}>
              <Space.Compact style={{ width: '100%' }}>
                <Form.Item name="agentId" noStyle rules={[{ required: true, whitespace: true, message: '请输入 Agent ID' }]}>
                  <Input placeholder="agent_xxx（写入记忆时归属的智能体）" />
                </Form.Item>
              </Space.Compact>
            </Form.Item>
            <Form.Item name="sceneId" label="所属 Scene ID" rules={[{ required: true, whitespace: true, message: '请输入 Scene ID' }]}>
              <Input placeholder="例如：logistics-dispatch" />
            </Form.Item>

            <div className="agent-collection-section">
              <Typography.Title level={5} style={{ marginTop: 0 }}>采集频次配置</Typography.Title>
              <Form.Item label="采集模式">
                <Segmented
                  block
                  value={collectionMode}
                  options={collectionModeOptions}
                  onChange={(value) => setCollectionMode(value as 'manual' | 'scheduled')}
                />
              </Form.Item>
              {collectionMode === 'scheduled' ? (
                <>
                  <Form.Item label="采集周期">
                    <Select
                      value={scheduleFrequency}
                      onChange={(value) => setScheduleFrequency(value as 'hourly' | 'daily' | 'custom')}
                      options={scheduleFrequencyOptions}
                    />
                  </Form.Item>
                  {scheduleFrequency === 'custom' ? (
                    <Form.Item name="customIntervalMinutes" label="自定义间隔（分钟）">
                      <InputNumber min={5} max={43200} style={{ width: 220 }} placeholder="例如 30" />
                    </Form.Item>
                  ) : null}
                </>
              ) : null}
            </div>

            <Button type="primary" htmlType="submit" loading={saving}>保存接入与采集配置</Button>
          </Form>
        </Card>
      )}

      <Modal
        open={!!credentialToShow}
        title="智能体注册成功"
        closable={false}
        footer={[
          <Button key="copy" type="primary" icon={<CopyOutlined />} onClick={() => void handleCopyApiKey()}>复制 API Key</Button>,
          <Button key="close" onClick={() => setCredentialToShow(null)}>我已妥善保存</Button>,
        ]}
      >
        <Alert
          type="warning"
          showIcon
          title="API Key 仅显示一次"
          description="请立即复制并妥善保存；关闭弹窗后不可再次查看，丢失需在「智能体管理」中轮换 API Key。"
          style={{ marginBottom: 16 }}
        />
        <Descriptions column={1} bordered size="small">
          <Descriptions.Item label="Agent ID">{credentialToShow?.agentId}</Descriptions.Item>
          <Descriptions.Item label="API Key">{credentialToShow?.apiKey}</Descriptions.Item>
        </Descriptions>
      </Modal>
    </PageContainer>
  )
}
