import { readdir } from 'fs/promises'
import { join, basename, extname } from 'path'
import { db } from '../db'
import { semanticFolders, semanticFiles } from '../db/schema'
import { embeddingService } from './embedding'
import { contentExtractorService } from './content-extractor'
import { eq } from 'drizzle-orm'

const SKIP_PATTERNS = ['node_modules', '.git', '.cache', '__pycache__', '.DS_Store']
const MAX_DEPTH = 10

// Result of indexing a folder (passed to parent)
interface FolderResult {
  id: number
  embedding: Float32Array
}

// Collected file info before batch processing
interface FileInfo {
  path: string
  name: string
  relativePath: string
  extension: string
}

class IndexerService {
  /**
   * Main entry point - checks if reindexing is needed
   */
  async indexFromRoot(rootPath: string): Promise<void> {
    console.log(`[Indexer] Checking if reindex is needed...`)

    // Check if DB is empty
    const existingFolders = await db.select().from(semanticFolders)
    if (existingFolders.length === 0) {
      console.log(`[Indexer] Database is empty, performing full index`)
      await this.performFullIndex(rootPath)
      return
    }

    // Quick scan of current file paths
    console.log(`[Indexer] Comparing current files with indexed files...`)
    const currentPaths = new Set<string>()
    await this.quickScanPaths(rootPath, 0, currentPaths)

    // Get stored paths from DB
    const storedFiles = await db.select({ path: semanticFiles.path }).from(semanticFiles)
    const storedPaths = new Set(storedFiles.map((f) => f.path))

    // Find differences
    const added = [...currentPaths].filter((p) => !storedPaths.has(p))
    const removed = [...storedPaths].filter((p) => !currentPaths.has(p))

    console.log(`[Indexer] Found ${added.length} new files, ${removed.length} removed files`)

    if (added.length === 0 && removed.length === 0) {
      console.log(`[Indexer] No changes detected, using cached index (${storedPaths.size} files)`)
      return
    }

    // If changes detected, perform full reindex
    console.log(`[Indexer] Changes detected, performing full reindex`)
    await this.performFullIndex(rootPath)
  }

  /**
   * Quick scan of all file paths (no embedding)
   */
  private async quickScanPaths(folderPath: string, depth: number, paths: Set<string>): Promise<void> {
    if (depth > MAX_DEPTH) return

    const folderName = basename(folderPath)
    if (SKIP_PATTERNS.some((p) => folderName === p || folderName.startsWith('.'))) {
      return
    }

    try {
      const entries = await readdir(folderPath, { withFileTypes: true })

      for (const entry of entries) {
        if (entry.isFile()) {
          if (!entry.name.startsWith('.') && !entry.name.startsWith('~$')) {
            paths.add(join(folderPath, entry.name))
          }
        } else if (entry.isDirectory()) {
          await this.quickScanPaths(join(folderPath, entry.name), depth + 1, paths)
        }
      }
    } catch {
      // Skip folders we can't read
    }
  }

