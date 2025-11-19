import { Greeting } from '@renderer/components/greeting'
import { useChats } from '@renderer/hooks/use-chat'
import { useTitlebar } from '@renderer/hooks/use-titlebar'

export function HomePage() {
  useTitlebar({ title: 'Kel' })
  const { chats } = useChats();
  console.log(chats)

  return (
    <div className="flex flex-col h-[100vh]">
      <div className="h-8"></div>
      <div className="px-4">
        <Greeting />
      </div>
      <div className='h-8'></div>
      <div className='p-4 text-sm text-f-300'>Recents</div>
      <pre className='text-sm p-4'>
        {JSON.stringify(chats, null, 2)}
      </pre>
    </div>
  )
}