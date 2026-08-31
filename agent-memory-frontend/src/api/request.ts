import type { AxiosRequestConfig } from 'axios'
import { apiClient } from '@/api/client'
import { unwrapApiResponse } from '@/api/types'

export async function request<T>(config: AxiosRequestConfig) {
  const response = await apiClient.request<unknown>(config)
  return unwrapApiResponse<T>(response.data)
}
