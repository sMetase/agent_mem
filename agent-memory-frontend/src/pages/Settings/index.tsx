import { Alert, Button, Card, Form, Input, Space } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { getLlmConfig, updateLlmConfig } from '@/api/modules/config'
import { ConfigForm } from '@/components/business/ConfigForm'
import { PageContainer } from '@/components/common'
import { useAppStore } from '@/store'
import { normalizeAppConfig } from '@/utils/config'
import { showErrorMessage, showSuccessMessage } from '@/utils/feedback'

interface LlmFormValues {
  llm_model?: string
  llm_api_key?: string
}

export default function SettingsPage() {
  const appConfig = useAppStore((state) => state.config)
  const setConfig = useAppStore((state) => state.setConfig)
  const [llmForm] = Form.useForm<LlmFormValues>()
  const [savingLlm, setSavingLlm] = useState(false)
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
      </Space>
    </PageContainer>
  )
}
