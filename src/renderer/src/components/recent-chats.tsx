import { useChats } from '@renderer/hooks/use-chat'
import { Link } from 'react-router-dom'

export function RecentChats() {
  const { chats, isLoading } = useChats()

  if (isLoading) {
    return <div className="p-4 text-f-500">Loading chats...</div>
  }

  if (!chats || chats.length === 0) {
    return <div className="p-4 text-f-500 text-xs">No chats yet...</div>
  }

  return (
    <div className='px-4 text-xs flex flex-col'>
      {chats.map((chat) => (
        <Link
          to={`/chat/${chat.id}`}
          key={chat.id}
          className="py-1 text-f-300 hover:text-f-paper duration-200"
        >
          <div className="whitespace-nowrap truncate">{chat.title || 'Untitled Chat'}</div>
        </Link>
      ))}
    </div>
  )
}
