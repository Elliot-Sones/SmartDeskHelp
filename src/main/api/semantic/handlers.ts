import { ipcMain } from 'electron'
import { join } from 'path'
import { homedir } from 'os'
import { indexerService } from '../../services/indexing/file-indexer'
import { fileSearchService } from '../../services/tools/helpers/file-search'
import { openFile } from '../../services/tools/actions/file-opener'
import { domainRouterService } from '../../services/tools/helpers/domain-router'
import { systemScraperService } from '../../services/tools/helpers/system-info'
import { photoIndexerService } from '../../services/tools/helpers/photo-metadata'
import { personalMemoryService } from '../../services/tools/helpers/personal-memory'
import { knowledgeStoreService } from '../../services/tools/helpers/knowledge-store'

export function registerSemanticHandlers() {
  // Trigger manual reindex
  ipcMain.handle('semantic:reindex', async () => {
    const desktopPath = join(homedir(), 'Desktop')
    await indexerService.indexFromRoot(desktopPath)
    return { success: true }
  })

  // Search files semantically
  ipcMain.handle('semantic:search', async (_event, query: string) => {
    return await fileSearchService.findRelevantFiles(query)
  })

  // Open a file
  ipcMain.handle('semantic:open', async (_event, filePath: string) => {
    return await openFile(filePath)
  })

  // === KNOWLEDGE SYSTEM HANDLERS ===

  // Index system information (RAM, apps, etc.)
  ipcMain.handle('knowledge:indexSystem', async () => {
    await systemScraperService.scrapeAndIndex()
    return { success: true }
  })

  // Index photos from default directories
  ipcMain.handle('knowledge:indexPhotos', async (_event, directories?: string[]) => {
    await photoIndexerService.indexPhotos(directories)
    return { success: true }
  })

  // Initialize personal memory
  ipcMain.handle('knowledge:initPersonal', async () => {
    await personalMemoryService.initialize()
    return { success: true }
  })

  // Learn a personal fact
  ipcMain.handle('knowledge:learn', async (_event, fact: string) => {
    await personalMemoryService.learn(fact, 'user')
    return { success: true }
  })

  // Query knowledge (uses domain router)
  ipcMain.handle('knowledge:search', async (_event, query: string) => {
    return await domainRouterService.route(query)
  })

  // Get knowledge tree stats for debugging
  ipcMain.handle('knowledge:stats', async () => {
    const [photos, computer, personal] = await Promise.all([
      knowledgeStoreService.getTreeStats('photos'),
      knowledgeStoreService.getTreeStats('computer'),
      knowledgeStoreService.getTreeStats('personal')
    ])
    return { photos, computer, personal }
  })

  // Full reindex: files + knowledge
  ipcMain.handle('knowledge:reindexAll', async () => {
    const desktopPath = join(homedir(), 'Desktop')
    
    // Index files
    await indexerService.indexFromRoot(desktopPath)
    
    // Index knowledge domains
    await systemScraperService.scrapeAndIndex()
    await photoIndexerService.indexPhotos()
    await personalMemoryService.initialize()
    
    return { success: true }
  })
}

