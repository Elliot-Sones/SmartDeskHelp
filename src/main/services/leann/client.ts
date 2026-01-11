/**
 * LEANN Client - TypeScript client for the LEANN vector search service.
 *
 * LEANN (Lightweight Embeddings for Approximate Nearest Neighbors) provides
 * fast semantic search over indexed files, photos, and personal memory.
 *
 * Architecture:
 *   TypeScript (this client) → HTTP → Python Server → LEANN Index
 *
 * The Python server (python/function_gemma_server.py) handles:
 *   - /search: Vector similarity search with metadata filtering
 *   - /route: Query routing via FunctionGemma
 *   - /index_status: Check if index exists
 *
 * @see python/leann_search.py for search implementation
 * @see python/leann_indexer.py for index building
 */

// ============================================================================
// CONFIGURATION
// ============================================================================

const LEANN_SERVER_URL = 'http://localhost:8765'
const DEFAULT_TIMEOUT_MS = 5000

// ============================================================================
// TYPES
// ============================================================================

/**
 * Search intent determines what type of results to return.
 * - "find": Returns file entries (for "find my resume" queries)
 * - "read": Returns content chunks (for "what does my resume say" queries)
 * - "open": Same as "find", but indicates user wants to open the file
 */
export type SearchIntent = 'find' | 'read' | 'open'

/**
 * Data source filter for narrowing search scope.
 * - "desktop": Files from ~/Desktop and subdirectories
 * - "photos": Image files from ~/Pictures, ~/Photos, etc.
 * - "memory": Personal facts learned from conversations
 */
export type DataSource = 'desktop' | 'photos' | 'memory'

/**
 * Parameters for LEANN search requests.
 */
export interface SearchParams {
  /** The search query (natural language or keywords) */
  query: string

  /** What type of results to return (default: "find") */
  intent?: SearchIntent

  /** Filter by data source (default: all sources) */
  source?: DataSource

  /** Filter by folder path prefix (e.g., "Desktop/Projects") */
  folder?: string

  /** Maximum number of results (default: 10) */
  limit?: number
}

/**
 * A single search result from LEANN.
 */
export interface SearchResult {
  /** The searchable text (filename description or content chunk) */
  text: string

  /** Similarity score (0-1, higher is better) */
  score: number

  /** Entry type: "file" for find intent, "chunk" for read intent */
  type: 'file' | 'chunk'

  /** Data source this result came from */
  source: DataSource

  /** Full path to the file (for opening) */
  filePath: string

  /** Just the filename (for display) */
  fileName: string

  /** Folder path relative to home (for display) */
  folder: string

  /** Chunk index within the file (only for type="chunk") */
  chunkIndex: number | null
}

/**
 * Response from LEANN search endpoint.
 */
export interface SearchResponse {
  /** Whether the search succeeded */
  success: boolean

  /** Search results (empty array if error) */
  results: SearchResult[]

  /** Error message if search failed */
  error?: string
}

/**
 * LEANN index status.
 */
export interface IndexStatus {
  /** Whether the index file exists */
  indexed: boolean

  /** Path to the index file (null if not indexed) */
  path: string | null
}

// ============================================================================
// CLIENT CLASS
// ============================================================================

/**
 * Client for interacting with the LEANN search service.
 *
 * Usage:
 *   const client = new LeannClient()
 *
 *   // Find files
 *   const files = await client.findFiles("project report")
 *
 *   // Read content
 *   const content = await client.readContent("what does my resume say")
 *
 *   // Search photos
 *   const photos = await client.findPhotos("vacation beach")
 *
 *   // Search personal memory
 *   const memories = await client.searchMemory("my favorite")
 */
export class LeannClient {
  private serverUrl: string
  private timeoutMs: number

  constructor(serverUrl = LEANN_SERVER_URL, timeoutMs = DEFAULT_TIMEOUT_MS) {
    this.serverUrl = serverUrl
    this.timeoutMs = timeoutMs
  }

  // --------------------------------------------------------------------------
  // CORE SEARCH METHOD
  // --------------------------------------------------------------------------

