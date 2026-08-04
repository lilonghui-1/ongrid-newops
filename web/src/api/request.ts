import axios, {
  type AxiosInstance,
  type AxiosError,
  type InternalAxiosRequestConfig,
  type AxiosResponse,
} from 'axios'
import { ElMessage } from 'element-plus'

const TOKEN_KEY = 'token'

// Axios 实例：baseURL 使用 /api 前缀，开发环境由 Vite 代理转发到后端（见 vite.config.ts）
const service: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 请求拦截器：携带 Authorization Token
service.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error),
)

// 响应拦截器：统一错误处理，401 跳转登录
service.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error: AxiosError<{ message?: string; detail?: string }>) => {
    const status = error.response?.status
    const url = error.config?.url || ''
    // 登录接口本身的 401 表示凭证错误，不应触发「会话失效」跳转
    const isLoginRequest = url.includes('/auth/login')
    if (status === 401 && !isLoginRequest) {
      ElMessage.error('登录状态已失效，请重新登录')
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem('userInfo')
      // 跳转登录页（整页刷新以重置应用状态）
      window.location.href = `/login?redirect=${encodeURIComponent(window.location.pathname)}`
    } else {
      const data = error.response?.data as
        | { message?: string; detail?: string }
        | undefined
      const msg =
        data?.message || data?.detail || error.message || '请求失败，请稍后重试'
      ElMessage.error(msg)
    }
    return Promise.reject(error)
  },
)

export default service
