import { DashboardOutlined } from '@ant-design/icons'
import { Menu, Typography } from 'antd'
import type { MenuProps } from 'antd'
import { useLocation, useNavigate } from 'react-router-dom'
import { appRoutes } from '@/constants/routes'
import { menuSectionConfigs } from '@/router/route-config'

interface SidebarMenuProps {
  onNavigate?: () => void
}

export function SidebarMenu({ onNavigate }: SidebarMenuProps) {
  const location = useLocation()
  const navigate = useNavigate()
  const menuEntries = menuSectionConfigs.flatMap((section) => section.items)
  const routeMap = new Map(menuEntries.map((entry) => [entry.key, entry.path]))
  const currentLocation = `${location.pathname}${location.search}`
  const selectedEntry = menuEntries.find((entry) => entry.path === currentLocation)
    ?? menuEntries.find((entry) => entry.path.split('?')[0] === location.pathname)
  const items: MenuProps['items'] = [
    {
      key: appRoutes.overview,
      icon: <DashboardOutlined />,
      label: '系统总览',
    },
    ...menuSectionConfigs.map((section) => ({
      key: section.key,
      icon: section.icon,
      label: section.label,
      children: section.items.map((entry) => ({
        key: entry.key,
        icon: entry.icon,
        label: entry.label,
      })),
    })),
  ]

  return (
    <div className="app-sidebar">
      <div className="app-brand">
        <div className="app-brand-mark">AM</div>
        <div>
          <Typography.Text className="app-brand-title">智能体记忆系统</Typography.Text>
          <Typography.Text className="app-brand-subtitle">AGENT MEMORY CONSOLE</Typography.Text>
        </div>
      </div>
      <Menu
        className="app-sidebar-menu"
        mode="inline"
        selectedKeys={[location.pathname === appRoutes.overview ? appRoutes.overview : selectedEntry?.key ?? location.pathname]}
        defaultOpenKeys={menuSectionConfigs.slice(0, 5).map((section) => section.key)}
        items={items}
        onClick={({ key }) => {
          navigate(key === appRoutes.overview ? appRoutes.overview : routeMap.get(key) ?? appRoutes.overview)
          onNavigate?.()
        }}
      />
    </div>
  )
}
