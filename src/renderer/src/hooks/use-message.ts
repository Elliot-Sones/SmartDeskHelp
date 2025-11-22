import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import type { InferElectron } from '@renderer/lib/types'
import type { StreamEvent } from '@shared/schemas'

export type Message = InferElectron<typeof window.api.message.listByChatId>
export type CreateMessageData = Parameters<typeof window.api.message.create>[0]

export const messageKey = ['message'] as const

export function useMessages(chatId: number) {
  const [streamBuffer, setStreamBuffer] = useState<string>('')

  const query = useQuery({
    queryKey: [messageKey, chatId],
    queryFn: async () => await window.api.message.listByChatId(chatId),
    enabled: chatId > 0
  })

  useEffect(() => {
    const unsubscribe = window.api.ai.onStream((event: StreamEvent) => {
      if (event.chatId !== chatId) return

      const { chunk } = event
      if (chunk.type === 'text-delta') {
        setStreamBuffer((prev) => prev + chunk.text)
      } else if (chunk.type === 'finish' || chunk.type === 'error') {
        setStreamBuffer('')
      }
    })

    return unsubscribe
  }, [chatId])

  return { ...query, streamBuffer }
}

export function useCreateMessage() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: CreateMessageData) => {
      const result = await window.api.message.create(data)
      return result
    },
    onSuccess: (_data, { chatId }) => {
      queryClient.invalidateQueries({ queryKey: [messageKey, chatId] })
    }
  })
}

export function useDeleteMessage() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (id: number) => {
      const result = await window.api.message.delete(id)
      return result
    },
    onSuccess: (_data, _id) => {
      queryClient.invalidateQueries({ queryKey: messageKey })
    }
  })
}
