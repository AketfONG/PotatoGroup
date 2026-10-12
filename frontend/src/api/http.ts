/**
 * REST 客户端:统一包络解包、token 注入、401 跳转登录。
 */

import axios, { type AxiosError } from 'axios'

import type { ApiResponse } from './types'

const TOKEN_KEY = 'potato_token'

export class ApiError extends Error {
  code: number
  constructor(code: number, message: string) {
    super(message)
    this.code = code
  }
}

export const http = axios.create({
  baseURL: '/api/v1',
  timeout: 15000,
})

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null): void {
  if (token === null) localStorage.removeItem(TOKEN_KEY)
  else localStorage.setItem(TOKEN_KEY, token)
}

// 请求:注入 Bearer token
http.interceptors.request.use((config) => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 响应:解统一包络 {code, message, data}
http.interceptors.response.use(
  (response) => {
    const body = response.data as ApiResponse
    if (body.code !== 0) {
      throw new ApiError(body.code, body.message)
    }
    return response
  },
  (error: AxiosError<ApiResponse>) => {
    const body = error.response?.data
    if (body && typeof body.code === 'number') {
      if (body.code === 1002) {
        // 未登录/登录过期:清理并跳转登录页
        setToken(null)
        if (window.location.pathname !== '/login') window.location.href = '/login'
      }
      return Promise.reject(new ApiError(body.code, body.message))
    }
    return Promise.reject(new ApiError(-1, '网络异常,请稍后重试'))
  },
)

/** 取响应包络中的 data(泛型直达) */
export async function unwrap<T>(promise: Promise<{ data: ApiResponse<T> }>): Promise<T> {
  const res = await promise
  return res.data.data as T
}