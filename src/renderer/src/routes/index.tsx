import { createHashRouter } from 'react-router-dom'
import { RootLayout } from './layouts/RootLayout'
import { HomePage } from './pages/HomePage'
import { SettingsPage } from './pages/SettingsPage'

export const router = createHashRouter([
  {
    path: '/',
    element: <RootLayout />,
    children: [
      {
        index: true,
        element: <HomePage />
      },
      {
        path: '/settings',
        element: <SettingsPage/>
      }
    ]
  }
])
