import { Alert, Button, Card, Form, Input, Radio, Select, Space, TimePicker } from 'antd'
import type { Dayjs } from 'dayjs'
import dayjs from 'dayjs'
import { useCallback, useEffect, useState } from 'react'
import {
  getExtractionSchedule,
  getLlmConfig,
  updateExtractionSchedule,
  updateLlmConfig,
} from '@/api/modules/config'
import { ConfigForm } from '@/components/business/ConfigForm'
import { PageContainer } from '@/components/common'
import { useAppStore } from '@/store'
import { normalizeAppConfig } from '@/utils/config'
import { showErrorMessage, showSuccessMessage } from '@/utils/feedback'

interface LlmFormValues {
  llm_model?: string
  llm_api_key?: string
}

type ExtractionMode = 'continuous' | 'scheduled'

interface ExtractionScheduleFormValues {
  mode: ExtractionMode
  window?: [Dayjs, Dayjs]
  timezone: string
}

const TIMEZONE_OPTIONS = [
  { value: 'Asia/Shanghai', label: '中国标准时间（Asia/Shanghai）' },
  { value: 'Asia/Tokyo', label: '日本标准时间（Asia/Tokyo）' },
  { value: 'UTC', label: '协调世界时（UTC）' },
  { value: 'America/Los_Angeles', label: '太平洋时间（America/Los_Angeles）' },
]

function parseScheduleTime(value: string) {
  return dayjs(`2000-01-01T${value}`)
}

