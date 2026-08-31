import {
  DownOutlined,
  FilterOutlined,
  ReloadOutlined,
  SearchOutlined,
  UpOutlined,
} from '@ant-design/icons'
import {
  Button,
  Card,
  Col,
  Collapse,
  DatePicker,
  Flex,
  Input,
  Row,
  Select,
  Space,
  Tag,
} from 'antd'
import { useEffect, useState } from 'react'
import type { Dayjs } from 'dayjs'
import { listAgents } from '@/api/modules/agent'
import { listScenes } from '@/api/modules/scene'
import { listSessions } from '@/api/modules/session'
import { listTasks } from '@/api/modules/task'
import { memoryTypeOptions } from '@/constants/memory'
import type { MemoryScope } from '@/pages/Memory/types'

const { RangePicker } = DatePicker

export interface MemoryAdvancedFilters {
  tags?: string
  sceneId?: string
  sessionId?: string
  taskId?: string
  agentId?: string
  memoryType?: string
  timeRange?: [Dayjs, Dayjs] | null
}

interface OptionItem {
  value: string
  label: string
}

interface MemorySearchBarProps {
  scope: MemoryScope
  keyword: string
  loading?: boolean
  advanced: MemoryAdvancedFilters
  onKeywordChange: (value: string) => void
  onAdvancedChange: (filters: MemoryAdvancedFilters) => void
  onSearch: () => void
  onReset: () => void
}

export function MemorySearchBar({
  scope,
  keyword,
  loading,
  advanced,
  onKeywordChange,
  onAdvancedChange,
  onSearch,
  onReset,
}: MemorySearchBarProps) {
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [sceneOptions, setSceneOptions] = useState<OptionItem[]>([])
  const [agentOptions, setAgentOptions] = useState<OptionItem[]>([])
  const [sessionOptions, setSessionOptions] = useState<OptionItem[]>([])
  const [taskOptions, setTaskOptions] = useState<OptionItem[]>([])

  // 四层入口统一「名称下拉」，用户不接触原始 id（GET /scene、/agent、/session、/task）。
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
    listSessions({ status: 'active', pageSize: 100 })
      .then((data) => setSessionOptions(data.items.map((session) => ({
        value: session.session_id,
        label: session.title ?? session.session_id,
      }))))
      .catch(() => setSessionOptions([]))
    listTasks({ pageSize: 100 })
      .then((data) => setTaskOptions(data.items.map((task) => ({
        value: task.task_id,
        label: task.title ?? task.task_id,
      }))))
      .catch(() => setTaskOptions([]))
  }, [])

  const scopePlaceholder: Record<MemoryScope, string> = {
    all: '按记忆内容、ID 检索',
    user: '按记忆内容、标签检索',
    session: '按记忆内容、会话检索',
    task: '按记忆内容、任务检索',
    agent: '按记忆内容、智能体检索',
  }

  const updateAdvanced = (patch: Partial<MemoryAdvancedFilters>) => {
    onAdvancedChange({ ...advanced, ...patch })
  }

  const filterApplied = Boolean(
    advanced.tags
    || advanced.sceneId
    || advanced.sessionId
    || advanced.taskId
    || advanced.agentId
    || advanced.memoryType
    || advanced.timeRange,
  )

  return (
    <Card className="console-card memory-search-card" variant="borderless">
      <Flex wrap gap={12} align="center">
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder={scopePlaceholder[scope]}
          value={keyword}
          style={{ flex: '1 1 260px', minWidth: 0 }}
          onChange={(event) => onKeywordChange(event.target.value)}
          onPressEnter={onSearch}
        />
        <Space>
          <Button icon={<FilterOutlined />} onClick={() => setAdvancedOpen((open) => !open)}>
            高级查询
            {advancedOpen ? <UpOutlined /> : <DownOutlined />}
          </Button>
          <Button type="primary" loading={loading} onClick={onSearch}>查询</Button>
          <Button icon={<ReloadOutlined />} onClick={onReset}>重置</Button>
        </Space>
      </Flex>

      {advancedOpen ? (
        <Collapse
          className="memory-advanced-collapse"
          activeKey="advanced"
          items={[{
            key: 'advanced',
            label: (
              <Space size={8}>
                筛选条件
                {filterApplied ? <Tag color="blue">已应用</Tag> : null}
              </Space>
            ),
            children: (
              <Row gutter={[12, 12]}>
                <Col xs={24} sm={12} lg={8}>
                  <div className="memory-advanced-label">记忆类型</div>
                  <Select
                    allowClear
                    placeholder="全部类型"
                    value={advanced.memoryType}
                    onChange={(value) => updateAdvanced({ memoryType: value })}
                    options={memoryTypeOptions}
                    style={{ width: '100%' }}
                  />
                </Col>
                <Col xs={24} sm={12} lg={8}>
                  <div className="memory-advanced-label">场景</div>
                  <Select
                    allowClear
                    showSearch
                    optionFilterProp="label"
                    placeholder={sceneOptions.length ? '选择场景' : '暂无可选场景'}
                    value={advanced.sceneId}
                    onChange={(value) => updateAdvanced({ sceneId: value })}
                    options={sceneOptions}
                    style={{ width: '100%' }}
                  />
                </Col>
                <Col xs={24} sm={12} lg={8}>
                  <div className="memory-advanced-label">智能体</div>
                  <Select
                    allowClear
                    showSearch
                    optionFilterProp="label"
                    placeholder={agentOptions.length ? '选择智能体' : '暂无可选智能体'}
                    value={advanced.agentId}
                    onChange={(value) => updateAdvanced({ agentId: value })}
                    options={agentOptions}
                    style={{ width: '100%' }}
                  />
                </Col>
                {scope === 'session' || scope === 'all' ? (
                  <Col xs={24} sm={12} lg={8}>
                    <div className="memory-advanced-label">会话</div>
                    <Select
                      allowClear
                      showSearch
                      optionFilterProp="label"
                      placeholder={sessionOptions.length ? '选择会话' : '暂无可选会话'}
                      value={advanced.sessionId}
                      onChange={(value) => updateAdvanced({ sessionId: value })}
                      options={sessionOptions}
                      style={{ width: '100%' }}
                    />
                  </Col>
                ) : null}
                {scope === 'task' || scope === 'all' ? (
                  <Col xs={24} sm={12} lg={8}>
                    <div className="memory-advanced-label">任务</div>
                    <Select
                      allowClear
                      showSearch
                      optionFilterProp="label"
                      placeholder={taskOptions.length ? '选择任务' : '暂无可选任务'}
                      value={advanced.taskId}
                      onChange={(value) => updateAdvanced({ taskId: value })}
                      options={taskOptions}
                      style={{ width: '100%' }}
                    />
                  </Col>
                ) : null}
                <Col xs={24} sm={12} lg={8}>
                  <div className="memory-advanced-label">记忆标签</div>
                  <Input
                    allowClear
                    placeholder="多个标签用逗号分隔"
                    value={advanced.tags}
                    onChange={(event) => updateAdvanced({ tags: event.target.value })}
                  />
                </Col>
                <Col xs={24} lg={16}>
                  <div className="memory-advanced-label">创建时间范围</div>
                  <RangePicker
                    style={{ width: '100%' }}
                    value={advanced.timeRange}
                    onChange={(range) => updateAdvanced({ timeRange: range as [Dayjs, Dayjs] | null })}
                  />
                </Col>
              </Row>
            ),
          }]}
        />
      ) : null}
    </Card>
  )
}
