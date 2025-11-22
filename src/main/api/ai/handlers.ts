import { ipcMain, type BrowserWindow } from 'electron'
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
import { streamText } from 'ai';

let mainWindow: BrowserWindow | null = null

export function setMainWindow(window: BrowserWindow) {
  mainWindow = window
}

export function sendStreamEvent(event: StreamEvent) {
  mainWindow?.webContents.send('chat:stream', event)
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

export function registerAiHandlers() {
  ipcMain.handle('chat:new', async (_event, data: CreateChatNewData): Promise<ChatNewResponse> => {
    const validated = createChatNewSchema.parse(data)
    const chatId = await createNewChat(validated.prompt)

    // Example: Stream to renderer
    const { openrouter, selectedModel } = await createOpenRouter()
    const result = streamText({
      model: openrouter(selectedModel),
      prompt: validated.prompt,
    })
    
    for await (const chunk of result.fullStream) {
      if (chunk.type === 'text-delta') {
        sendStreamEvent({ chatId, chunk })
      } else if (chunk.type === 'finish') {
        sendStreamEvent({ chatId, chunk })
      }
    }

    return { chatId }
  })
}
