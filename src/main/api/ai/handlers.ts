import { ipcMain, type BrowserWindow } from 'electron'
import { eq } from 'drizzle-orm'
import { db } from '../../db'
import { chat } from '../../db/tables/chat'
import { message } from '../../db/tables/message'
import {
  createChatNewSchema,
  type CreateChatNewData,
  type ChatNewResponse,
  type StreamEvent
} from './schema'
import { createOpenRouter } from '../../lib/openrouter'
import { getOllamaModel, parseOllamaModel } from '../../lib/ollama'
import { streamText, smoothStream } from 'ai'

let mainWindow: BrowserWindow | null = null
let currentAbortController: AbortController | null = null

// T5Gemma Answer Server config
const T5GEMMA_SERVER_URL = 'http://localhost:8766'

/**
 * Stream answer from T5Gemma server
 * Uses SSE endpoint for real-time token streaming
 */
async function streamT5GemmaAnswer(
  chatId: number,
  context: string,
  query: string,
  abortSignal: AbortSignal
): Promise<string> {
  const response = await fetch(`${T5GEMMA_SERVER_URL}/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ context, query, max_tokens: 512 }),
    signal: abortSignal
  })

  if (!response.ok) {
    throw new Error(`T5Gemma server error: ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) throw new Error('No response body')

  const decoder = new TextDecoder()
  let fullResponse = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      const chunk = decoder.decode(value, { stream: true })
      // Parse SSE events
      const lines = chunk.split('\n')
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            if (data.token) {
              fullResponse += data.token
              // Send as text-delta event (same format as other models)
              sendStreamEvent({
                chatId,
                chunk: { type: 'text-delta', id: 't5gemma', text: data.token }
              })
            }
            if (data.done) {
              // Send finish event
              sendStreamEvent({
                chatId,
                chunk: {
                  type: 'finish',
                  finishReason: 'stop',
                  totalUsage: { inputTokens: 0, outputTokens: 0, totalTokens: 0 }
                }
              })
            }
          } catch {
            // Ignore parse errors for incomplete chunks
          }
        }
      }
    }
  } finally {
    reader.releaseLock()
  }

  return fullResponse
}

/**
 * Check if T5Gemma server is running
 */
async function isT5GemmaServerRunning(): Promise<boolean> {
  try {
    const response = await fetch(`${T5GEMMA_SERVER_URL}/health`, {
      method: 'GET',
      signal: AbortSignal.timeout(2000)
    })
    return response.ok
  } catch {
    return false
  }
}

// Initialize gemma router on startup (keeps model loaded)
let gemmaRouterInitialized = false

async function initializeGemmaRouter(): Promise<void> {
  if (gemmaRouterInitialized) return
  
  try {
    const { gemmaRouterService } = await import('../../services/orchestration/tool-router')
    await gemmaRouterService.initialize()
    gemmaRouterInitialized = true
    console.log('[AI] Gemma router initialized and ready')
  } catch (error) {
    console.log('[AI] Gemma router initialization failed, will use fallback:', error)
  }
}

export function setMainWindow(window: BrowserWindow) {
  mainWindow = window
  // Initialize gemma router when window is set (app startup)
  initializeGemmaRouter()
}

export function sendStreamEvent(event: StreamEvent) {
  mainWindow?.webContents.send('chat:stream', event)
}

/**
 * Extract memory tags from LLM response
 * Format: <memory>fact to remember</memory>
 */
function extractMemoriesFromResponse(response: string): string[] {
  const regex = /<memory>(.*?)<\/memory>/gs
  const memories: string[] = []
  let match
  
  while ((match = regex.exec(response)) !== null) {
    const memory = match[1].trim()
    if (memory) {
      memories.push(memory)
    }
  }
  
  return memories
}

async function createNewChat(prompt: string) {
  const title = prompt.length > 150 ? prompt.substring(0, 150) + '...' : prompt

  const chatResult = await db
    .insert(chat)
    .values({
      title
    })
    .returning()

  const newChat = chatResult[0]

  await db.insert(message).values({
    chatId: newChat.id,
    role: 'user',
    content: prompt
  })

  return newChat.id
}

