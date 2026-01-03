import { z } from 'zod'
import type { InferSelectModel } from 'drizzle-orm'
import type { chat } from '../../db/tables/chat'

// Inferred type from database schema
export type Chat = InferSelectModel<typeof chat>

// Zod schemas for validation
export const createChatSchema = z.object({
  title: z.string().min(1, 'Title is required').max(255)
})

export const updateChatSchema = z.object({
  title: z.string().min(1, 'Title is required').max(255).optional()
})

// TypeScript types
export type CreateChatData = z.infer<typeof createChatSchema>
export type UpdateChatData = z.infer<typeof updateChatSchema>

// Client-side API interface
export interface ChatApi {
  list: () => Promise<Chat[]>
  create: (data: CreateChatData) => Promise<Chat>
  update: (id: number, data: UpdateChatData) => Promise<Chat | null>
  delete: (id: number) => Promise<boolean>
  get: (id: number) => Promise<Chat | null>
  closeSession: (id: number) => Promise<boolean>
}
