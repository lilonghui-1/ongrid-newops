import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import request from '@/api/request'

const TOKEN_KEY = 'token'
const REFRESH_TOKEN_KEY = 'refresh_token'
const USER_INFO_KEY = 'userInfo'

/** 用户信息 */
export interface UserInfo {
  id?: number | string
  username: string
  display_name?: string
  role?: string
  [key: string]: unknown
}

/** 登录凭证 */
export interface LoginCredentials {
  username: string
  password: string
}

/** 登录响应（后端真实契约） */
export interface LoginResult {
  access_token: string
  refresh_token?: string
  username: string
  role?: string
  [key: string]: unknown
}

export const useAuthStore = defineStore('auth', () => {
  // 初始化时从 localStorage 恢复登录态
  const token = ref<string>(localStorage.getItem(TOKEN_KEY) || '')
  const refreshToken = ref<string>(localStorage.getItem(REFRESH_TOKEN_KEY) || '')

  const userInfo = ref<UserInfo | null>(
    (() => {
      const raw = localStorage.getItem(USER_INFO_KEY)
      if (!raw) return null
      try {
        return JSON.parse(raw) as UserInfo
      } catch {
        return null
      }
    })(),
  )

  const isLoggedIn = computed(() => !!token.value)

  /** 登录：调用 POST /auth/login，按 {access_token, refresh_token, username, role} 解析 */
  async function login(credentials: LoginCredentials): Promise<LoginResult> {
    const res = await request.post<LoginResult>('/auth/login', credentials)
    const data = res.data
    token.value = data.access_token
    refreshToken.value = data.refresh_token || ''
    userInfo.value = {
      username: data.username,
      role: data.role,
      display_name: data.username,
    }
    localStorage.setItem(TOKEN_KEY, data.access_token)
    if (data.refresh_token) {
      localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token)
    }
    localStorage.setItem(USER_INFO_KEY, JSON.stringify(userInfo.value))
    return data
  }

  /** 登出 */
  function logout(): void {
    token.value = ''
    refreshToken.value = ''
    userInfo.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
    localStorage.removeItem(USER_INFO_KEY)
    window.location.href = '/login'
  }

  return {
    token,
    refreshToken,
    userInfo,
    isLoggedIn,
    login,
    logout,
  }
})
