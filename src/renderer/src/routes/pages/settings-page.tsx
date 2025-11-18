import { Link } from 'react-router-dom'
import { useTitlebar } from '@renderer/hooks/use-titlebar'

export function SettingsPage() {
  useTitlebar({ title: 'Settings' })
  return (
    <>
      <div>Hello settings!</div>
      <br />
      <Link to="/">Go home</Link>
    </>
  )
}
