import { ipcMain, type BrowserWindow, shell } from 'electron'
import { eq } from 'drizzle-orm'
import { z } from 'zod'
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
import { streamText, smoothStream, type Tool } from 'ai'

let mainWindow: BrowserWindow | null = null
let currentAbortController: AbortController | null = null

export function setMainWindow(window: BrowserWindow) {
  mainWindow = window
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
  const { openrouter, selectedModel } = await createOpenRouter()

  const messages = await db
    .select()
    .from(message)
    .where(eq(message.chatId, chatId))
    .orderBy(message.createdAt)

  // Get the last user message for semantic routing
  const lastUserMessage = messages[messages.length - 1]?.content || ''

  // Route through semantic system to find relevant files
  let fileContext = ''
  let fileContent = ''
  let knowledgeContext = ''

  try {
    const { routerService } = await import('../../services/router')
    const { fileReaderService } = await import('../../services/file-reader')
    const { domainRouterService } = await import('../../services/domain-router')

    // Try knowledge system first for non-file queries
    try {
      const knowledgeResult = await domainRouterService.route(lastUserMessage)
      
      if (knowledgeResult.domain !== 'files' && knowledgeResult.results.length > 0) {
        knowledgeContext = `\n\n## Knowledge about the user/system:\n${knowledgeResult.results
          .slice(0, 10)
          .map((r: { content: string }) => `- ${r.content}`)
          .join('\n')}`
        console.log(`[AI] Found ${knowledgeResult.results.length} knowledge items for domain: ${knowledgeResult.domain}`)
      }
    } catch (knowledgeError) {
      console.log('[AI] Knowledge system not available:', knowledgeError)
    }

    const relevantFiles = await routerService.findRelevantFiles(lastUserMessage)

    if (relevantFiles.length > 0) {
      // Build context for LLM with file candidates
      fileContext = `\n\nFiles found on user's computer that may match their query:\n${relevantFiles
        .slice(0, 5)
        .map((f) => `- ${f.name} (${f.path}) [confidence: ${(f.score * 100).toFixed(0)}%]`)
        .join('\n')}`

      // Try to read content from the top match (for RAG)
      const topMatch = relevantFiles[0]
      if (topMatch.score > 0.3 && fileReaderService.isSupported(topMatch.path)) {
        console.log(`[AI] Reading content from: ${topMatch.name}`)
        const content = await fileReaderService.readFileContent(topMatch.path)
        
        if (content) {
          fileContent = `\n\n## Content from ${topMatch.name}:\n\`\`\`\n${content.text}\n\`\`\`${content.truncated ? '\n(Content truncated - file is larger)' : ''}`
          console.log(`[AI] Extracted ${content.text.length} chars from ${content.fileType} file`)
          
          // Opportunistic embedding enrichment: since we already read the full content,
          // update the embedding with richer content than the initial 500-char signature
          try {
            const { embeddingService } = await import('../../services/embedding')
            const { semanticFiles } = await import('../../db/schema')
            
            // Embed up to 2000 chars (much richer than 500-char signature)
            const enrichedText = content.text.slice(0, 2000)
            const enrichedEmbedding = await embeddingService.embed(enrichedText)
            
            // Update the file's content embedding in DB
            await db
              .update(semanticFiles)
              .set({
                contentSignature: enrichedText,
                contentEmbedding: embeddingService.serializeEmbedding(enrichedEmbedding)
              })
              .where(eq(semanticFiles.id, topMatch.id))
            
            console.log(`[AI] Enriched embedding for ${topMatch.name} with ${enrichedText.length} chars`)
          } catch (enrichError) {
            console.log(`[AI] Could not enrich embedding:`, enrichError)
          }
        }
      }
    }
  } catch (error) {
    console.error('[AI] Semantic routing error:', error)
  }

  // Simplified message format without image
  const formattedMessages = messages.map((m) => ({
    role: m.role,
    content: m.content
  }))

  currentAbortController = new AbortController()

  const systemPrompt = `You are Kel, an AI assistant who lives on your user's computer. You can help them find and open files, answer questions about file contents, and provide personalized answers based on what you know about their system.

Be helpful, creative, clever, and very friendly. When writing mathematical expressions or equations, always use $ for inline math and $$ for display math (LaTeX notation).
${knowledgeContext}

## File Search Results
${fileContext || '\nNo files found matching the current query.'}
${fileContent}

## Instructions for File Operations
- You have access to an "openFile" tool that can open files on the user's computer
- **IMPORTANT: You MUST use the EXACT paths from the file search results above. NEVER make up or guess file paths.**
- When the user wants to open a file and you found a good match (confidence > 50%), use the tool with the exact path shown above
- If you open a file, confirm what you opened using the exact filename and path from the results

## Instructions for Answering Questions About Files
- If file content is provided above, use it to answer the user's question
- If the user asks about something in a file (like dates, deadlines, information), look in the content section
- Quote relevant parts of the file content in your answer when appropriate
- If the content is truncated, let the user know you only saw part of the file

## Instructions for System/Personal Questions
- If knowledge context is provided above, use it to give personalized answers
- For questions about hardware, storage, or apps, refer to the system facts
- Be specific when you know facts about the user's setup

## Memory Instructions
After your response, if the user mentioned anything worth remembering, include it using <memory> tags.
Things worth remembering:
- Personal preferences (dark mode, favorite language, etc.)
- Facts about them (name, occupation, current projects)
- Goals or upcoming events (deadlines, interviews)

Format: <memory>fact to remember</memory>

Only include memories for NEW information. Do NOT remember:
- Generic questions about files or features
- Things you already know (from knowledge context above)
- Temporary or trivial information

Example: If user says "I'm a data scientist working on NLP", you might end your response with:
<memory>User is a data scientist</memory>
<memory>User works on NLP</memory>`

  // Define the openFile tool that the LLM can call
  const openFileTool: Tool<{ path: string; filename: string }, { success: boolean; message: string }> = {
    description: 'Opens a file on the user\'s computer using the default application',
    inputSchema: z.object({
      path: z.string().describe('The absolute path to the file to open'),
      filename: z.string().describe('The name of the file being opened (for confirmation)')
    }),
    execute: async ({ path, filename }) => {
      console.log(`[AI Tool] Opening file: ${path}`)
      try {
        // Try direct path first
        let result = await shell.openPath(path)

        // If direct path fails, try glob matching (handles Unicode filename issues)
        if (result !== '') {
          console.log(`[AI Tool] Direct path failed, trying glob fallback...`)

          // Extract directory and create a pattern from filename
          const { dirname } = await import('path')
          const { glob } = await import('glob')

          const dir = dirname(path)
          // Create pattern: first 10 chars + * + extension
          const ext = filename.includes('.') ? filename.slice(filename.lastIndexOf('.')) : ''
          const prefix = filename.slice(0, Math.min(10, filename.length)).replace(/[^\w\s]/g, '?')
          const pattern = `${dir}/${prefix}*${ext}`

          console.log(`[AI Tool] Glob pattern: ${pattern}`)
          const matches = await glob(pattern)

          if (matches.length > 0) {
            console.log(`[AI Tool] Found ${matches.length} matches, opening first: ${matches[0]}`)
            result = await shell.openPath(matches[0])
          }
        }

        if (result === '') {
          console.log(`[AI Tool] Successfully opened: ${filename}`)
          return { success: true, message: `Opened ${filename}` }
        } else {
          console.error(`[AI Tool] Failed to open file: ${result}`)
          return { success: false, message: `Failed to open: ${result}` }
        }
      } catch (error) {
        console.error(`[AI Tool] Error opening file:`, error)
        return { success: false, message: `Error opening file` }
      }
    }
  }

  const result = streamText({
    model: openrouter(selectedModel),
    system: systemPrompt,
    messages: formattedMessages,
    tools: {
      openFile: openFileTool
    },
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

    // Extract and store memories from the response
    const memories = extractMemoriesFromResponse(fullResponse)
    if (memories.length > 0) {
      console.log(`[AI] Extracted ${memories.length} memories:`, memories)
      try {
        const { personalMemoryService } = await import('../../services/personal-memory')
        for (const memory of memories) {
          await personalMemoryService.learn(memory, 'inferred')
        }
      } catch (memoryError) {
        console.log('[AI] Could not store memories:', memoryError)
      }
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
