import { readdir, stat } from 'fs/promises'
import { join, basename, extname, dirname } from 'path'
import { db } from '../../db'
import { semanticFolders, semanticFiles, semanticChunks } from '../../db/schema'
import { embeddingService } from './embedding'
import { contentExtractorService } from '../tools/helpers/content-extractor'
import { eq } from 'drizzle-orm'

// LAZY CHUNKING: Chunks are NOT generated during indexing.
// They are generated on-demand during search and cached.
// This makes initial indexing fast (seconds instead of minutes).

const SKIP_PATTERNS = [
  // Version control & caches
  'node_modules', '.git', '.cache', '__pycache__', '.DS_Store',
  // Python environments
  'venv', '.venv', 'env', '.env', 'virtualenv', 'site-packages',
  // Build outputs
  'dist', 'build', 'out', '.next', '.nuxt', '.output',
  // IDE & tools
  '.idea', '.vscode', '.gradle', '.m2',
  // Package manager caches
  '.pnpm', '.npm', '.yarn', 'vendor',
  // Other
  'coverage', '.turbo', '.parcel-cache', 'tmp', 'temp'
]
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
  mtime?: Date
}

// File stats for change detection
interface FileStats {
  path: string
  mtime: number
  size: number
}

class IndexerService {
  /**
   * Main entry point - performs incremental indexing
   */
  async indexFromRoot(rootPath: string): Promise<void> {
    const startTime = Date.now()
    console.log(`[Indexer] Starting incremental check...`)

    // Check if DB is empty
    const existingFolders = await db.select().from(semanticFolders)
    if (existingFolders.length === 0) {
      console.log(`[Indexer] Database is empty, performing full index`)
      await this.performFullIndex(rootPath)
      return
    }
    // Note: Chunks are generated lazily during search, not during indexing

    // Scan current file stats (path + mtime + size)
    console.log(`[Indexer] Scanning file system...`)
    const currentFiles = new Map<string, FileStats>()
    await this.quickScanStats(rootPath, 0, currentFiles)

    // Get stored file info from DB
    const storedFiles = await db
      .select({
        path: semanticFiles.path,
        lastModified: semanticFiles.lastModified
      })
      .from(semanticFiles)

    const storedMap = new Map(storedFiles.map((f) => [f.path, f.lastModified?.getTime() || 0]))

    // Find changes
    const toAdd: string[] = []
    const toUpdate: string[] = []
    const toRemove: string[] = []

    for (const [path, stats] of currentFiles) {
      const storedMtime = storedMap.get(path)
      if (storedMtime === undefined) {
        toAdd.push(path)
      } else {
        // Truncate to seconds to avoid precision issues with DB serialization
        const storedSeconds = Math.floor(storedMtime / 1000)
        const currentSeconds = Math.floor(stats.mtime / 1000)
        if (storedSeconds !== currentSeconds) {
          toUpdate.push(path)
        }
      }
    }

    for (const [path] of storedMap) {
      if (!currentFiles.has(path)) {
        toRemove.push(path)
      }
    }

    const changeCount = toAdd.length + toUpdate.length + toRemove.length
    console.log(`[Indexer] Changes: ${toAdd.length} new, ${toUpdate.length} modified, ${toRemove.length} removed`)

    if (changeCount === 0) {
      const elapsed = ((Date.now() - startTime) / 1000).toFixed(1)
      console.log(`[Indexer] No changes, using cached index (${storedMap.size} files) [${elapsed}s]`)
      return
    }

    // If too many changes (>50%), just do full reindex (more efficient)
    if (changeCount > storedMap.size * 0.5 || storedMap.size === 0) {
      console.log(`[Indexer] Many changes detected, performing full reindex`)
      await this.performFullIndex(rootPath)
      return
    }

    // Incremental update
    await this.processIncrementalChanges(toAdd, toUpdate, toRemove, rootPath)

    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1)
    console.log(`[Indexer] Incremental update complete [${elapsed}s]`)
  }

  /**
   * Quick scan of file stats (mtime, size) for change detection
   */
  private async quickScanStats(
    folderPath: string,
    depth: number,
    stats: Map<string, FileStats>
  ): Promise<void> {
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
            const filePath = join(folderPath, entry.name)
            try {
              const fileStat = await stat(filePath)
              stats.set(filePath, {
                path: filePath,
                mtime: fileStat.mtimeMs,
                size: fileStat.size
              })
            } catch {
              // Skip files we can't stat
            }
          }
        } else if (entry.isDirectory()) {
          await this.quickScanStats(join(folderPath, entry.name), depth + 1, stats)
        }
      }
    } catch {
      // Skip folders we can't read
    }
  }

  /**
   * Process incremental file changes
   */
  private async processIncrementalChanges(
    toAdd: string[],
    toUpdate: string[],
    toRemove: string[],
    rootPath: string
  ): Promise<void> {
    // 1. Remove deleted files and their chunks
    if (toRemove.length > 0) {
      console.log(`[Indexer] Removing ${toRemove.length} deleted files...`)
      for (const path of toRemove) {
        // Get file ID first to delete chunks
        const [file] = await db.select({ id: semanticFiles.id }).from(semanticFiles).where(eq(semanticFiles.path, path))
        if (file) {
          await db.delete(semanticChunks).where(eq(semanticChunks.fileId, file.id))
        }
        await db.delete(semanticFiles).where(eq(semanticFiles.path, path))
      }
    }

    // 2. Remove modified files and their chunks (will re-add with updated data)
    if (toUpdate.length > 0) {
      console.log(`[Indexer] Updating ${toUpdate.length} modified files...`)
      for (const path of toUpdate) {
        // Get file ID first to delete chunks
        const [file] = await db.select({ id: semanticFiles.id }).from(semanticFiles).where(eq(semanticFiles.path, path))
        if (file) {
          await db.delete(semanticChunks).where(eq(semanticChunks.fileId, file.id))
        }
        await db.delete(semanticFiles).where(eq(semanticFiles.path, path))
      }
    }

    // 3. Process new and updated files
    const filesToProcess = [...toAdd, ...toUpdate]
    if (filesToProcess.length > 0) {
      console.log(`[Indexer] Indexing ${filesToProcess.length} files...`)
      await this.indexFilesBatch(filesToProcess, rootPath)
    }

    // 4. Update affected folder embeddings
    const affectedFolders = new Set<string>()
    for (const path of [...toAdd, ...toUpdate, ...toRemove]) {
      affectedFolders.add(dirname(path))
    }
    await this.updateFolderEmbeddings(affectedFolders)
  }

  /**
   * Index a batch of files (used for incremental updates)
   * LAZY CHUNKING: Only stores metadata + signature, chunks generated on search
   */
  private async indexFilesBatch(filePaths: string[], rootPath: string): Promise<void> {
    // Get or create parent folders
    const folderCache = new Map<string, number>()

    for (const filePath of filePaths) {
      const folderPath = dirname(filePath)
      let folderId = folderCache.get(folderPath)

      if (folderId === undefined) {
        // Check if folder exists
        const existing = await db
          .select({ id: semanticFolders.id })
          .from(semanticFolders)
          .where(eq(semanticFolders.path, folderPath))

        if (existing.length > 0) {
          folderId = existing[0].id
        } else {
          // Create folder (simplified - just basic info)
          const [newFolder] = await db
            .insert(semanticFolders)
            .values({
              path: folderPath,
              name: basename(folderPath),
              depth: folderPath.split('/').length - rootPath.split('/').length,
              indexedAt: new Date()
            })
            .returning()
          folderId = newFolder.id
        }
        folderCache.set(folderPath, folderId)
      }

      // Index the file
      const fileName = basename(filePath)
      const ext = extname(fileName).slice(1)
      const desktopIndex = folderPath.indexOf('Desktop')
      const relativePath =
        desktopIndex !== -1
          ? folderPath.slice(desktopIndex + 'Desktop/'.length) + '/' + fileName
          : basename(folderPath) + '/' + fileName

      // Get file stats for mtime
      let mtime: Date | undefined
      try {
        const fileStat = await stat(filePath)
        mtime = fileStat.mtime
      } catch {
        // Use current time as fallback
        mtime = new Date()
      }

      // Extract content signature only (no chunking - that's lazy)
      const contentSig = await contentExtractorService.extractSignature(filePath)
      const [filenameEmb] = await embeddingService.embedBatch([relativePath])

      // Insert file record (chunkCount = 0, chunks generated lazily)
      await db.insert(semanticFiles).values({
        folderId,
        path: filePath,
        name: fileName,
        embedding: filenameEmb ? embeddingService.serializeEmbedding(filenameEmb) : null,
        contentSignature: contentSig?.signature || null,
        contentEmbedding: contentSig?.embedding
          ? embeddingService.serializeEmbedding(contentSig.embedding)
          : null,
        extension: ext,
        indexedAt: new Date(),
        lastModified: mtime,
        chunkCount: 0 // Chunks generated lazily during search
      })
    }
  }

  /**
   * Update folder embeddings after incremental changes
   */
  private async updateFolderEmbeddings(folderPaths: Set<string>): Promise<void> {
    for (const folderPath of folderPaths) {
      // Get all files in this folder
      const files = await db
        .select({ embedding: semanticFiles.embedding, contentEmbedding: semanticFiles.contentEmbedding })
        .from(semanticFiles)
        .where(eq(semanticFiles.path, folderPath))

      // Get folder record
      const [folder] = await db
        .select()
        .from(semanticFolders)
        .where(eq(semanticFolders.path, folderPath))

      if (!folder) continue

      // Compute new embedding
      const embeddings: Float32Array[] = []
      for (const file of files) {
        if (file.contentEmbedding) {
          embeddings.push(embeddingService.deserializeEmbedding(file.contentEmbedding as Buffer))
        } else if (file.embedding) {
          embeddings.push(embeddingService.deserializeEmbedding(file.embedding as Buffer))
        }
      }

      if (embeddings.length > 0) {
        const newEmbedding = embeddingService.meanPool(embeddings)
        await db
          .update(semanticFolders)
          .set({ embedding: embeddingService.serializeEmbedding(newEmbedding) })
          .where(eq(semanticFolders.id, folder.id))
      }
    }
  }

  // Track progress for logging
  private filesProcessed = 0

  /**
   * Perform full indexing using bottom-up single-phase approach
   * LAZY CHUNKING: Only metadata is stored, chunks generated on-demand during search
   */
  private async performFullIndex(rootPath: string): Promise<void> {
    const startTime = Date.now()
    console.log(`[Indexer] Starting fast index from: ${rootPath}`)
    console.log(`[Indexer] Note: Using lazy chunking (chunks generated on search)`)

    // Reset progress counter
    this.filesProcessed = 0

    // Clear existing data (chunks first due to foreign key dependency)
    await db.delete(semanticChunks)
    await db.delete(semanticFiles)
    await db.delete(semanticFolders)

    // Single-phase bottom-up recursive indexing (no chunking)
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

      // 2. Collect file info with mtime
      const fileInfos: FileInfo[] = []
      for (const entry of fileEntries) {
        const filePath = join(folderPath, entry.name)
        const desktopIndex = folderPath.indexOf('Desktop')
        const relativePath =
          desktopIndex !== -1
            ? folderPath.slice(desktopIndex + 'Desktop/'.length) + '/' + entry.name
            : folderName + '/' + entry.name

        let mtime: Date | undefined
        try {
          const fileStat = await stat(filePath)
          mtime = fileStat.mtime
        } catch {
          mtime = new Date()
        }

        fileInfos.push({
          path: filePath,
          name: entry.name,
          relativePath,
          extension: extname(entry.name).slice(1),
          mtime
        })
      }

      // 3. Extract content signatures (NOT full chunking - that's lazy)
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

      // Add file embeddings (prefer content signature, fallback to filename)
      for (let i = 0; i < fileInfos.length; i++) {
        const sig = contentSignatures[i]
        if (sig && sig.embedding) {
          allEmbeddings.push(sig.embedding)
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

      // 8. INSERT FILES TO DB (no chunks - they're generated lazily)
      for (let i = 0; i < fileInfos.length; i++) {
        const file = fileInfos[i]
        const sig = contentSignatures[i]
        const filenameEmb = filenameEmbeddings[i]

        // Insert file record
        await db.insert(semanticFiles).values({
          folderId: savedFolder.id,
          path: file.path,
          name: file.name,
          embedding: filenameEmb ? embeddingService.serializeEmbedding(filenameEmb) : null,
          contentSignature: sig?.signature || null,
          contentEmbedding: sig?.embedding
            ? embeddingService.serializeEmbedding(sig.embedding)
            : null,
          extension: file.extension,
          indexedAt: new Date(),
          lastModified: file.mtime,
          chunkCount: 0 // Chunks generated lazily during search
        })

        this.filesProcessed++

        // Log progress every 500 files
        if (this.filesProcessed % 500 === 0) {
          console.log(`[Indexer] Progress: ${this.filesProcessed} files indexed`)
        }
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
