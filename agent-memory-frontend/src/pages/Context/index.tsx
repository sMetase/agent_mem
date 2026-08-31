import { SendOutlined } from '@ant-design/icons'
import {
  Button,
  Card,
  Col,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Tag,
  Typography,
} from 'antd'
import { useEffect, useState } from 'react'
import type { MemoryContextResult } from '@/api/types'
import { getMemoryContext } from '@/api/modules/memory'
import { listAgents } from '@/api/modules/agent'
import { listScenes } from '@/api/modules/scene'
import { FeedbackState, PageContainer } from '@/components/common'
import { useAppStore } from '@/store'
import { showErrorMessage } from '@/utils/feedback'
import { DifferentiatedResult } from '@/pages/Context/DifferentiatedResult'

interface ContextFormValues {
  query: string
  topK: number
  sceneId?: string
  agentId?: string
}

interface OptionItem {
  value: string
  label: string
}

export default function ContextPage() {
  const config = useAppStore((state) => state.config)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<MemoryContextResult | null>(null)
  const [sceneOptions, setSceneOptions] = useState<OptionItem[]>([])
  const [agentOptions, setAgentOptions] = useState<OptionItem[]>([])

  useEffect(() => {
    listScenes({ isActive: true })
      .then((data) => setSceneOptions(data.items.map((scene) => ({
        value: scene.scene_id,
        label: scene.scene_name ?? scene.scene_id,
      }))))
      .catch(() => setSceneOptions([]))
    listAgents({ isActive: true })
      .then((data) => setAgentOptions(data.items.map((agent) => ({
        value: agent.agent_id,
        label: agent.agent_name ?? agent.agent_id,
      }))))
      .catch(() => setAgentOptions([]))
  }, [])

  const handleGenerate = async (values: ContextFormValues) => {
    setLoading(true)
    try {
      setResult(await getMemoryContext({
        query: values.query.trim(),
        user_id: config.userId,
        scene_id: values.sceneId?.trim() || undefined,
        agent_id: values.agentId?.trim() || undefined,
        top_k: values.topK,
      }))
    } catch (error) {
      setResult(null)
      showErrorMessage(error, '上下文生成失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <PageContainer
      title="记忆上下文返回"
      description="根据查询检索相关记忆并组织为 Prompt 上下文片段，供外部智能体注入使用。"
      extra={<Tag color="green">非实时聊天模块</Tag>}
    >
      <Row gutter={[14, 14]}>
        <Col xs={24} xl={9}>
          <Card className="console-card" title="上下文请求" variant="borderless">
            <Form<ContextFormValues>
              layout="vertical"
              initialValues={{ topK: 10 }}
              onFinish={(values) => void handleGenerate(values)}
            >
              <Form.Item name="query" label="查询内容" rules={[{ required: true, whitespace: true, message: '请输入查询内容' }]}>
                <Input.TextArea rows={5} placeholder="例如：为物流调度任务返回用户偏好、历史决策和未完成事项" />
              </Form.Item>
              <Form.Item name="topK" label="候选记忆数量">
                <InputNumber min={1} max={50} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="sceneId" label="场景（可选）">
                <Select
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  placeholder={sceneOptions.length ? '选择场景' : '暂无可选场景'}
                  options={sceneOptions}
                />
              </Form.Item>
              <Form.Item name="agentId" label="智能体（可选）">
                <Select
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  placeholder={agentOptions.length ? '选择智能体' : '暂无可选智能体'}
                  options={agentOptions}
                />
              </Form.Item>
              <Button type="primary" htmlType="submit" icon={<SendOutlined />} loading={loading} block>
                生成上下文
              </Button>
            </Form>
          </Card>
        </Col>
        <Col xs={24} xl={15}>
          <Card
            className="console-card context-preview-card"
            title="上下文返回预览"
            extra={<Tag color="blue">综合视图</Tag>}
            variant="borderless"
          >
            {loading ? <FeedbackState status="loading" description="正在筛选并组织记忆上下文…" /> : null}
            {!loading && !result ? (
              <div className="context-placeholder">
                <SendOutlined />
                <Typography.Title level={5}>等待生成上下文</Typography.Title>
                <Typography.Text type="secondary">填写左侧查询条件后，可在此查看接口实际返回。</Typography.Text>
              </div>
            ) : null}
            {!loading && result ? (
              <DifferentiatedResult kind="all" result={result} />
            ) : null}
          </Card>
          {result ? (
            <Row gutter={12} style={{ marginTop: 14 }}>
              <Col span={8}><Card className="console-card result-stat"><Typography.Text type="secondary">引用记忆</Typography.Text><strong>{result.memory_count}</strong></Card></Col>
              <Col span={8}><Card className="console-card result-stat"><Typography.Text type="secondary">预估 Token</Typography.Text><strong>{result.estimated_tokens ?? '-'}</strong></Card></Col>
              <Col span={8}><Card className="console-card result-stat"><Typography.Text type="secondary">返回状态</Typography.Text><strong style={{ color: '#20a47c' }}>已生成</strong></Card></Col>
            </Row>
          ) : null}
        </Col>
      </Row>
    </PageContainer>
  )
}