export default function SettingsPage() {
  const appConfig = useAppStore((state) => state.config)
  const setConfig = useAppStore((state) => state.setConfig)
  const [llmForm] = Form.useForm<LlmFormValues>()
  const [scheduleForm] = Form.useForm<ExtractionScheduleFormValues>()
  const [savingLlm, setSavingLlm] = useState(false)
  const [savingSchedule, setSavingSchedule] = useState(false)
  const [hasApiKey, setHasApiKey] = useState(false)

  const loadLlmConfig = useCallback(async () => {
    try {
      const cfg = await getLlmConfig()
      llmForm.setFieldsValue({ llm_model: cfg.llm_model ?? '', llm_api_key: '' })
      setHasApiKey(Boolean(cfg.has_api_key))
    } catch {
      // 读取失败不阻塞，留空即可
    }
  }, [llmForm])

  useEffect(() => {
    void loadLlmConfig()
  }, [loadLlmConfig])

  const loadExtractionSchedule = useCallback(async () => {
    try {
      const schedule = await getExtractionSchedule()
      scheduleForm.setFieldsValue({
        mode: schedule.extraction_schedule_enabled ? 'scheduled' : 'continuous',
        window: [
          parseScheduleTime(schedule.extraction_window_start),
          parseScheduleTime(schedule.extraction_window_end),
        ],
        timezone: schedule.extraction_timezone,
      })
    } catch {
      scheduleForm.setFieldsValue({
        mode: 'continuous',
        window: [parseScheduleTime('23:00'), parseScheduleTime('06:00')],
        timezone: 'Asia/Shanghai',
      })
    }
  }, [scheduleForm])

  useEffect(() => {
    void loadExtractionSchedule()
  }, [loadExtractionSchedule])

  const handleSaveLlm = async (values: LlmFormValues) => {
    setSavingLlm(true)
    try {
      await updateLlmConfig({
        llm_model: values.llm_model?.trim() || undefined,
        llm_api_key: values.llm_api_key?.trim() || undefined,
      })
      showSuccessMessage('全局默认 LLM 配置已保存。')
      void loadLlmConfig()
    } catch (error) {
      showErrorMessage(error, '保存全局 LLM 配置失败')
    } finally {
      setSavingLlm(false)
    }
  }

  const handleSaveSchedule = async (values: ExtractionScheduleFormValues) => {
    setSavingSchedule(true)
    try {
      const [start, end] = values.window ?? []
      await updateExtractionSchedule({
        extraction_schedule_enabled: values.mode === 'scheduled',
        extraction_window_start: start?.format('HH:mm'),
        extraction_window_end: end?.format('HH:mm'),
        extraction_timezone: values.timezone,
      })
      showSuccessMessage(
        values.mode === 'scheduled' ? '异步消费时间窗口已保存。' : '已设置为持续异步消费。',
      )
      void loadExtractionSchedule()
    } catch (error) {
      showErrorMessage(error, '保存异步消费时间失败')
    } finally {
      setSavingSchedule(false)
    }
  }

  return (
    <PageContainer
      title="基础连接设置"
      description="配置当前浏览器访问的后端服务地址与大模型服务。"
    >
      <Space orientation="vertical" size={14} style={{ display: 'flex' }}>
        <Alert
          type="info"
          showIcon
          title="连接地址只保存在当前浏览器"
          description="修改后会影响健康检查、记忆写入、检索和上下文返回等全部接口。用户身份（User ID）已由登录自动派生，无需手动配置。"
        />
        <ConfigForm
          initialValues={appConfig}
          fields={['baseUrl']}
          title="后端服务连接"
          onSubmit={(values) => {
            setConfig(normalizeAppConfig({ ...appConfig, ...values }))
            showSuccessMessage('基础设置已保存到本地。')
          }}
        />

        <Card variant="borderless" title="全局默认 LLM 配置">
          <Alert
            type="info"
            showIcon
            title="智能体未单独配置时生效"
            description="每个智能体可在「智能体注册接入」单独配置自己的模型和 Key；未配置的智能体将回退到这里设置的全局默认值，再回退到后端环境变量。"
            style={{ marginBottom: 16 }}
          />
          <Form<LlmFormValues> form={llmForm} layout="vertical" onFinish={(values) => void handleSaveLlm(values)}>
            <Form.Item name="llm_model" label="LLM 模型">
              <Input placeholder="deepseek-chat（留空用后端默认）" />
            </Form.Item>
            <Form.Item name="llm_api_key" label="LLM API Key">
              <Input.Password
                placeholder={hasApiKey ? '已配置 Key（留空表示不修改，不会明文回显）' : '留空使用后端默认'}
              />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={savingLlm}>保存全局默认</Button>
          </Form>
        </Card>

        <Card variant="borderless" title="异步记忆消费时间">
          <Alert
            type="info"
            showIcon
            title="Kafka 写入持续进行，时间窗口只控制后续记忆抽取"
            description="持续异步会立即处理待抽取记录；指定时间后，记录会先进入待处理队列，在设定窗口内批量抽取。"
            style={{ marginBottom: 16 }}
          />
          <Form<ExtractionScheduleFormValues>
            form={scheduleForm}
            layout="vertical"
            initialValues={{ mode: 'continuous', timezone: 'Asia/Shanghai' }}
            onFinish={(values) => void handleSaveSchedule(values)}
          >
            <Form.Item name="mode" label="消费模式">
              <Radio.Group optionType="button" buttonStyle="solid">
                <Radio.Button value="continuous">持续异步</Radio.Button>
                <Radio.Button value="scheduled">指定时间</Radio.Button>
              </Radio.Group>
            </Form.Item>
            <Form.Item noStyle shouldUpdate={(prev, current) => prev.mode !== current.mode}>
              {({ getFieldValue }) => getFieldValue('mode') === 'scheduled' ? (
                <>
                  <Form.Item
                    name="window"
                    label="抽取时间窗口"
                    rules={[{ required: true, message: '请选择开始和结束时间' }]}
                  >
                    <TimePicker.RangePicker format="HH:mm" minuteStep={5} allowClear={false} />
                  </Form.Item>
                  <Form.Item name="timezone" label="时区" rules={[{ required: true, message: '请选择时区' }]}>
                    <Select options={TIMEZONE_OPTIONS} />
                  </Form.Item>
                </>
              ) : null}
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={savingSchedule}>保存消费设置</Button>
          </Form>
        </Card>
      </Space>
    </PageContainer>
  )
}
