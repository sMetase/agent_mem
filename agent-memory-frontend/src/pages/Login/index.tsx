import { GithubOutlined, LockOutlined, UserOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Divider, Flex, Form, Input, Typography } from 'antd'
import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { appRoutes } from '@/constants/routes'
import { useAppStore, useAuthStore } from '@/store'
import { normalizeAppConfig } from '@/utils/config'
import { showSuccessMessage } from '@/utils/feedback'

const { Text, Title } = Typography

interface LoginValues {
  username: string
  password: string
}

export default function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const login = useAuthStore((state) => state.login)
  const config = useAppStore((state) => state.config)
  const setConfig = useAppStore((state) => state.setConfig)
  const [loading, setLoading] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const from = (location.state as { from?: string } | null)?.from || appRoutes.overview

  const handleLogin = async (values: LoginValues) => {
    setLoading(true)
    setErrorMsg(null)
    try {
      const result = await login(values.username, values.password)
      if (result.success && result.user_id) {
        // 登录返回的 user_id 注入应用配置，后续所有请求用它作为用户标识。
        setConfig(normalizeAppConfig({ ...config, userId: result.user_id }))
        showSuccessMessage(`欢迎回来，${result.user?.displayName ?? result.user?.username}`)
        navigate(from, { replace: true })
      } else {
        setErrorMsg(result.message ?? '登录失败')
      }
    } catch {
      setErrorMsg('登录失败，请检查后端连接后重试')
    } finally {
      setLoading(false)
    }
  }

  const handleGitHubLogin = () => {
    // GitHub OAuth2 需应用注册 client-id/secret；当前为占位入口。
    setErrorMsg('GitHub 登录正在接入中，请使用账号密码登录。')
  }

  return (
    <div className="auth-page">
      <div className="auth-brand">
        <div className="auth-brand-inner">
          <div className="auth-brand-logo">AM</div>
          <Title className="auth-brand-title">智能体记忆系统</Title>
          <Text className="auth-brand-subtitle">AGENT MEMORY CONSOLE</Text>
          <Text className="auth-brand-desc">
            面向大模型智能体的记忆管理中台：接入智能体、沉淀记忆、融合检索、上下文返回。
          </Text>
        </div>
      </div>

      <div className="auth-form-wrap">
        <Card className="auth-card">
          <div className="auth-card-body">
            <Title level={4} style={{ margin: '0 0 4px' }}>用户登录</Title>
            <Text type="secondary">统一身份认证（登录即注册），登录后进入记忆控制台</Text>

            {errorMsg ? (
              <Alert message={errorMsg} type="error" showIcon closable onClose={() => setErrorMsg(null)} style={{ marginTop: 16 }} />
            ) : null}

            <Form<LoginValues>
              layout="vertical"
              autoComplete="off"
              onFinish={(values) => void handleLogin(values)}
              style={{ marginTop: 20 }}
            >
              <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
                <Input prefix={<UserOutlined style={{ color: '#999' }} />} placeholder="admin" size="large" />
              </Form.Item>
              <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
                <Input.Password prefix={<LockOutlined style={{ color: '#999' }} />} placeholder="admin123" size="large" />
              </Form.Item>
              <Flex justify="space-between" align="center" style={{ marginBottom: 16 }}>
                <Link to="/forgot-password" className="auth-link">忘记密码？</Link>
                <Text type="secondary" style={{ fontSize: 12 }}>测试账号 admin / admin123</Text>
              </Flex>
              <Button type="primary" htmlType="submit" loading={loading} block size="large">登 录</Button>
              <Divider plain style={{ color: '#8b99aa', fontSize: 12 }}>或</Divider>
              <Button block icon={<GithubOutlined />} onClick={handleGitHubLogin} size="large">GitHub 登录</Button>
            </Form>
          </div>
        </Card>
      </div>
    </div>
  )
}
