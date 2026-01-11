/**
 * Tool Router Service
 *
 * Routes user queries to the appropriate tool and executes them.
 *
 * Architecture:
 *   User Query → FunctionGemma (routing) → Tool Execution → Context for LLM
 *
 * Tools:
 *   - local_query: Search files, system info, or personal memory via LEANN
 *   - web_query: Search the internet
 *   - conversation: Chat without any tools
 *   - see: Screenshot + vision model analysis
 *
 * The Python server (localhost:8765) provides:
 *   - /route: FunctionGemma-based query routing
 *   - /search: LEANN vector search
 *
 * @module services/orchestration/tool-router
 */

import { userInfo } from 'os'
import { leannClient, type SearchResult } from '../leann'

// ============================================================================
// CONFIGURATION
// ============================================================================

const PYTHON_SERVER_URL = 'http://localhost:8765'

// ============================================================================
// TYPES
// ============================================================================

/**
 * Available tool names.
 */
export type ToolName =
  | 'local_query' // Files, system, memory via LEANN
  | 'web_query' // Internet search
  | 'conversation' // Chat without tools
  | 'multi_query' // Parallel query to multiple sources
  | 'see' // Screenshot + vision
  | 'no_tool' // Fallback

/**
 * Arguments extracted by FunctionGemma from user query.
 */
export interface ToolArguments {
  // Common
  query?: string

  // For local_query
  intent?: 'find' | 'read' | 'open' | 'list' | 'analyze' | 'recall'
  target?: 'files' | 'system' | 'memory' | 'apps' | 'disk' | 'photos'
  file_types?: string[]
  location?: string
  date_range?: string
  search_terms?: string[] // Extracted keywords for better embedding search

  // For web_query
  topic?: 'weather' | 'news' | 'facts' | 'prices' | 'events' | 'general'

  // For conversation
  type?: 'greeting' | 'farewell' | 'thanks' | 'help' | 'chat'
}

/**
 * Result from executing a tool.
 */
export interface ToolResult {
  tool: ToolName
  success: boolean
  data: unknown
  context: string // Formatted context string for LLM
}

/**
 * Complete result from routing and executing a query.
 */
export interface RouterResult {
  selectedTool: ToolName
  arguments: ToolArguments
  toolResult: ToolResult | null
  routingTimeMs: number
  executionTimeMs: number
  routingMethod: 'function-gemma' | 'keywords'
}

// ============================================================================
// TOOL ROUTER SERVICE
// ============================================================================

class ToolRouterService {
  private pythonServerAvailable = false
  private initAttempted = false

  /**
   * Initialize the router by checking Python server availability.
   */
  async initialize(): Promise<boolean> {
    if (this.initAttempted) {
      return this.pythonServerAvailable
    }

    this.initAttempted = true
    console.log('[ToolRouter] Checking Python server availability...')

    try {
      const response = await fetch(`${PYTHON_SERVER_URL}/health`, {
        method: 'GET',
        signal: AbortSignal.timeout(2000)
      })

      if (response.ok) {
        const data = await response.json()
        console.log(`[ToolRouter] Python server available (${data.model})`)
        this.pythonServerAvailable = true
      }
    } catch {
      console.log('[ToolRouter] Python server not running, using keyword fallback')
    }

    return this.pythonServerAvailable
  }

