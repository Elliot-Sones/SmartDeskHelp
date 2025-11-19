import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { InferElectron } from '@renderer/lib/types'

export type Chat = InferElectron<typeof window.api.chat.list>
export type CreateChatData = Parameters<typeof window.api.chat.create>[0]
export type UpdateChatData = Parameters<typeof window.api.chat.update>[1]

export const chatKey = ['chat'] as const

export function useChats() {
  const { data: chats, ...rest } = useQuery({
    queryKey: chatKey,
    queryFn: async () => await window.api.chat.list()
  })

  return { chats, ...rest }
}

export function useChat(id: number) {
  return useQuery({
    queryKey: ['chat', id],
    queryFn: async () => await window.api.chat.get(id),
    enabled: id > 0
  })
}

export function useCreateChat() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: CreateChatData) => {
      const result = await window.api.chat.create(data)
      return result
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: chatKey })
    }
  })
}

export function useUpdateChat() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ id, data }: { id: number; data: UpdateChatData }) => {
      const result = await window.api.chat.update(id, data)
      return result
    },
    onSuccess: (_data, { id }) => {
      queryClient.invalidateQueries({ queryKey: chatKey })
      queryClient.invalidateQueries({ queryKey: ['chat', id] })
    }
  })
}

export function useDeleteChat() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (id: number) => {
      const result = await window.api.chat.delete(id)
      return result
    },
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: chatKey })
      queryClient.removeQueries({ queryKey: ['chat', id] })
    }
  })
}
