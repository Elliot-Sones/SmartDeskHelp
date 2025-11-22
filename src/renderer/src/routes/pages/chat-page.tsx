import { useChat } from '@renderer/hooks/use-chat'
import { useMessages } from '@renderer/hooks/use-message'
import { useTitlebar } from '@renderer/hooks/use-titlebar'
import { useParams } from 'react-router-dom'

export function ChatPage() {
  const { id } = useParams<{ id: string }>()
  const chat = useChat(Number(id))
  const { data } = useMessages(Number(id))

  useTitlebar({ title: chat.data ? chat.data.title : 'New Chat' })

  return (
    <div className="flex-grow px-4">
      <pre className='text-sm'>{JSON.stringify(data, null, 2)}</pre>
    </div>
  )
}