  /**
   * Route a query to the appropriate tool and execute it.
   * @alias routeWithTools (for backwards compatibility)
   */
  async routeAndExecute(query: string): Promise<RouterResult> {
    const startTime = Date.now()
    await this.initialize()

    // Step 1: Route the query
    let selectedTool: ToolName
    let toolArguments: ToolArguments = { query }
    let routingMethod: 'function-gemma' | 'keywords' = 'keywords'

    if (this.pythonServerAvailable) {
      try {
        const routeResult = await this.routeWithPythonServer(query)
        selectedTool = routeResult.tool
        toolArguments = { query, ...routeResult.arguments }
        routingMethod = 'function-gemma'
      } catch (error) {
        console.log('[ToolRouter] Python routing failed, using fallback:', error)
        selectedTool = this.keywordFallback(query)
      }
    } else {
      selectedTool = this.keywordFallback(query)
    }

    const routingTimeMs = Date.now() - startTime
    console.log(`[ToolRouter] ${routingMethod} → ${selectedTool} (${routingTimeMs}ms)`)

    // Step 2: Execute the tool
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

  // --------------------------------------------------------------------------
  // ROUTING METHODS
  // --------------------------------------------------------------------------

  /**
   * Route using Python FunctionGemma server.
   */
  private async routeWithPythonServer(
    query: string
  ): Promise<{ tool: ToolName; arguments: ToolArguments }> {
    const { username } = userInfo()

    const response = await fetch(`${PYTHON_SERVER_URL}/route`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, username }),
      signal: AbortSignal.timeout(5000)
    })

    if (!response.ok) {
      throw new Error(`Server error: ${response.status}`)
    }

    const data = await response.json()
    if (data.error) {
      throw new Error(data.error)
    }

    return {
      tool: this.normalizeToolName(data.tool),
      arguments: data.arguments || {}
    }
  }

  /**
   * Normalize tool name from various formats.
   */
  private normalizeToolName(tool: string): ToolName {
    const normalized = tool.toLowerCase().trim()

    // Direct matches
    if (normalized === 'local_query') return 'local_query'
    if (normalized === 'web_query') return 'web_query'
    if (normalized === 'conversation') return 'conversation'
    if (normalized === 'multi_query') return 'multi_query'
    if (normalized === 'see') return 'see'

    // Legacy tool name mappings
    const localTools = [
      'search_files',
      'read_file_content',
      'open_file',
      'get_system_info',
      'analyze_disk',
      'get_user_memory'
    ]
    if (localTools.includes(normalized)) return 'local_query'

    const webTools = ['web_search', 'mcp_search']
    if (webTools.includes(normalized)) return 'web_query'

    if (normalized === 'no_tool') return 'conversation'

    return 'no_tool'
  }

  /**
   * Keyword-based fallback routing when Python server unavailable.
   */
  private keywordFallback(query: string): ToolName {
    const q = query.toLowerCase()

    // Local queries (files, system, memory)
    const localPatterns =
      /\b(find|search|open|read|file|document|pdf|photo|image|folder|project|resume|tax)\b/
    const systemPatterns = /\b(ram|memory|cpu|disk|storage|battery|specs?|system|process|slow)\b/
    const memoryPatterns = /\b(my favorite|about me|remember|what do you know)\b/

    if (localPatterns.test(q) || systemPatterns.test(q) || memoryPatterns.test(q)) {
      return 'local_query'
    }

    // Web queries
    const webPatterns =
      /\b(weather|news|current|latest|stock|price|who is|what is today|search online)\b/
    const notWebPatterns = /\b(my|file|folder|document|downloaded)\b/

    if (webPatterns.test(q) && !notWebPatterns.test(q)) {
      return 'web_query'
    }

    // Conversation
    const chatPatterns = /\b(hello|hi|hey|thanks|thank you|bye|help|what can you do)\b/
    if (chatPatterns.test(q)) {
      return 'conversation'
    }

    // Default to local query for ambiguous queries
    return 'local_query'
  }

  // --------------------------------------------------------------------------
  // TOOL EXECUTION
  // --------------------------------------------------------------------------

  /**
   * Execute the selected tool.
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
        case 'no_tool':
        default:
          return { tool: 'conversation', success: true, data: null, context: '' }
      }
    } catch (error) {
      console.error(`[ToolRouter] Tool execution failed:`, error)
      return {
        tool,
        success: false,
        data: error,
        context: `(Error executing ${tool})`
      }
    }
  }

  /**
   * Execute local_query using LEANN.
   */
  private async executeLocalQuery(args: ToolArguments): Promise<ToolResult> {
    const intent = args.intent || 'find'
    const target = args.target || 'files'
    const query = args.query || ''
    const searchTerms = args.search_terms || []

    // Use extracted search terms for better embedding match
    const embeddingQuery = searchTerms.length > 0 ? searchTerms.join(' ') : query

    console.log(`[ToolRouter] Local query: intent=${intent}, target=${target}`)
    console.log(`[ToolRouter] Embedding query: "${embeddingQuery}"`)

    switch (target) {
      case 'files':
        return await this.searchFiles(embeddingQuery, intent, args)

      case 'photos':
        return await this.searchPhotos(embeddingQuery)

      case 'memory':
        return await this.searchMemory(embeddingQuery)

      case 'system':
        return await this.getSystemInfo(query)

      case 'disk':
        return {
          tool: 'local_query',
          success: true,
          data: {},
          context: '\n\n## Disk Analysis\nDisk analysis not yet implemented.'
        }

      default:
        return {
          tool: 'local_query',
          success: false,
          data: null,
          context: `Unknown target: ${target}`
        }
    }
  }

  /**
   * Search files using LEANN.
   */
  private async searchFiles(
    query: string,
    intent: string,
    args: ToolArguments
  ): Promise<ToolResult> {
    // Determine search intent
    const leannIntent = intent === 'read' ? 'read' : 'find'

    console.log(`[ToolRouter] LEANN search: intent=${leannIntent}, query="${query}"`)

    const response = await leannClient.search({
      query,
      intent: leannIntent,
      folder: args.location,
      limit: 10
    })

    if (!response.success || response.results.length === 0) {
      return {
        tool: 'local_query',
        success: true,
        data: [],
        context: response.error
          ? `\n\n## File Search\nSearch error: ${response.error}`
          : '\n\n## File Search\nNo matching files found.'
      }
    }

    const results = response.results

    // Handle "open" intent - open the first matching file
    if (intent === 'open' && results.length > 0) {
      const { openFile } = await import('../tools/actions/file-opener')
      await openFile(results[0].filePath)
      return {
        tool: 'local_query',
        success: true,
        data: results[0],
        context: `\n\n## Action\nOpened: ${results[0].fileName}`
      }
    }

    // Handle "read" intent - return content chunks
    if (intent === 'read') {
      return this.formatContentResults(results)
    }

    // Default: return file list
    return this.formatFileResults(results)
  }

  /**
   * Search photos using hybrid approach: keyword first, embedding fallback.
   * Calls the Python server's /search_photos endpoint.
   */
  private async searchPhotos(query: string): Promise<ToolResult> {
    try {
      // Extract keywords from query for photo search
      const stopwords = new Set([
        'the',
        'and',
        'for',
        'with',
        'from',
        'photo',
        'picture',
        'image',
        'find',
        'show',
        'open',
        'me',
        'my',
        'of',
        'in',
        'at',
        'on'
      ])
      const keywords = query
        .toLowerCase()
        .split(/\s+/)
        .filter((w) => w.length > 2 && !stopwords.has(w))

      console.log(`[ToolRouter] Photo search: query="${query}", keywords=${keywords.join(',')}`)

      const response = await fetch(`${PYTHON_SERVER_URL}/search_photos`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, keywords, limit: 10 }),
        signal: AbortSignal.timeout(10000)
      })

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`)
      }

      const result = await response.json()

      if (!result.success || result.count === 0) {
        return {
          tool: 'local_query',
          success: true,
          data: [],
          context: result.error
            ? `\n\n## Photo Search\nError: ${result.error}`
            : '\n\n## Photo Search\nNo matching photos found.'
        }
      }

      // Format results for LLM
      const photos = result.results.slice(0, 5)
      const context =
        `\n\n## Photo Search Results (${result.method} search)\n` +
        photos
          .map((r: { file_name: string; file_path: string; keywords?: string[]; persons?: string[] }, i: number) => {
            let desc = `${i + 1}. **${r.file_name}**`
            if (r.persons && r.persons.length > 0) {
              desc += ` (${r.persons.join(', ')})`
            }
            if (r.keywords && r.keywords.length > 0) {
              desc += ` - ${r.keywords.slice(0, 3).join(', ')}`
            }
            return desc + `\n   Path: ${r.file_path}`
          })
          .join('\n')

      return {
        tool: 'local_query',
        success: true,
        data: result.results,
        context
      }
    } catch (error) {
      console.error('[ToolRouter] Photo search failed:', error)

      // Fallback to LEANN direct search
      console.log('[ToolRouter] Falling back to LEANN photo search')
      const results = await leannClient.findPhotos(query)

      if (results.length === 0) {
        return {
          tool: 'local_query',
          success: true,
          data: [],
          context: '\n\n## Photo Search\nNo matching photos found.'
        }
      }

      const context =
        `\n\n## Photo Search Results\n` +
        results
          .slice(0, 5)
          .map((r, i) => `${i + 1}. **${r.fileName}** - ${r.filePath}`)
          .join('\n')

      return { tool: 'local_query', success: true, data: results, context }
    }
  }

  /**
   * Search personal memory using LEANN.
   */
  private async searchMemory(query: string): Promise<ToolResult> {
    const results = await leannClient.searchMemory(query)

    if (results.length === 0) {
      return {
        tool: 'local_query',
        success: true,
        data: [],
        context: "\n\n## About You\nI don't know much about you yet. Tell me about yourself!"
      }
    }

    const context =
      `\n\n## What I Know About You\n` +
      results
        .slice(0, 5)
        .map((r) => `- ${r.text}`)
        .join('\n')

    return { tool: 'local_query', success: true, data: results, context }
  }

  /**
   * Get real-time system information (CPU, RAM, Disk, Processes, Battery).
   * Calls the Python server's /system_info endpoint.
   */
  private async getSystemInfo(query: string): Promise<ToolResult> {
    try {
      // Determine which sections to fetch based on query
      const queryLower = query.toLowerCase()
      const sections: string[] = []

      if (queryLower.includes('ram') || queryLower.includes('memory')) {
        sections.push('memory')
      }
      if (queryLower.includes('cpu') || queryLower.includes('processor') || queryLower.includes('slow')) {
        sections.push('cpu')
      }
      if (queryLower.includes('disk') || queryLower.includes('storage') || queryLower.includes('space')) {
        sections.push('disk')
      }
      if (queryLower.includes('process') || queryLower.includes('using') || queryLower.includes('running')) {
        sections.push('processes')
      }
      if (queryLower.includes('battery')) {
        sections.push('battery')
      }

      // If no specific sections detected, get all
      if (sections.length === 0) {
        sections.push('all')
      }

      console.log(`[ToolRouter] System info request: sections=${sections.join(',')}`)

      const response = await fetch(`${PYTHON_SERVER_URL}/system_info`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sections }),
        signal: AbortSignal.timeout(5000)
      })

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`)
      }

      const result = await response.json()

      if (!result.success) {
        return {
          tool: 'local_query',
          success: false,
          data: result,
          context: `\n\n## System Info\nError: ${result.error || 'Unknown error'}`
        }
      }

      return {
        tool: 'local_query',
        success: true,
        data: result.data,
        context: result.formatted || '\n\n## System Info\nNo system information available.'
      }
    } catch (error) {
      console.error('[ToolRouter] System info fetch failed:', error)

      // Fallback: search LEANN for indexed system facts
      console.log('[ToolRouter] Falling back to LEANN search for system info')
      const response = await leannClient.search({
        query: query || 'computer specs',
        intent: 'read',
        source: 'memory',
        limit: 10
      })

      if (!response.success || response.results.length === 0) {
        return {
          tool: 'local_query',
          success: false,
          data: [],
          context:
            '\n\n## System Info\nCould not fetch real-time system info. Python server may not be running.'
        }
      }

      const context =
        `\n\n## System Information (from memory)\n` +
        response.results
          .slice(0, 5)
          .map((r) => `- ${r.text}`)
          .join('\n')

      return { tool: 'local_query', success: true, data: response.results, context }
    }
  }

  /**
   * Format content chunk results for LLM.
   */
  private formatContentResults(results: SearchResult[]): ToolResult {
    // Group chunks by file
    const byFile = new Map<string, SearchResult[]>()
    for (const r of results) {
      const existing = byFile.get(r.filePath) || []
      existing.push(r)
      byFile.set(r.filePath, existing)
    }

    let context = '\n\n## File Content Results\n'

    for (const [filePath, chunks] of byFile) {
      const fileName = chunks[0].fileName
      context += `### ${fileName}\n`
      context += `*Path: ${filePath}*\n\n`
      context += '**Relevant content:**\n'
      context += chunks
        .slice(0, 2)
        .map((c) => `> ${c.text.trim()}`)
        .join('\n\n...\n\n')
      context += '\n\n'
    }

    return {
      tool: 'local_query',
      success: true,
      data: { results, byFile: Object.fromEntries(byFile) },
      context
    }
  }

  /**
   * Format file list results for LLM.
   */
  private formatFileResults(results: SearchResult[]): ToolResult {
    const context =
      `\n\n## File Search Results\n` +
      results
        .slice(0, 5)
        .map((r, i) => `${i + 1}. **${r.fileName}** - ${r.filePath}`)
        .join('\n')

    return { tool: 'local_query', success: true, data: results, context }
  }

  /**
   * Execute web search.
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
   * Execute multi-query (parallel search across sources).
   */
  private async executeMultiQuery(args: ToolArguments): Promise<ToolResult> {
    console.log(`[ToolRouter] Multi-query: gathering context from multiple sources`)

    const [systemResult, webResult] = await Promise.allSettled([
      this.executeLocalQuery({ ...args, intent: 'analyze', target: 'system' }),
      this.executeWebQuery(args)
    ])

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
   * Execute screenshot + vision analysis.
   */
  private async executeSee(args: ToolArguments): Promise<ToolResult> {
    console.log('[ToolRouter] Capturing screenshot for vision analysis...')

    try {
      const { screenCaptureService } = await import('../tools/actions/screen-capture')
      const screenshotBase64 = await screenCaptureService.captureScreenBase64()

      // Send to vision model (Gemma3:4b via Ollama)
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

      return {
        tool: 'see',
        success: true,
        data: { description },
        context: `\n\n## Screen Description\n${description}`
      }
    } catch (error) {
      console.error('[ToolRouter] Vision analysis failed:', error)
      return {
        tool: 'see',
        success: false,
        data: error,
        context:
          '\n\n## Screen Description\nFailed to capture or analyze screen. Ensure Ollama is running with gemma3:4b.'
      }
    }
  }

  // --------------------------------------------------------------------------
  // BACKWARDS COMPATIBILITY
  // --------------------------------------------------------------------------

  /**
   * Alias for routeAndExecute (backwards compatibility).
   * @deprecated Use routeAndExecute instead.
   */
  async routeWithTools(query: string): Promise<RouterResult> {
    return this.routeAndExecute(query)
  }
}

// ============================================================================
// EXPORTS
// ============================================================================

/** Singleton instance */
export const toolRouterService = new ToolRouterService()

// Legacy export for backwards compatibility
export const gemmaRouterService = toolRouterService
