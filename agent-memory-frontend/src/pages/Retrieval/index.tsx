import { SearchOutlined } from '@ant-design/icons'
import {
  Button,
  Card,
  Col,
  Empty,
  Flex,
  Form,
  Input,
  InputNumber,
  Progress,
  Row,
  Select,
  Space,
  Tag,
  Typography,
} from 'antd'
import { useEffect, useState } from 'react'
import type { MemorySearchResult } from '@/api/types'
import { searchMemories } from '@/api/modules/memory'
import { listScenes } from '@/api/modules/scene'
import { listAgents } from '@/api/modules/agent'
import { FeedbackState, PageContainer } from '@/components/common'
import { memoryTypeOptions } from '@/constants/memory'
import { useAppStore } from '@/store'
import { showErrorMessage } from '@/utils/feedback'

const { Text } = Typography

/** 检索默认只查有效记忆；「已删除」供排查用。 */
const statusOptions = [
  { label: '有效', value: 'active' },
  { label: '已删除', value: 'deleted' },
]

interface RetrievalFormValues {
  query: string
  memoryTypes?: string[]
  status?: string[]
  sceneId?: string
  agentId?: string
  topK: number
}

function formatTime(value?: string) {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}

function scorePercent(value?: number) {
  return typeof value === 'number' ? Math.round(value * 100) : null
}

export default function RetrievalPage() {
  const config = useAppStore((state) => state.config)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<MemorySearchResult | null>(null)
  const [sceneOptions, setSceneOptions] = useState<Array<{ value: string; label: string }>>([])
  const [agentOptions, setAgentOptions] = useState<Array<{ value: string; label: string }>>([])

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

  const handleSearch = async (values: RetrievalFormValues) => {
    setLoading(true)
    try {
      const query = values.query?.trim() || ''
      const backendResult = await searchMemories({
        query,
        user_id: config.userId,
        scene_id: values.sceneId?.trim() || undefined,
        agent_id: values.agentId?.trim() || undefined,
        memory_types: values.memoryTypes?.length ? values.memoryTypes : undefined,
        status: values.status?.length ? values.status : undefined,
        top_k: values.topK,
        rerank: true,
        max_content_length: 500,
      })
      setResult(backendResult)
    } catch (error) {
      setResult(null)
      showErrorMessage(error, '记忆检索失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <PageContainer
      title="多信号融合记忆检索"
      description="hybrid 检索（语义向量 + 关键词 RRF 融合），可结合记忆类型、状态与场景过滤。"
      extra={<Tag color="blue">用户：{config.userId}</Tag>}
    >
      <Card className="console-card" variant="borderless">
        <Form<RetrievalFormValues>
          layout="vertical"
          initialValues={{ status: ['active'], topK: 10 }}
          onFinish={(values) => void handleSearch(values)}
        >
          <Row gutter={12} align="bottom">
            <Col xs={24} lg={10}>
              <Form.Item name="query" label="检索内容" rules={[{ required: true, whitespace: true, message: '请输入检索内容' }]}>
                <Input prefix={<SearchOutlined />} placeholder="例如：冷链配送、订单DH001、用户偏好" />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12} lg={5}>
              <Form.Item name="memoryTypes" label="记忆类型">
                <Select
                  mode="multiple"
                  allowClear
                  placeholder="全部类型"
                  options={memoryTypeOptions}
                />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12} lg={3}>
              <Form.Item name="status" label="记忆状态">
                <Select
                  mode="multiple"
                  allowClear
                  placeholder="默认有效"
                  options={statusOptions}
                />
              </Form.Item>
            </Col>
            <Col xs={12} lg={3}>
              <Form.Item name="sceneId" label="场景（可选）">
                <Select
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  placeholder={sceneOptions.length ? '选择场景' : '暂无可选场景'}
                  options={sceneOptions}
                />
              </Form.Item>
            </Col>
            <Col xs={12} lg={3}>
              <Form.Item name="agentId" label="智能体（可选）">
                <Select
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  placeholder={agentOptions.length ? '选择智能体' : '暂无可选智能体'}
                  options={agentOptions}
                />
              </Form.Item>
            </Col>
            <Col xs={12} lg={3}>
              <Form.Item name="topK" label="返回数量">
                <InputNumber min={1} max={50} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Button type="primary" htmlType="submit" icon={<SearchOutlined />} loading={loading} block>
            检索记忆
          </Button>
        </Form>
      </Card>

      {loading ? <FeedbackState status="loading" description="正在融合语义与关键词信号检索…" /> : null}

      {!loading && result ? (
        <Space orientation="vertical" size={14} style={{ display: 'flex' }}>
          <Row gutter={[12, 12]}>
            <Col xs={12} md={6}><Card className="console-card result-stat"><Text type="secondary">返回结果</Text><strong>{result.results.length}</strong></Card></Col>
            <Col xs={12} md={6}><Card className="console-card result-stat"><Text type="secondary">候选记忆</Text><strong>{result.total_candidates}</strong></Card></Col>
            <Col xs={12} md={6}><Card className="console-card result-stat"><Text type="secondary">检索耗时</Text><strong>{result.elapsed_ms} ms</strong></Card></Col>
            <Col xs={12} md={6}><Card className="console-card result-stat"><Text type="secondary">检索方式</Text><strong>hybrid 融合</strong></Card></Col>
          </Row>

          <Card className="console-card" title={`检索结果（${result.results.length}）`} variant="borderless">
            {result.results.length ? (
              <Space orientation="vertical" size={10} style={{ display: 'flex' }}>
                {result.results.map((item, index) => {
                  const percent = scorePercent(item.relevance_score)
                  return (
                    <div className="ret-result-item" key={item.memory_id}>
                      <Flex gap={12} align="flex-start">
                        <div className="ret-rank-badge">{index + 1}</div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <Text ellipsis={{ tooltip: item.content }}>{item.content}</Text>
                          <Flex gap={6} wrap style={{ marginTop: 4 }}>
                            <Tag color="blue">{item.memory_type || 'unknown'}</Tag>
                            {item.memory_scope ? <Tag>{item.memory_scope}</Tag> : null}
                            {item.scene_id ? <Tag color="cyan">{item.scene_id}</Tag> : null}
                            <Text type="secondary" style={{ fontSize: 12 }}>{formatTime(item.created_at)}</Text>
                          </Flex>
                        </div>
                        {percent !== null ? (
                          <Flex vertical align="center" gap={4} style={{ width: 110 }}>
                            <Progress percent={percent} size="small" strokeColor="#1677ff" style={{ width: '100%', margin: 0 }} />
                            <Text type="secondary" style={{ fontSize: 11 }}>相关度 {percent}%</Text>
                          </Flex>
                        ) : null}
                      </Flex>
                    </div>
                  )
                })}
              </Space>
            ) : <Empty description="没有匹配的记忆，可尝试放宽类型或状态过滤。" />}
          </Card>
        </Space>
      ) : null}
    </PageContainer>
  )
}
