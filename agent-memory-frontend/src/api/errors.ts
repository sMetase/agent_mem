interface ApiErrorOptions {
  code?: number
  errorCode?: string
  traceId?: string
}

export class ApiError extends Error {
  readonly code?: number
  readonly errorCode?: string
  readonly traceId?: string

  constructor(message: string, options: ApiErrorOptions = {}) {
    super(message)
    this.name = 'ApiError'
    this.code = options.code
    this.errorCode = options.errorCode
    this.traceId = options.traceId
  }
}
