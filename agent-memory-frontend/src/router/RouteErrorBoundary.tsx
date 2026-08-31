import { Button } from 'antd'
import {
  isRouteErrorResponse,
  useNavigate,
  useRouteError,
} from 'react-router-dom'
import { AppErrorFallback } from '@/components/common'
import { appRoutes } from '@/constants/routes'
import { getErrorMessage } from '@/utils/error'

export function RouteErrorBoundary() {
  const error = useRouteError()
  const navigate = useNavigate()

  let title = '页面加载失败'
  let subtitle = getErrorMessage(error, '请稍后重试。')

  if (isRouteErrorResponse(error)) {
    title = error.status === 404 ? '页面不存在' : `请求失败（${error.status}）`
    subtitle =
      typeof error.data === 'string'
        ? error.data
        : error.statusText || subtitle
  }

  return (
    <AppErrorFallback
      title={title}
      subtitle={subtitle}
      extra={
        <Button type="primary" onClick={() => navigate(appRoutes.overview)}>
          返回首页
        </Button>
      }
    />
  )
}
