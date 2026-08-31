import { request } from '@/api/request'

export interface AuthLoginPayload {
  username: string
  password: string
}

export interface AuthLoginResult {
  user: {
    user_id: string
    username: string
    name?: string
  }
  token: string
  user_id: string
}

/** 登录即注册：username 不存在时后端自动创建账号（用传入密码）；已存在则校验密码。 */
export function loginApi(payload: AuthLoginPayload) {
  return request<AuthLoginResult>({
    url: '/api/v1/auth/login',
    method: 'POST',
    data: payload,
  })
}
