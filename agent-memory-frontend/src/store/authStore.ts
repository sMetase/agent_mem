import { create } from 'zustand'
import { storageKeys } from '@/constants/storage'
import { loginApi } from '@/api/modules/auth'
import { getErrorMessage } from '@/utils/error'

export type UserRole = 'admin' | 'operator' | 'auditor'

export interface AuthUser {
  id: string
  username: string
  displayName: string
  role: UserRole
  department: string
  email?: string
  phone?: string
}

export interface LoginResult {
  success: boolean
  message?: string
  user?: AuthUser
  token?: string
  user_id?: string
}

interface AuthStoreState {
  user: AuthUser | null
  token: string | null
  isAuthenticated: boolean
  login: (username: string, password: string) => Promise<LoginResult>
  logout: () => void
  restore: () => void
}

function loadStoredAuth() {
  try {
    const raw = localStorage.getItem(storageKeys.auth)
    if (!raw) return { user: null as AuthUser | null, token: null as string | null }
    const parsed = JSON.parse(raw) as { user: AuthUser | null; token: string | null }
    return { user: parsed.user, token: parsed.token }
  } catch {
    return { user: null, token: null }
  }
}

export const useAuthStore = create<AuthStoreState>((set) => {
  const stored = loadStoredAuth()
  return {
    user: stored.user,
    token: stored.token,
    isAuthenticated: Boolean(stored.user && stored.token),
    // 真实登录：POST /api/v1/auth/login（登录即注册），返回 user + token + user_id。
    login: async (username, password) => {
      try {
        const result = await loginApi({ username: username.trim(), password })
        const user: AuthUser = {
          id: result.user_id,
          username: result.user.username,
          displayName: result.user.name || result.user.username,
          // 后端暂不返回角色/部门，先按管理员预留，后续接口就绪再对齐。
          role: 'admin',
          department: '',
        }
        localStorage.setItem(storageKeys.auth, JSON.stringify({ user, token: result.token }))
        set({ user, token: result.token, isAuthenticated: true })
        return { success: true, user, token: result.token, user_id: result.user_id }
      } catch (error) {
        return { success: false, message: getErrorMessage(error, '登录失败') }
      }
    },
    logout: () => {
      localStorage.removeItem(storageKeys.auth)
      set({ user: null, token: null, isAuthenticated: false })
    },
    restore: () => {
      const restored = loadStoredAuth()
      set({
        user: restored.user,
        token: restored.token,
        isAuthenticated: Boolean(restored.user && restored.token),
      })
    },
  }
})
