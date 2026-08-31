import { Button } from 'antd'
import { createBrowserRouter, Link, Navigate } from 'react-router-dom'
import { AppErrorFallback } from '@/components/common'
import { appRoutes } from '@/constants/routes'
import { AppLayout } from '@/layouts/AppLayout'
import { RequireAuth } from '@/router/RequireAuth'
import { RouteErrorBoundary } from '@/router/RouteErrorBoundary'
import { LegacyCapabilityRedirect } from '@/router/LegacyCapabilityRedirect'
import { appRouteConfigs } from '@/router/route-config'

const childRoutes = appRouteConfigs.map((route) => {
  if (route.path === appRoutes.overview) {
    return {
      index: true,
      element: route.element,
    }
  }

  return {
    path: route.path.replace(/^\//, ''),
    element: route.element,
  }
})

export const appRouter = createBrowserRouter([
  {
    path: '/login',
    lazy: async () => ({ Component: (await import('@/pages/Login')).default }),
    errorElement: <RouteErrorBoundary />,
  },
  {
    path: '/forgot-password',
    lazy: async () => ({ Component: (await import('@/pages/ForgotPassword')).default }),
    errorElement: <RouteErrorBoundary />,
  },
  {
    path: appRoutes.overview,
    element: <RequireAuth><AppLayout /></RequireAuth>,
    errorElement: <RouteErrorBoundary />,
    children: [
      ...childRoutes,
      {
        path: 'profile',
        lazy: async () => ({ Component: (await import('@/pages/Profile')).default }),
      },
      {
        path: 'capabilities/:capabilityId',
        element: <LegacyCapabilityRedirect />,
      },
      {
        path: 'home',
        element: <Navigate replace to={appRoutes.overview} />,
      },
      {
        path: '*',
        element: (
          <AppErrorFallback
            title="页面不存在"
            subtitle="请检查访问路径是否正确。"
            extra={
              <Button type="primary">
                <Link to={appRoutes.overview}>返回首页</Link>
              </Button>
            }
          />
        ),
      },
    ],
  },
])
