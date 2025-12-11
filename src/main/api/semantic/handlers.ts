import { ipcMain } from 'electron'
import { join } from 'path'
import { homedir } from 'os'
import { indexerService } from '../../services/indexer'
import { routerService } from '../../services/router'
import { openFile } from '../../services/file-actions'
import { domainRouterService } from '../../services/domain-router'
import { systemScraperService } from '../../services/system-scraper'
import { photoIndexerService } from '../../services/photo-indexer'
import { personalMemoryService } from '../../services/personal-memory'
import { knowledgeTreeService } from '../../services/knowledge-tree'

export function registerSemanticHandlers() {
  // Trigger manual reindex
  ipcMain.handle('semantic:reindex', async () => {
    const desktopPath = join(homedir(), 'Desktop')
    await indexerService.indexFromRoot(desktopPath)
    return { success: true }
  })

  // Search files semantically
  ipcMain.handle('semantic:search', async (_event, query: string) => {
    return await routerService.findRelevantFiles(query)
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
      knowledgeTreeService.getTreeStats('photos'),
      knowledgeTreeService.getTreeStats('computer'),
      knowledgeTreeService.getTreeStats('personal')
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

