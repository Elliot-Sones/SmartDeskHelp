import { TextStreamPart, ToolSet } from 'ai'
import { z } from 'zod'

export const SupportedModels = [
  'anthropic/claude-sonnet-4.5',
  'anthropic/claude-haiku-4.5',
  'ollama/phi3.5:latest',
  'ollama/deepseek-r1:1.5b',
  'ollama/gemma3:4b',  // Vision-capable local model
  't5gemma/1b-1b'      // Encoder-decoder for efficient context→answer
] as const
export type SupportedModel = (typeof SupportedModels)[number]

// Zod schemas for validation
export const createChatNewSchema = z.object({
  prompt: z.string().min(1, 'Prompt is required'),
  chatId: z.number().int().positive().optional()
})

// TypeScript types
export type CreateChatNewData = z.infer<typeof createChatNewSchema>

export type ChatNewResponse = {
  chatId: number
}

export type StreamEvent = {
  chatId: number
  chunk: TextStreamPart<ToolSet>
}

// Client-side API interface
export interface AiApi {
  new: (data: CreateChatNewData) => Promise<ChatNewResponse>
  abort: () => Promise<void>
  onStream: (callback: (event: StreamEvent) => void) => () => void
}
