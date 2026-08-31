import { isAxiosError } from 'axios'

function hasMessage(value: unknown): value is { message?: string } {
  return typeof value === 'object' && value !== null && 'message' in value
}

export function getErrorMessage(error: unknown, fallback = '发生未知错误') {
  if (isAxiosError(error)) {
    const responseData = error.response?.data

    if (hasMessage(responseData) && responseData.message) {
      return responseData.message
    }

    if (error.message) {
      return error.message
    }

    return fallback
  }

  if (error instanceof Error) {
    return error.message
  }

  if (typeof error === 'string') {
    return error
  }

  return fallback
}
