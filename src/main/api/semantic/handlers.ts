/**
 * Semantic Search API Handlers
 *
 * Provides IPC handlers for semantic search via LEANN.
 * All indexing is handled by the Python server - these handlers just query.
 *
 * Usage (from renderer):
 *   // Search files
 *   const results = await window.api.semantic.search("project report")
 *
 *   // Open a file
 *   await window.api.semantic.open("/path/to/file.pdf")
 *
 *   // Get index status
 *   const status = await window.api.semantic.status()
 *
 * @module api/semantic/handlers
 */

import { ipcMain } from 'electron'
import { leannClient } from '../../services/leann'
import { openFile } from '../../services/tools/actions/file-opener'

export function registerSemanticHandlers(): void {
  /**
   * Search files using LEANN.
   * Returns file entries (for "find my X" queries).
   */
  ipcMain.handle('semantic:search', async (_event, query: string) => {
    const response = await leannClient.search({
      query,
      intent: 'find',
      limit: 10
    })

    if (!response.success) {
      console.error('[Semantic] Search error:', response.error)
      return []
    }

    // Transform to match previous API format
    return response.results.map((r) => ({
      path: r.filePath,
      name: r.fileName,
      score: r.score,
      folder: r.folder
    }))
  })

  /**
   * Search file contents using LEANN.
   * Returns content chunks (for "what does X say" queries).
   */
  ipcMain.handle('semantic:searchContent', async (_event, query: string) => {
    const response = await leannClient.search({
      query,
      intent: 'read',
      limit: 10
    })

    if (!response.success) {
      console.error('[Semantic] Content search error:', response.error)
      return []
    }

    return response.results.map((r) => ({
      filePath: r.filePath,
      fileName: r.fileName,
      content: r.text,
      chunkIndex: r.chunkIndex,
      score: r.score
    }))
  })

  /**
   * Search photos using LEANN.
   */
  ipcMain.handle('semantic:searchPhotos', async (_event, query: string) => {
    const results = await leannClient.findPhotos(query)
    return results.map((r) => ({
      path: r.filePath,
      name: r.fileName,
      score: r.score
    }))
  })

  /**
   * Search personal memory using LEANN.
   */
  ipcMain.handle('semantic:searchMemory', async (_event, query: string) => {
    const results = await leannClient.searchMemory(query)
    return results.map((r) => ({
      content: r.text,
      score: r.score
    }))
  })

  /**
   * Open a file using the system default application.
   */
  ipcMain.handle('semantic:open', async (_event, filePath: string) => {
    return await openFile(filePath)
  })

  /**
   * Get LEANN index status.
   */
  ipcMain.handle('semantic:status', async () => {
    const [indexStatus, serverHealthy] = await Promise.all([
      leannClient.getIndexStatus(),
      leannClient.isHealthy()
    ])

    return {
      indexed: indexStatus.indexed,
      indexPath: indexStatus.path,
      serverRunning: serverHealthy
    }
  })

  /**
   * Trigger reindex via Python server.
   * Note: This requires the Python server to support incremental indexing.
   * For now, returns instructions to run the indexer manually.
   */
  ipcMain.handle('semantic:reindex', async () => {
    // Check if server is running
    const healthy = await leannClient.isHealthy()

    if (!healthy) {
      return {
        success: false,
        message: 'Python server not running. Start it with: python python/function_gemma_server.py'
      }
    }

    // TODO: Add /index endpoint to Python server for programmatic indexing
    return {
      success: false,
      message: 'Manual indexing required. Run: python python/leann_indexer.py --force'
    }
  })

  // ============================================================================
  // LEGACY HANDLERS (for backwards compatibility)
  // These return helpful messages directing users to use Python indexer.
  // ============================================================================

  ipcMain.handle('knowledge:indexSystem', async () => {
    return {
      success: false,
      message: 'System indexing moved to Python. Run: python python/leann_indexer.py'
    }
  })

  ipcMain.handle('knowledge:indexPhotos', async () => {
    return {
      success: false,
      message: 'Photo indexing moved to Python. Run: python python/leann_indexer.py'
    }
  })

  ipcMain.handle('knowledge:initPersonal', async () => {
    return {
      success: false,
      message: 'Personal memory moved to Python. Run: python python/leann_indexer.py'
    }
  })

  ipcMain.handle('knowledge:search', async (_event, query: string) => {
    // Redirect to LEANN search
    const response = await leannClient.search({
      query,
      intent: 'read',
      limit: 10
    })

    return {
      items: response.results.map((r) => ({
        content: r.text,
        source: r.source,
        score: r.score
      }))
    }
  })

  ipcMain.handle('knowledge:stats', async () => {
    const status = await leannClient.getIndexStatus()
    return {
      indexed: status.indexed,
      path: status.path,
      message: 'Stats available via Python. Check: python python/leann_indexer.py --status'
    }
  })

  ipcMain.handle('knowledge:reindexAll', async () => {
    return {
      success: false,
      message: 'Full reindex moved to Python. Run: python python/leann_indexer.py --force'
    }
  })

  ipcMain.handle('knowledge:learn', async (_event, fact: string) => {
    // TODO: Add learning endpoint to Python server
    console.log('[Semantic] Learning fact (not yet implemented):', fact)
    return {
      success: false,
      message: 'Learning new facts not yet implemented in LEANN. Coming soon!'
    }
  })
}
