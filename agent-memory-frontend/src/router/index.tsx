import { RouterProvider } from 'react-router-dom'
import { appRouter } from '@/router/routes'

export function AppRouterProvider() {
  return <RouterProvider router={appRouter} />
}
