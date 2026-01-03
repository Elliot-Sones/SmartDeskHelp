import { Titlebar } from '@renderer/components/Titlebar'
import { Outlet, useNavigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState, useEffect, useRef } from 'react'
import { TitlebarContext } from '@renderer/hooks/use-titlebar'
import { Disclaimer } from '@renderer/components/disclaimer'

export function RootLayout() {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: 1,
          },
          mutations: {
            retry: 1
          }
        }
      })
  )

  const [title, setTitle] = useState('Minnie')
  const navigate = useNavigate()

  // Listen for query from search popup
  // Use ref to prevent StrictMode double-mount from creating duplicate listeners
  const hasSubscribedRef = useRef(false)

  useEffect(() => {
    // Guard against StrictMode double-mount
    if (hasSubscribedRef.current) return
    hasSubscribedRef.current = true

    const handlePopupQuery = async (_event: unknown, query: string): Promise<void> => {
      console.log('[RootLayout] Received query from popup:', query)
      try {
        // Create a new chat with the query
        const result = await window.api.ai.new({ prompt: query })
        // Navigate to the new chat
        navigate(`/chat/${result.chatId}`)
      } catch (error) {
        console.error('[RootLayout] Failed to create chat from popup:', error)
      }
    }

    window.electron.ipcRenderer.on('submit-query-from-popup', handlePopupQuery)

    return () => {
      window.electron.ipcRenderer.removeListener('submit-query-from-popup', handlePopupQuery)
      hasSubscribedRef.current = false
    }
  }, [navigate])

  return (
    <QueryClientProvider client={queryClient}>
      <TitlebarContext.Provider value={{ title, setTitle }}>
        <div className="bg-background/75 text-foreground h-[100vh] border glass-divider flex flex-col overflow-x-hidden">
          <Titlebar />
          <Outlet />
          <Disclaimer />
        </div>
      </TitlebarContext.Provider>
    </QueryClientProvider>
  )
}

