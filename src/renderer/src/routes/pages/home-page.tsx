import { ComposeMessage } from '@renderer/components/compose-message'
import { Greeting } from '@renderer/components/greeting'
import { RecentChats } from '@renderer/components/recent-chats'
import { useTitlebar } from '@renderer/hooks/use-titlebar'

export function HomePage() {
  useTitlebar({ title: 'Minnie' })

  return (
    <div className="flex flex-col h-[100vh] glass-page">
      <div className="h-8"></div>
      <div className="px-4">
        <Greeting />
      </div>
      <div className="h-8"></div>
      <RecentChats />
      <div className="flex-grow"></div>
      <ComposeMessage />
    </div>
  )
}

