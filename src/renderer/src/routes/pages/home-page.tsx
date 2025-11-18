import { Greeting } from '@renderer/components/greeting'
import { Textarea } from '@renderer/components/ui/textarea'
import { useTitlebar } from '@renderer/hooks/use-titlebar'

export function HomePage() {
  useTitlebar({ title: 'Kel' })

  return (
    <div className="flex flex-col h-[100vh]">
      <div className="h-8"></div>
      <div className="px-4">
        <Greeting />
      </div>

      <div className="flex-grow"></div>
      <div className='p-2'>
        <Textarea className='h-32' placeholder="Let's make something great!" />
      </div>
    </div>
  )
}
