/**
 * Gemma Router Service
 * 
 * Uses FunctionGemma (270M) with 3 meta-tools for better accuracy:
 * - local_query: Files, system, memory, apps, disk
 * - web_query: Internet searches
 * - conversation: Chat without tools
 */

// Python server endpoint (function-gemma 270M)
const PYTHON_SERVER_URL = 'http://localhost:8765'

import { userInfo } from 'os'

// Meta-tool names (3 core + 1 multi for ambiguous queries)
type ToolName = 
  | 'local_query'   // Files, system, memory, apps, disk
  | 'web_query'     // Internet searches
  | 'conversation'  // Chat without actions
  | 'multi_query'   // Ambiguous queries - call multiple tools
  | 'see'           // Screenshot + vision model description
  | 'no_tool'       // Fallback

// Rich arguments from FunctionGemma
interface ToolArguments {
  // Common
  query?: string
  
  // For local_query
  intent?: 'find' | 'read' | 'open' | 'list' | 'analyze' | 'recall'
  target?: 'files' | 'system' | 'memory' | 'apps' | 'disk'
  file_types?: string[]
  location?: string
  date_range?: string
  metrics?: string[]
  search_terms?: string[]  // Key terms extracted from query for better embedding search
  
  // For web_query
  topic?: 'weather' | 'news' | 'facts' | 'prices' | 'events' | 'general'
  
  // For conversation
  type?: 'greeting' | 'farewell' | 'thanks' | 'help' | 'chat'
}

interface ToolResult {
  tool: ToolName
  success: boolean
  data: unknown
  context: string
}

interface RouterResult {
  selectedTool: ToolName
  arguments: ToolArguments
  toolResult: ToolResult | null
  multiToolResults?: ToolResult[]  // For multi_tool: array of all tool results
  routingTimeMs: number
  executionTimeMs: number
  routingMethod: 'function-gemma' | 'keywords'
}

class GemmaRouterService {
  private initPromise: Promise<void> | null = null
  private initAttempted = false
  private usePythonServer = false

  /**
   * Initialize the router - checks for Python server availability
   */
  async initialize(): Promise<boolean> {
    if (this.initAttempted) {
      return this.usePythonServer
    }
    
    if (this.initPromise) {
      await this.initPromise
      return this.usePythonServer
    }

    this.initPromise = this.doInitialize()
    await this.initPromise
    return this.usePythonServer
  }

  private async doInitialize(): Promise<void> {
    this.initAttempted = true

    // 1. Try Python function-gemma server first (best option)
    console.log('[GemmaRouter] Checking Python function-gemma server...')
    try {
      const response = await fetch(`${PYTHON_SERVER_URL}/health`, {
        method: 'GET',
        signal: AbortSignal.timeout(2000)
      })
      
      if (response.ok) {
        const data = await response.json()
        console.log(`[GemmaRouter] ✓ Python server available (${data.model})`)
        this.usePythonServer = true
        return
      }
    } catch {
      console.log('[GemmaRouter] Python server not running')
    }

    console.log('[GemmaRouter] Using keyword-only fallback')
  }

  /**
   * Route a query to the appropriate tool
   */
  async routeWithTools(query: string): Promise<RouterResult> {
    const startTime = Date.now()
    
    await this.initialize()
    
    let selectedTool: ToolName
    let toolArguments: ToolArguments = { query }
    let routingMethod: 'function-gemma' | 'keywords' = 'keywords'

    // Try Python function-gemma server first
    if (this.usePythonServer) {
      try {
        const result = await this.routeWithPythonServer(query)
        selectedTool = result.tool
        toolArguments = { query, ...result.arguments }
        routingMethod = 'function-gemma'
        console.log(`[GemmaRouter] FunctionGemma args:`, toolArguments)
      } catch (error) {
        console.log('[GemmaRouter] Python server routing failed:', error)
        // Fall back to keywords
        selectedTool = this.keywordFallback(query)
      }
    } else {
      selectedTool = this.keywordFallback(query)
    }
    
    const routingTimeMs = Date.now() - startTime
    console.log(`[GemmaRouter] ${routingMethod} selected: ${selectedTool} (${routingTimeMs}ms)`)
    
    const execStartTime = Date.now()
    const toolResult = await this.executeTool(selectedTool, toolArguments)
    const executionTimeMs = Date.now() - execStartTime
    
    return {
      selectedTool,
      arguments: toolArguments,
      toolResult,
      routingTimeMs,
      executionTimeMs,
      routingMethod
    }
  }

