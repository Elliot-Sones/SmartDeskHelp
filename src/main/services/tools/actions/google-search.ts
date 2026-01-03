/**
 * MCP Google Search Service
 * Provides web search capabilities using Google Custom Search API
 */

// Google Custom Search API endpoint
const GOOGLE_SEARCH_API = 'https://www.googleapis.com/customsearch/v1'

interface SearchResult {
  title: string
  link: string
  snippet: string
}

interface GoogleSearchResponse {
  items?: Array<{
    title: string
    link: string
    snippet: string
  }>
  error?: {
    message: string
  }
}

class McpGoogleSearchService {
  private apiKey: string | null = null
  private searchEngineId: string | null = null

  /**
   * Initialize with API credentials
   * Call this on app startup with stored credentials
   */
  initialize(apiKey: string, searchEngineId: string): void {
    this.apiKey = apiKey
    this.searchEngineId = searchEngineId
    console.log('[MCP-GoogleSearch] Initialized with API key')
  }

  /**
   * Check if the service is configured
   */
  isConfigured(): boolean {
    return Boolean(this.apiKey && this.searchEngineId)
  }

  /**
   * Perform a web search
   * Returns top results with title, link, and snippet
   */
  async search(query: string, numResults = 5): Promise<SearchResult[]> {
    if (!this.apiKey || !this.searchEngineId) {
      console.log('[MCP-GoogleSearch] Not configured - returning mock results')
      return this.getMockResults(query)
    }

    try {
      const params = new URLSearchParams({
        key: this.apiKey,
        cx: this.searchEngineId,
        q: query,
        num: String(Math.min(numResults, 10))
      })

      const response = await fetch(`${GOOGLE_SEARCH_API}?${params}`)
      const data = (await response.json()) as GoogleSearchResponse

      if (data.error) {
        console.error('[MCP-GoogleSearch] API error:', data.error.message)
        return this.getMockResults(query)
      }

      if (!data.items || data.items.length === 0) {
        return []
      }

      return data.items.slice(0, numResults).map((item) => ({
        title: item.title,
        link: item.link,
        snippet: item.snippet
      }))
    } catch (error) {
      console.error('[MCP-GoogleSearch] Fetch error:', error)
      return this.getMockResults(query)
    }
  }

  /**
   * Get mock results when API is not configured
   * This allows the system to work without credentials during development
   */
  private getMockResults(query: string): SearchResult[] {
    return [
      {
        title: `Web search for: ${query}`,
        link: `https://www.google.com/search?q=${encodeURIComponent(query)}`,
        snippet: `MCP Google Search is not configured. To enable real web search, add your Google Custom Search API key and Search Engine ID in settings. For now, showing placeholder results for: "${query}"`
      }
    ]
  }

  /**
   * Format search results for LLM consumption
   */
  formatForLLM(results: SearchResult[]): string {
    if (results.length === 0) {
      return 'No web search results found.'
    }

    return results
      .map(
        (r, i) =>
          `${i + 1}. **${r.title}**\n   ${r.snippet}\n   Source: ${r.link}`
      )
      .join('\n\n')
  }
}

export const googleSearchService = new McpGoogleSearchService()
