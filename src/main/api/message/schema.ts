import { z } from 'zod'
import type { InferSelectModel } from 'drizzle-orm'
import type { message } from '../../db/tables/message'

// Inferred type from database schema
export type Message = InferSelectModel<typeof message>

// Zod schemas for validation
export const createMessageSchema = z.object({
  chatId: z.number().int().positive(),
  role: z.enum(['user', 'assistant']),
  content: z.string().min(1, 'Content is required')
})

// TypeScript types
export type CreateMessageData = z.infer<typeof createMessageSchema>

// Client-side API interface
export interface MessageApi {
  listByChatId: (chatId: number) => Promise<Message[]>
  create: (data: CreateMessageData) => Promise<Message>
  delete: (id: number) => Promise<boolean>
}