async function processAiStream(chatId: number) {
  // Get selected model from settings
  const { openrouter, selectedModel } = await createOpenRouter()

  // Check if using T5Gemma (encoder-decoder model)
  const isT5GemmaModel = selectedModel.startsWith('t5gemma/')

  // Determine which provider to use based on model prefix
  const isOllamaModel = selectedModel.startsWith('ollama/')
  const modelProvider = isOllamaModel
    ? getOllamaModel(parseOllamaModel(selectedModel))
    : openrouter(selectedModel)

  const messages = await db
    .select()
    .from(message)
    .where(eq(message.chatId, chatId))
    .orderBy(message.createdAt)

  // Get the last user message for intelligent routing
  const lastUserMessage = messages[messages.length - 1]?.content || ''

  // Session context is now handled by LEANN if needed in the future
  const sessionContextStr = ''

  // Use Tool Router for intelligent tool selection and context gathering via LEANN
  let toolContext = ''

  try {
    const { gemmaRouterService } = await import('../../services/orchestration/tool-router')

    console.log(`[AI] Routing query through Gemma Router...`)
    const routerResult = await gemmaRouterService.routeWithTools(lastUserMessage)

    console.log(`[AI] Tool selected: ${routerResult.selectedTool} (routing: ${routerResult.routingTimeMs}ms, execution: ${routerResult.executionTimeMs}ms)`)

    if (routerResult.toolResult && routerResult.toolResult.context) {
      toolContext = routerResult.toolResult.context
    }
  } catch (error) {
    console.error('[AI] Gemma routing error:', error)
    // Fall through with empty context - LLM will respond without tool context
  }

  currentAbortController = new AbortController()

  // ============================================
  // T5Gemma Path: Encoder-decoder for efficient context→answer
  // ============================================
  if (isT5GemmaModel) {
    console.log('[AI] Using T5Gemma encoder-decoder model')

    // Check if T5Gemma server is running
    const serverRunning = await isT5GemmaServerRunning()
    if (!serverRunning) {
      console.error('[AI] T5Gemma server not running on port 8766')
      sendStreamEvent({
        chatId,
        chunk: { type: 'text-delta', id: 't5gemma-error', text: 'Error: T5Gemma server not running. Start it with: python python/t5gemma_answer_server.py' }
      })
      sendStreamEvent({
        chatId,
        chunk: { type: 'finish', finishReason: 'error', totalUsage: { inputTokens: 0, outputTokens: 0, totalTokens: 0 } }
      })
      return
    }

    // Build context for T5Gemma (combines tool context + session context)
    const fullContext = `${toolContext}${sessionContextStr}`.trim()

    let fullResponse = ''
    try {
      fullResponse = await streamT5GemmaAnswer(
        chatId,
        fullContext,
        lastUserMessage,
        currentAbortController.signal
      )

      // Save response to database
      await db.insert(message).values({
        chatId,
        role: 'assistant',
        content: fullResponse.trim()
      })
    } catch (error: unknown) {
      if (error instanceof Error && error.name === 'AbortError') {
        if (fullResponse.trim()) {
          await db.insert(message).values({
            chatId,
            role: 'assistant',
            content: fullResponse
          })
        }
        sendStreamEvent({
          chatId,
          chunk: { type: 'finish', finishReason: 'stop', totalUsage: { inputTokens: 0, outputTokens: 0, totalTokens: 0 } }
        })
      } else {
        throw error
      }
    } finally {
      currentAbortController = null
    }
    return
  }

  // ============================================
  // Standard Path: Ollama / OpenRouter (decoder-only)
  // ============================================

  // Simplified message format without image
  const formattedMessages = messages.map((m) => ({
    role: m.role,
    content: m.content
  }))

  // Simplified system prompt for local LLMs
  const systemPrompt = `You are Minnie, a friendly AI assistant on this computer. Be helpful and concise.
${toolContext}${sessionContextStr}

If the user mentioned personal facts, remember them with <memory>fact</memory> tags.`

  const result = streamText({
    model: modelProvider,
    system: systemPrompt,
    messages: formattedMessages,
    experimental_transform: smoothStream({
      delayInMs: 50
    }),
    abortSignal: currentAbortController.signal
  })

  let fullResponse = ''
  try {
    for await (const chunk of result.fullStream) {
      if (chunk.type === 'text-delta') {
        fullResponse += chunk.text
        sendStreamEvent({ chatId, chunk })
      } else if (chunk.type === 'tool-call') {
        // Tool is being called - the execute function handles it
        console.log(`[AI] Tool called: ${chunk.toolName} with input:`, chunk.input)
      } else if (chunk.type === 'tool-result') {
        // Tool finished executing
        console.log(`[AI] Tool result:`, chunk.output)
      } else if (chunk.type === 'finish') {
        sendStreamEvent({ chatId, chunk })
      }
    }

    // Extract memories from response (for future LEANN integration)
    const memories = extractMemoriesFromResponse(fullResponse)
    if (memories.length > 0) {
      console.log(`[AI] Extracted ${memories.length} memories:`, memories)
      // TODO: Add learning endpoint to Python LEANN server
    }

    // Remove memory tags from the response before saving
    const cleanResponse = fullResponse.replace(/<memory>.*?<\/memory>/gs, '').trim()

    await db.insert(message).values({
      chatId,
      role: 'assistant',
      content: cleanResponse
    })
  } catch (error: unknown) {
    // If aborted, save partial response
    if (error instanceof Error && error.name === 'AbortError') {
      if (fullResponse.trim()) {
        await db.insert(message).values({
          chatId,
          role: 'assistant',
          content: fullResponse
        })
      }
      // Send finish event after abort
      sendStreamEvent({
        chatId,
        chunk: {
          type: 'finish',
          finishReason: 'stop',
          totalUsage: {
            inputTokens: 0,
            outputTokens: 0,
            totalTokens: 0
          }
        }
      })
    } else {
      throw error
    }
  } finally {
    currentAbortController = null
  }
}

export function registerAiHandlers() {
  ipcMain.handle('chat:new', async (_event, data: CreateChatNewData): Promise<ChatNewResponse> => {
    const validated = createChatNewSchema.parse(data)

    let chatId: number
    if (validated.chatId) {
      chatId = validated.chatId
      await db.insert(message).values({
        chatId,
        role: 'user',
        content: validated.prompt
      })
    } else {
      chatId = await createNewChat(validated.prompt)
    }

    processAiStream(chatId).catch((error) => {
      console.error('AI stream processing error:', error)
    })

    return { chatId }
  })

  ipcMain.handle('chat:abort', async () => {
    if (currentAbortController) {
      currentAbortController.abort()
      currentAbortController = null
    }
  })
}
