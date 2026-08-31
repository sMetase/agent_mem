import { ArrowLeftOutlined, MailOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Form, Input, Steps, Typography } from 'antd'
import { useState } from 'react'
import { Link } from 'react-router-dom'

const { Text, Title } = Typography

interface ForgotPasswordValues {
  email: string
  code: string
  password: string
  confirmPassword: string
}

export default function ForgotPasswordPage() {
  const [step, setStep] = useState(0)
  const [sent, setSent] = useState(false)
  const [done, setDone] = useState(false)
  const [form] = Form.useForm<ForgotPasswordValues>()

  const handleSendCode = async () => {
    await form.validateFields(['email'])
    // 模拟发送验证码；真实发送接口由后端提供后对接。
    setSent(true)
  }

  const handleSubmit = async (_values: ForgotPasswordValues) => {
    setStep(2)
    setDone(true)
  }

  const stepItems = [
    { title: '验证身份' },
    { title: '设置密码' },
    { title: '完成' },
  ]

  return (
    <div className="auth-page">
      <div className="auth-brand">
        <div className="auth-brand-inner">
          <div className="auth-brand-logo">AM</div>
          <Title className="auth-brand-title">智能体记忆系统</Title>
          <Text className="auth-brand-subtitle">AGENT MEMORY CONSOLE</Text>
        </div>
      </div>

      <div className="auth-form-wrap">
        <Card className="auth-card">
          <Link to="/login" className="auth-link" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <ArrowLeftOutlined /> 返回登录
          </Link>
          <Steps size="small" current={step} items={stepItems} style={{ margin: '16px 0 20px' }} />

          {done ? (
            <div style={{ textAlign: 'center', padding: '20px 0' }}>
              <Title level={4}>密码重置成功</Title>
              <Text type="secondary">请使用新密码重新登录。</Text>
              <div style={{ marginTop: 20 }}>
                <Link to="/login"><Button type="primary">去登录</Button></Link>
              </div>
            </div>
          ) : (
            <Form<ForgotPasswordValues> form={form} layout="vertical" onFinish={(values) => void handleSubmit(values)}>
              {step === 0 ? (
                <>
                  <Title level={5} style={{ marginTop: 0 }}>验证身份</Title>
                  <Text type="secondary">输入注册邮箱获取验证码。</Text>
                  <Form.Item name="email" label="邮箱" rules={[{ required: true, type: 'email', message: '请输入有效邮箱' }]} style={{ marginTop: 16 }}>
                    <Input prefix={<MailOutlined style={{ color: '#999' }} />} placeholder="name@example.com" size="large" />
                  </Form.Item>
                  <Form.Item
                    name="code"
                    label="验证码"
                    rules={[{ required: true, message: '请输入验证码' }]}
                    extra={
                      sent ? (
                        <Text type="success">验证码已发送（演示环境请使用任意 6 位数字）</Text>
                      ) : null
                    }
                  >
                    <Input placeholder="6 位验证码" maxLength={6} size="large" />
                  </Form.Item>
                  <Button block onClick={() => void handleSendCode()} style={{ marginBottom: 12 }} disabled={sent}>
                    {sent ? '验证码已发送' : '获取验证码'}
                  </Button>
                  <Button type="primary" htmlType="submit" block size="large">下一步</Button>
                </>
              ) : (
                <>
                  <Title level={5} style={{ marginTop: 0 }}>设置新密码</Title>
                  <Form.Item name="password" label="新密码" rules={[{ required: true, min: 8, message: '密码至少 8 位' }]} style={{ marginTop: 16 }}>
                    <Input.Password placeholder="至少 8 位密码" size="large" />
                  </Form.Item>
                  <Form.Item
                    name="confirmPassword"
                    label="确认新密码"
                    dependencies={['password']}
                    rules={[
                      { required: true, message: '请再次输入密码' },
                      ({ getFieldValue }) => ({
                        validator: (_, value) =>
                          !value || getFieldValue('password') === value
                            ? Promise.resolve()
                            : Promise.reject(new Error('两次输入的密码不一致')),
                      }),
                    ]}
                  >
                    <Input.Password placeholder="再次输入新密码" size="large" />
                  </Form.Item>
                  <Button type="primary" htmlType="submit" block size="large">重置密码</Button>
                </>
              )}
            </Form>
          )}
          {!done && sent ? (
            <Alert type="info" showIcon message="当前为演示环境，验证码发送与重置逻辑将在后端认证能力就绪后对接。" style={{ marginTop: 16 }} />
          ) : null}
        </Card>
      </div>
    </div>
  )
}
