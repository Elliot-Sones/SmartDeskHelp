import { useTitlebar } from '@renderer/hooks/use-titlebar'
import { Input } from '@renderer/components/ui/input'

export function SettingsPage() {
  useTitlebar({ title: 'Kel — Settings' })
  return (
    <>
      <div className='h-20'></div>
      <Input placeholder="Type here..." type="password" />
    </>
  )
}