  /**
   * Search the LEANN index with full parameter control.
   *
   * @param params - Search parameters
   * @returns Search response with results or error
   */
  async search(params: SearchParams): Promise<SearchResponse> {
    const { query, intent = 'find', source, folder, limit = 10 } = params

    try {
      const response = await fetch(`${this.serverUrl}/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          intent,
          source,
          folder,
          top_k: limit
        }),
        signal: AbortSignal.timeout(this.timeoutMs)
      })

      if (!response.ok) {
        return {
          success: false,
          results: [],
          error: `Server error: ${response.status} ${response.statusText}`
        }
      }

      const data = await response.json()

      if (data.error) {
        return {
          success: false,
          results: [],
          error: data.error
        }
      }

      // Transform snake_case to camelCase
      const results: SearchResult[] = (data.results || []).map(
        (r: Record<string, unknown>) => ({
          text: r.text as string,
          score: r.score as number,
          type: r.type as 'file' | 'chunk',
          source: r.source as DataSource,
          filePath: r.file_path as string,
          fileName: r.file_name as string,
          folder: r.folder as string,
          chunkIndex: r.chunk_index as number | null
        })
      )

      return { success: true, results }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error'
      return {
        success: false,
        results: [],
        error: `Search failed: ${message}`
      }
    }
  }

  // --------------------------------------------------------------------------
  // CONVENIENCE METHODS
  // --------------------------------------------------------------------------

  /**
   * Find files matching a query.
   * Use this for "find my resume" type queries.
   */
  async findFiles(query: string, limit = 10): Promise<SearchResult[]> {
    const response = await this.search({ query, intent: 'find', limit })
    return response.results
  }

  /**
   * Find files and return the response with success/error info.
   */
  async findFilesWithStatus(query: string, limit = 10): Promise<SearchResponse> {
    return this.search({ query, intent: 'find', limit })
  }

  /**
   * Search content chunks to answer questions about file contents.
   * Use this for "what does my resume say about X" type queries.
   */
  async readContent(query: string, limit = 10): Promise<SearchResult[]> {
    const response = await this.search({ query, intent: 'read', limit })
    return response.results
  }

  /**
   * Find photos matching a query.
   */
  async findPhotos(query: string, limit = 10): Promise<SearchResult[]> {
    const response = await this.search({
      query,
      intent: 'find',
      source: 'photos',
      limit
    })
    return response.results
  }

  /**
   * Search personal memory facts.
   */
  async searchMemory(query: string, limit = 10): Promise<SearchResult[]> {
    const response = await this.search({
      query,
      intent: 'read',
      source: 'memory',
      limit
    })
    return response.results
  }

  /**
   * Find files within a specific folder.
   */
  async findInFolder(query: string, folder: string, limit = 10): Promise<SearchResult[]> {
    const response = await this.search({ query, intent: 'find', folder, limit })
    return response.results
  }

  // --------------------------------------------------------------------------
  // STATUS METHODS
  // --------------------------------------------------------------------------

  /**
   * Check if the LEANN index exists.
   */
  async getIndexStatus(): Promise<IndexStatus> {
    try {
      const response = await fetch(`${this.serverUrl}/index_status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
        signal: AbortSignal.timeout(this.timeoutMs)
      })

      if (!response.ok) {
        return { indexed: false, path: null }
      }

      const data = await response.json()
      return {
        indexed: data.indexed ?? false,
        path: data.path ?? null
      }
    } catch {
      return { indexed: false, path: null }
    }
  }

  /**
   * Check if the Python server is running and healthy.
   */
  async isHealthy(): Promise<boolean> {
    try {
      const response = await fetch(`${this.serverUrl}/health`, {
        method: 'GET',
        signal: AbortSignal.timeout(2000)
      })
      return response.ok
    } catch {
      return false
    }
  }
}

// ============================================================================
// SINGLETON INSTANCE
// ============================================================================

/**
 * Default LEANN client instance.
 * Use this for most cases instead of creating new instances.
 */
export const leannClient = new LeannClient()