  /**
   * Route using Python function-gemma server
   */
  private async routeWithPythonServer(query: string): Promise<{ tool: ToolName; arguments: ToolArguments }> {
    const { username } = userInfo()
    
    const response = await fetch(`${PYTHON_SERVER_URL}/route`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, username }),
      signal: AbortSignal.timeout(5000)
    })
    
    if (!response.ok) {
      throw new Error(`Python server error: ${response.status}`)
    }
    
    const data = await response.json()
    
    if (data.error) {
      throw new Error(data.error)
    }
    
    return {
      tool: this.validateToolName(data.tool),
      arguments: data.arguments || {}
    }
  }

  /**
   * Validate and normalize tool name to 3 meta-tools
   */
  private validateToolName(tool: string): ToolName {
    const normalized = tool.toLowerCase().trim()
    
    // Map to 3 meta-tools
    if (normalized === 'local_query') return 'local_query'
    if (normalized === 'web_query') return 'web_query'
    if (normalized === 'conversation') return 'conversation'
    
    // Legacy mappings for old tool names
    if (['search_files', 'read_file_content', 'open_file', 'get_system_info', 
         'analyze_disk', 'get_user_memory'].includes(normalized)) {
      return 'local_query'
    }
    if (['web_search', 'mcp_search'].includes(normalized)) {
      return 'web_query'
    }
    if (['no_tool'].includes(normalized)) {
      return 'conversation'
    }
    
    return 'no_tool'
  }

  /**
   * Keyword-based fallback routing for 3 meta-tools
   */
  private keywordFallback(query: string): ToolName {
    const q = query.toLowerCase()
    
    // Local computer queries
    if (/\b(find|search|open|read|file|document|pdf|photo|image|folder|project|resume|tax)\b/.test(q) ||
        /\b(ram|memory|cpu|disk|storage|battery|specs?|system|process|slow)\b/.test(q) ||
        /\b(my favorite|about me|remember|what do you know)\b/.test(q)) {
      return 'local_query'
    }
    
    // Web queries
    if (/\b(weather|news|current|latest|stock|price|who is|what is today|search online)\b/.test(q) &&
        !/\b(my|file|folder|document|downloaded)\b/.test(q)) {
      return 'web_query'
    }
    
    // Conversation (greetings, thanks, help)
    if (/\b(hello|hi|hey|thanks|thank you|bye|help|what can you do)\b/.test(q)) {
      return 'conversation'
    }
    
    // Default to local_query for ambiguous queries
    return 'local_query'
  }

  /**
   * Execute the selected meta-tool and return formatted context
   */
  private async executeTool(tool: ToolName, args: ToolArguments): Promise<ToolResult> {
    try {
      switch (tool) {
        case 'local_query':
          return await this.executeLocalQuery(args)
        case 'web_query':
          return await this.executeWebQuery(args)
        case 'multi_query':
          return await this.executeMultiQuery(args)
        case 'see':
          return await this.executeSee(args)
        case 'conversation':
          return { tool: 'conversation', success: true, data: null, context: '' }
        case 'no_tool':
        default:
          return { tool: 'no_tool', success: true, data: null, context: '' }
      }
    } catch (error) {
      console.error(`[GemmaRouter] Tool execution failed for ${tool}:`, error)
      return { tool, success: false, data: error, context: `(Error executing ${tool})` }
    }
  }

  /**
   * Execute local_query - routes to appropriate local service based on intent & target
   */
  private async executeLocalQuery(args: ToolArguments): Promise<ToolResult> {
    const intent = args.intent || 'find'
    const target = args.target || 'files'
    const query = args.query || ''
    const searchTerms = args.search_terms || []
    
    // Use search_terms for embedding if provided (much better similarity scores)
    // Fall back to raw query if no terms extracted
    const embeddingQuery = searchTerms.length > 0 ? searchTerms.join(' ') : query
    
    console.log(`[GemmaRouter] Local query: intent=${intent}, target=${target}`)
    console.log(`[GemmaRouter] Raw query: "${query}"`)
    console.log(`[GemmaRouter] Search terms: [${searchTerms.join(', ')}] → embedding query: "${embeddingQuery}"`)
    
    // Handle based on target
    switch (target) {
      case 'files': {
        const { fileSearchService } = await import('../tools/helpers/file-search')
        
        // Use deep content search for 'read' intent (questions about file content)
        // This triggers LAZY CHUNKING: chunks are generated on-demand and cached
        if (intent === 'read') {
          console.log('[GemmaRouter] Using deep content search for read intent')
          const { files, chunks } = await fileSearchService.searchWithContent(embeddingQuery)
          
          if (files.length === 0 && chunks.length === 0) {
            return { tool: 'local_query', success: true, data: [], context: '\n\n## File Search\nNo matching files found.' }
          }
          
          // Format results with chunk content for LLM
          let context = '\n\n## File Content Results\n'
          for (const file of files.slice(0, 3)) {
            context += `### ${file.name}\n`
            context += `*Path: ${file.path}*\n\n`
            
            // Include matching chunk content
            const fileChunks = chunks.filter(c => c.fileId === file.id)
            if (fileChunks.length > 0) {
              context += '**Relevant content:**\n'
              context += fileChunks.slice(0, 2).map(c => `> ${c.chunkContent.trim()}`).join('\n\n...\n\n')
              context += '\n\n'
            }
          }
          
          return { tool: 'local_query', success: true, data: { files, chunks }, context }
        }
        
        // Use filtered search if we have filters
        const hasFilters = args.file_types || args.location || args.date_range
        const files = hasFilters
          ? await fileSearchService.findFilesWithFilters({
              query: embeddingQuery,
              file_types: args.file_types,
              location: args.location,
              date_range: args.date_range
            })
          : await fileSearchService.findRelevantFiles(embeddingQuery)
        
        if (files.length === 0) {
          return { tool: 'local_query', success: true, data: [], context: '\n\n## File Search\nNo matching files found.' }
        }
        
        // If intent is 'open', open the first file
        if (intent === 'open' && files.length > 0) {
          const { openFile } = await import('../tools/actions/file-opener')
          await openFile(files[0].path)
          return { tool: 'local_query', success: true, data: files[0], context: `\n\n## Action\nOpened: ${files[0].name}` }
        }
        
        // NOTE: 'read' intent is now handled earlier with deep content search (searchWithContent)
        
        // Default: return file list
        const context = `\n\n## File Search Results\n${files.slice(0, 5).map((f, i) => 
          `${i + 1}. **${f.name}** - ${f.path}`).join('\n')}`
        return { tool: 'local_query', success: true, data: files, context }
      }
      
      case 'system': {
        const { knowledgeStoreService } = await import('../tools/helpers/knowledge-store')
        const items = await knowledgeStoreService.query(query || 'computer specs', 'computer')
        
        if (items.length === 0) {
          return { tool: 'local_query', success: true, data: [], context: '\n\n## System Info\nNo system information indexed yet.' }
        }
        
        return {
          tool: 'local_query',
          success: true,
          data: items,
          context: `\n\n## System Information\n${items.slice(0, 5).map(item => `- ${item.content}`).join('\n')}`
        }
      }
      
      case 'memory': {
        const { personalMemoryService } = await import('../tools/helpers/personal-memory')
        const memories = await personalMemoryService.recall(query)
        
        if (memories.length === 0) {
          return { tool: 'local_query', success: true, data: [], context: "\n\n## About You\nI don't know much about you yet. Tell me about yourself!" }
        }
        
        return {
          tool: 'local_query',
          success: true,
          data: memories,
          context: `\n\n## What I Know About You\n${memories.slice(0, 5).map(m => `- ${m}`).join('\n')}`
        }
      }
      
      case 'disk': {
        // TODO: Implement disk analysis
        return {
          tool: 'local_query',
          success: true,
          data: {},
          context: '\n\n## Disk Analysis\nDisk analysis is not yet implemented.'
        }
      }
      
      default:
        return { tool: 'local_query', success: false, data: null, context: `Unknown target: ${target}` }
    }
  }

  /**
   * Execute web_query - search the internet
   */
  private async executeWebQuery(args: ToolArguments): Promise<ToolResult> {
    const { googleSearchService } = await import('../tools/actions/google-search')
    const results = await googleSearchService.search(args.query || '')
    
    return {
      tool: 'web_query',
      success: true,
      data: results,
      context: `\n\n## Web Search\n${googleSearchService.formatForLLM(results)}`
    }
  }

  /**
   * Execute multi_query - call multiple tools in parallel for ambiguous queries
   * Gives the main LLM rich context to synthesize the best answer
   */
  private async executeMultiQuery(args: ToolArguments): Promise<ToolResult> {
    console.log(`[GemmaRouter] Multi-query: gathering context from system + web`)
    
    // Call both tools in parallel
    const [systemResult, webResult] = await Promise.allSettled([
      this.executeLocalQuery({ ...args, intent: 'analyze', target: 'system', metrics: ['all'] }),
      this.executeWebQuery(args)
    ])
    
    // Combine contexts
    const contexts: string[] = []
    const data: Record<string, unknown> = {}
    
    if (systemResult.status === 'fulfilled' && systemResult.value.success) {
      contexts.push(systemResult.value.context)
      data.system = systemResult.value.data
    }
    
    if (webResult.status === 'fulfilled' && webResult.value.success) {
      contexts.push(webResult.value.context)
      data.web = webResult.value.data
    }
    
    return {
      tool: 'multi_query',
      success: true,
      data,
      context: contexts.join('\n') || '\n\n## Context\nNo additional context available.'
    }
  }

  /**
   * Execute see - capture screenshot and describe using Gemma3:4b vision model
   * Always uses Gemma3:4b regardless of selected model (vision-capable)
   */
  private async executeSee(args: ToolArguments): Promise<ToolResult> {
    console.log('[GemmaRouter] Executing see tool - capturing screen...')
    
    try {
      // Capture screenshot
      const { screenCaptureService } = await import('../tools/actions/screen-capture')
      const screenshotBase64 = await screenCaptureService.captureScreenBase64()
      
      console.log('[GemmaRouter] Screenshot captured, sending to Gemma3:4b vision model...')
      
      // Send to Gemma3:4b vision model via Ollama
      // Using the Ollama API directly for vision since we need to force Gemma3:4b
      const response = await fetch('http://localhost:11434/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: 'gemma3:4b',
          prompt: args.query || 'Describe what you see on this screen. Be concise but thorough.',
          images: [screenshotBase64],
          stream: false
        })
      })
      
      if (!response.ok) {
        throw new Error(`Ollama API error: ${response.status}`)
      }
      
      const data = await response.json()
      const description = data.response || 'Could not describe the screen'
      
      console.log('[GemmaRouter] Vision model responded with description')
      
      return {
        tool: 'see',
        success: true,
        data: { description },
        context: `\n\n## Screen Description\n${description}`
      }
    } catch (error) {
      console.error('[GemmaRouter] See tool failed:', error)
      return {
        tool: 'see',
        success: false,
        data: error,
        context: '\n\n## Screen Description\nFailed to capture or analyze screen. Make sure Ollama is running with gemma3:4b model.'
      }
    }
  }
}

// Export singleton instance
export const gemmaRouterService = new GemmaRouterService()

export type { ToolName, ToolArguments, ToolResult, RouterResult }
