import { useTitlebar } from '@renderer/hooks/use-titlebar'

export function Titlebar() {
  const { title } = useTitlebar()

  return (
    <div className="h-7 flex items-center justify-center text-xs font-[450] text-f-500 gap-2">
      {title}
    </div>
  )
}
