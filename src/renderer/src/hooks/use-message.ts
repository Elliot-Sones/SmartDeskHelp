import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { InferElectron } from '@renderer/lib/types'

export type Message = InferElectron<typeof window.api.message.listByChatId>
export type CreateMessageData = Parameters<typeof window.api.message.create>[0]

export const messageKey = ['message'] as const

export function useMessages(chatId: number) {
  return useQuery({
    queryKey: [messageKey, chatId],
    queryFn: async () => await window.api.message.listByChatId(chatId),
    enabled: chatId > 0
  })
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
