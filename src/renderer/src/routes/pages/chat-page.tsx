import { useParams } from 'react-router-dom'

export function ChatPage() {
  const { id } = useParams<{ id: string }>()
  return <div>Hi! {id}</div>
}