  /**
   * Perform full indexing using bottom-up single-phase approach
   */
  private async performFullIndex(rootPath: string): Promise<void> {
    const startTime = Date.now()
    console.log(`[Indexer] Starting bottom-up index from: ${rootPath}`)

    // Clear existing data
    await db.delete(semanticFiles)
    await db.delete(semanticFolders)

    // Single-phase bottom-up recursive indexing
    console.log(`[Indexer] Indexing with content signatures...`)
    await this.indexFolderRecursive(rootPath, 0, null)

    const folderCount = await db.select().from(semanticFolders)
    const fileCount = await db.select().from(semanticFiles)
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1)
    console.log(`[Indexer] Indexed ${folderCount.length} folders, ${fileCount.length} files in ${elapsed}s`)
  }

  /**
   * Bottom-up recursive folder indexing
   * Post-order traversal: children are indexed before parent
   * Returns the folder result so parent can aggregate embeddings
   */
  private async indexFolderRecursive(
    folderPath: string,
    depth: number,
    parentId: number | null
  ): Promise<FolderResult | null> {
    if (depth > MAX_DEPTH) return null

    const folderName = basename(folderPath)
    if (SKIP_PATTERNS.some((p) => folderName === p || folderName.startsWith('.'))) {
      return null
    }

    try {
      const entries = await readdir(folderPath, { withFileTypes: true })
      const fileEntries = entries.filter((e) => e.isFile() && !e.name.startsWith('.') && !e.name.startsWith('~$'))
      const subdirEntries = entries.filter((e) => e.isDirectory())

      // 1. RECURSE INTO CHILDREN FIRST (post-order traversal)
      const childResults: FolderResult[] = []
      for (const subdir of subdirEntries) {
        const result = await this.indexFolderRecursive(
          join(folderPath, subdir.name),
          depth + 1,
          null // parentId updated after we insert this folder
        )
        if (result) {
          childResults.push(result)
        }
      }

      // 2. Collect file info
      const fileInfos: FileInfo[] = fileEntries.map((entry) => {
        const filePath = join(folderPath, entry.name)
        const desktopIndex = folderPath.indexOf('Desktop')
        const relativePath =
          desktopIndex !== -1
            ? folderPath.slice(desktopIndex + 'Desktop/'.length) + '/' + entry.name
            : folderName + '/' + entry.name

        return {
          path: filePath,
          name: entry.name,
          relativePath,
          extension: extname(entry.name).slice(1)
        }
      })

      // 3. Extract content signatures (batch)
      const contentSignatures = await contentExtractorService.extractBatch(
        fileInfos.map((f) => f.path)
      )

      // 4. Embed filenames/paths (batch)
      const filenameTexts = fileInfos.map((f) => f.relativePath)
      const filenameEmbeddings = filenameTexts.length > 0
        ? await embeddingService.embedBatch(filenameTexts)
        : []

      // 5. Aggregate embeddings for folder
      // Combine: file content embeddings + child folder embeddings
      const allEmbeddings: Float32Array[] = []

      // Add file embeddings (prefer content, fallback to filename)
      for (let i = 0; i < fileInfos.length; i++) {
        const contentSig = contentSignatures[i]
        if (contentSig) {
          allEmbeddings.push(contentSig.embedding)
        } else if (filenameEmbeddings[i]) {
          allEmbeddings.push(filenameEmbeddings[i])
        }
      }

      // Add child folder embeddings
      for (const child of childResults) {
        allEmbeddings.push(child.embedding)
      }

      // Mean-pool to create folder embedding
      const folderEmbedding = embeddingService.meanPool(allEmbeddings)

      // 6. Build summary for folder
      const summary = this.buildSummary(folderName, fileInfos, childResults.length)

      // 7. INSERT FOLDER TO DB
      const [savedFolder] = await db
        .insert(semanticFolders)
        .values({
          path: folderPath,
          parentId,
          name: folderName,
          depth,
          summary,
          embedding: embeddingService.serializeEmbedding(folderEmbedding),
          fileCount: fileInfos.length,
          indexedAt: new Date()
        })
        .returning()

      // 8. INSERT FILES TO DB
      for (let i = 0; i < fileInfos.length; i++) {
        const file = fileInfos[i]
        const contentSig = contentSignatures[i]
        const filenameEmb = filenameEmbeddings[i]

        await db.insert(semanticFiles).values({
          folderId: savedFolder.id,
          path: file.path,
          name: file.name,
          embedding: filenameEmb ? embeddingService.serializeEmbedding(filenameEmb) : null,
          contentSignature: contentSig?.signature || null,
          contentEmbedding: contentSig?.embedding
            ? embeddingService.serializeEmbedding(contentSig.embedding)
            : null,
          extension: file.extension,
          indexedAt: new Date()
        })
      }

      // 9. UPDATE CHILD FOLDERS with correct parentId
      for (const child of childResults) {
        await db
          .update(semanticFolders)
          .set({ parentId: savedFolder.id })
          .where(eq(semanticFolders.id, child.id))
      }

      // Log progress
      if (depth <= 2) {
        console.log(`[Indexer] Indexed: ${folderName} (${fileInfos.length} files, ${childResults.length} subfolders)`)
      }

      return { id: savedFolder.id, embedding: folderEmbedding }
    } catch (error) {
      console.error(`[Indexer] Error indexing ${folderPath}:`, error)
      return null
    }
  }

  /**
   * Build a summary string for a folder
   */
  private buildSummary(folderName: string, files: FileInfo[], childCount: number): string {
    const parts: string[] = [`${folderName} folder`]

    if (files.length > 0) {
      const sampleFiles = files.slice(0, 5).map((f) => f.name)
      parts.push(`containing files: ${sampleFiles.join(', ')}`)
      if (files.length > 5) {
        parts.push(`and ${files.length - 5} more`)
      }
    }

    if (childCount > 0) {
      parts.push(`with ${childCount} subfolder${childCount > 1 ? 's' : ''}`)
    }

    return parts.join(' ')
  }
}

export const indexerService = new IndexerService()
