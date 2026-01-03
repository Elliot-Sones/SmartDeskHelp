import { db } from '../../../db'
import { semanticFolders, semanticFiles, semanticChunks } from '../../../db/schema'
import { embeddingService } from '../../indexing/embedding'
import { contentExtractorService } from './content-extractor'
import { eq, isNull, inArray } from 'drizzle-orm'
import { homedir } from 'os'
import { join } from 'path'

// LAZY CHUNKING: Chunks are generated on-demand during search, not during indexing.
// This makes initial indexing fast, with slightly slower first search for each file.

interface FolderNode {
  id: number
  path: string
  name: string
  depth: number
  confidence: number
}

interface FileResult {
  id: number
  path: string
  name: string
  extension: string | null
  score: number
  filenameScore: number
  contentScore: number
  keywordScore: number
  foundAtLevel: number
  folderPath: string
}

// Result from chunk-level search with context
export interface ChunkSearchResult {
  fileId: number
  filePath: string
  fileName: string
  extension: string | null
  chunkIndex: number
  chunkContent: string  // The matching chunk text
  charOffset: number    // Position in original document
  score: number         // Similarity score
}

// Search filters from FunctionGemma
export interface SearchFilters {
  query: string
  file_types?: string[]
  location?: string
  date_range?: string
}

// Map file_type categories to actual extensions
const FILE_TYPE_EXTENSIONS: Record<string, string[]> = {
  pdf: ['pdf'],
  image: ['jpg', 'jpeg', 'png', 'gif', 'webp', 'heic', 'svg', 'bmp', 'tiff'],
  document: ['doc', 'docx', 'txt', 'rtf', 'odt', 'pages', 'md', 'pdf'],
  code: ['js', 'ts', 'tsx', 'jsx', 'py', 'java', 'c', 'cpp', 'h', 'go', 'rs', 'rb', 'php', 'swift', 'kt', 'sh', 'bash', 'zsh', 'json', 'yaml', 'yml', 'toml', 'xml', 'html', 'css', 'scss', 'sql'],
  video: ['mp4', 'mov', 'avi', 'mkv', 'webm', 'wmv', 'm4v'],
  audio: ['mp3', 'wav', 'aac', 'm4a', 'flac', 'ogg', 'wma'],
  archive: ['zip', 'tar', 'gz', 'rar', '7z', 'bz2']
}

// Map location names to actual paths
const LOCATION_PATHS: Record<string, string> = {
  documents: join(homedir(), 'Documents'),
  downloads: join(homedir(), 'Downloads'),
  desktop: join(homedir(), 'Desktop'),
  photos: join(homedir(), 'Pictures'),
  projects: join(homedir(), 'Desktop', 'Home', 'Projects'), // Adjust as needed
  home: homedir()
}

// Date range to milliseconds ago
const DATE_RANGE_MS: Record<string, number> = {
  today: 24 * 60 * 60 * 1000,           // 1 day
  week: 7 * 24 * 60 * 60 * 1000,        // 7 days
  month: 30 * 24 * 60 * 60 * 1000,      // 30 days
  year: 365 * 24 * 60 * 60 * 1000       // 365 days
}

// Minimum score for a folder to be considered a match (lowered to allow more exploration)
const FOLDER_THRESHOLD = 0.05

// Minimum score for a file result to be returned to the LLM
// Stricter threshold (0.35) to only return highly relevant results
const MIN_RESULT_SCORE = 0.25

// Weights for hybrid scoring (filename + content + keyword)
const FILENAME_WEIGHT = 0.35
const CONTENT_WEIGHT = 0.35
const KEYWORD_WEIGHT = 0.30

// Set to true to enable verbose beam search logging (floods terminal)
const DEBUG_LOGGING = false

// Beam search parameters
const BEAM_WIDTH = 3 // Number of top folders to explore
const BEAM_TOLERANCE = 0.15 // If folder is within this of best, include in beam
const ALWAYS_EXPLORE_BEST = true // Always add best folder even if below threshold

// Maximum search depth
const MAX_DEPTH = 20

interface BeamNode {
  folderId: number
  folderName: string
  path: FolderNode[]
  depth: number
}

class RouterService {
  /**
   * Extract keywords from a query string
   * Filters out common words and short words
   */
  private extractKeywords(query: string): string[] {
    const stopWords = new Set([
      'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
      'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
      'should', 'may', 'might', 'can', 'my', 'your', 'our', 'their', 'its',
      'for', 'to', 'of', 'in', 'on', 'at', 'by', 'with', 'from', 'and', 'or',
      'find', 'open', 'show', 'get', 'please', 'can', 'you', 'me', 'i'
    ])

    return query
      .toLowerCase()
      .replace(/[^\w\s]/g, '') // Remove punctuation
      .split(/\s+/)
      .filter((word) => word.length >= 2 && !stopWords.has(word))
  }

  /**
   * Calculate keyword score based on how many keywords match the path
   */
  private calculateKeywordScore(filePath: string, keywords: string[]): number {
    if (keywords.length === 0) return 0

    const lowerPath = filePath.toLowerCase()
    let matchCount = 0

    for (const keyword of keywords) {
      if (lowerPath.includes(keyword)) {
        matchCount++
      }
    }

    return matchCount / keywords.length
  }

  /**
   * Search for files in a specific folder and return scored results with hybrid scoring
   */
  private async searchFilesInFolder(
    queryVec: Float32Array,
    folderId: number,
    level: number,
    keywords: string[],
    folderPath: string
  ): Promise<FileResult[]> {
    const files = await db
      .select()
      .from(semanticFiles)
      .where(eq(semanticFiles.folderId, folderId))

    const scored = files.map((f) => {
      const filenameEmb = f.embedding as Buffer | null
      const contentEmb = f.contentEmbedding as Buffer | null
      
      const filenameScore = filenameEmb ? embeddingService.cosineSimilarity(queryVec, filenameEmb) : 0
      const contentScore = contentEmb ? embeddingService.cosineSimilarity(queryVec, contentEmb) : 0
      const keywordScore = this.calculateKeywordScore(f.path, keywords)

      // Hybrid score: weighted combination of filename, content, and keyword
      // If no content embedding, redistribute weight to filename
      let score: number
      if (contentEmb) {
        score = FILENAME_WEIGHT * filenameScore + CONTENT_WEIGHT * contentScore + KEYWORD_WEIGHT * keywordScore
      } else {
        // No content: use 60% filename, 40% keyword
        score = 0.6 * filenameScore + 0.4 * keywordScore
      }

      return {
        file: f,
        score,
        filenameScore,
        contentScore,
        keywordScore
      }
    })

    return scored
      .sort((a, b) => b.score - a.score)
      .slice(0, 3) // Top 3 per folder to avoid too many candidates
      .map((r) => ({
        id: r.file.id,
        path: r.file.path,
        name: r.file.name,
        extension: r.file.extension,
        score: r.score,
        filenameScore: r.filenameScore,
        contentScore: r.contentScore,
        keywordScore: r.keywordScore,
        foundAtLevel: level,
        folderPath
      }))
  }

  /**
   * Beam Search: explores multiple folder paths simultaneously
   * Instead of picking single best folder, explores top K folders if scores are close
   */
  async findRelevantFiles(query: string, limit: number = 10): Promise<FileResult[]> {
    console.log(`[Router] Beam Search for: "${query}"`)

    // Extract keywords for hybrid scoring
    const keywords = this.extractKeywords(query)
    console.log(`[Router] Keywords extracted: [${keywords.join(', ')}]`)

    const queryVec = await embeddingService.embed(query)
    console.log(`[Router] Query vector length: ${queryVec.length}`)

    const allCandidates: FileResult[] = []
    const exploredPaths: string[] = []

    // Initialize beam with root folders
    const rootFolders = await db.select().from(semanticFolders).where(isNull(semanticFolders.parentId))

    let beam: BeamNode[] = rootFolders.map((f) => ({
      folderId: f.id,
      folderName: f.name,
      path: [{
        id: f.id,
        path: f.path,
        name: f.name,
        depth: f.depth,
        confidence: 1
      }],
      depth: 0
    }))

    console.log(`[Router] Starting beam search with ${beam.length} root nodes`)

    // BFS with beam search
    while (beam.length > 0) {
      const currentNode = beam.shift()!

      if (currentNode.depth > MAX_DEPTH) continue

      const pathStr = currentNode.path.map((n) => n.name).join(' → ')
      if (DEBUG_LOGGING) console.log(`[Router] Exploring: ${pathStr} (depth ${currentNode.depth})`)

      // Collect file candidates from this folder
      const filesInFolder = await this.searchFilesInFolder(
        queryVec,
        currentNode.folderId,
        currentNode.depth,
        keywords,
        pathStr
      )

      if (filesInFolder.length > 0) {
        if (DEBUG_LOGGING) console.log(
          `[Router] Files found: ${filesInFolder
            .slice(0, 2)
            .map((f) => `${f.name}=${f.score.toFixed(3)}`)
            .join(', ')}`
        )
        allCandidates.push(...filesInFolder)
      }

      // Get child folders
      const children = await db
        .select()
        .from(semanticFolders)
        .where(eq(semanticFolders.parentId, currentNode.folderId))

      if (children.length === 0) {
        exploredPaths.push(pathStr)
        continue
      }

      // Score child folders (folders have mean-pooled embeddings of their content)
      const scoredChildren = children.map((folder) => {
        const embedding = folder.embedding as Buffer | null
        const semanticScore = embedding ? embeddingService.cosineSimilarity(queryVec, embedding) : 0
        const keywordScore = this.calculateKeywordScore(folder.path, keywords)
        // Folder semantic score combines filename + content weight since folder embedding is content-aware
        const score = (FILENAME_WEIGHT + CONTENT_WEIGHT) * semanticScore + KEYWORD_WEIGHT * keywordScore

        return { folder, score, semanticScore, keywordScore }
      })

      // Sort by score
      scoredChildren.sort((a, b) => b.score - a.score)

      if (scoredChildren.length > 0) {
        const bestScore = scoredChildren[0].score

        // Select folders for beam: top K and any within tolerance of best
        const selectedFolders = scoredChildren.filter(
          (f, idx) => idx < BEAM_WIDTH || f.score >= bestScore - BEAM_TOLERANCE
        )

        // Filter by threshold, but ALWAYS include at least the best folder
        let validFolders = selectedFolders.filter(
          (f) => f.score >= FOLDER_THRESHOLD || children.length === 1
        )

        // If no folders passed threshold but we should always explore best, add it
        if (validFolders.length === 0 && ALWAYS_EXPLORE_BEST && scoredChildren.length > 0) {
          validFolders = [scoredChildren[0]] // Add the best folder regardless of score
        }

        if (validFolders.length > 0) {
          if (DEBUG_LOGGING) console.log(
            `[Router] Beam expansion: ${validFolders.map((f) => `${f.folder.name}=${f.score.toFixed(3)}`).join(', ')}`
          )

          // Add to beam
          for (const { folder, score } of validFolders) {
            beam.push({
              folderId: folder.id,
              folderName: folder.name,
              path: [
                ...currentNode.path,
                {
                  id: folder.id,
                  path: folder.path,
                  name: folder.name,
                  depth: folder.depth,
                  confidence: score
                }
              ],
              depth: currentNode.depth + 1
            })
          }
        }
      }
    }

    // Sort all candidates by hybrid score
    allCandidates.sort((a, b) => b.score - a.score)

    // De-duplicate by path
    const seen = new Set<string>()
    const uniqueCandidates = allCandidates.filter((c) => {
      if (seen.has(c.path)) return false
      seen.add(c.path)
      return true
    })

    console.log(`[Router] Explored ${exploredPaths.length} leaf paths`)

    if (uniqueCandidates.length > 0) {
      // Filter by minimum relevance score
      const relevantResults = uniqueCandidates.filter(c => c.score >= MIN_RESULT_SCORE)
      
      if (relevantResults.length === 0) {
        console.log(`[Router] No results above relevance threshold (${MIN_RESULT_SCORE})`)
        console.log(`[Router] Best score was: ${uniqueCandidates[0].score.toFixed(3)} for ${uniqueCandidates[0].name}`)
        return []
      }
      
      const best = relevantResults[0]
      console.log(
        `[Router] Best match: ${best.name} (hybrid=${(best.score * 100).toFixed(1)}%, filename=${(best.filenameScore * 100).toFixed(1)}%, content=${(best.contentScore * 100).toFixed(1)}%, keyword=${(best.keywordScore * 100).toFixed(1)}%)`
      )
      console.log(`[Router] Found in: ${best.folderPath}`)
      console.log(
        `[Router] Returning ${relevantResults.slice(0, limit).length} relevant results (threshold: ${MIN_RESULT_SCORE})`
      )

      return relevantResults.slice(0, limit)
    }

    console.log('[Router] No matching files found')
    return []
  }

  /**
   * Find files with filters from FunctionGemma
   * Applies file type, location, and date filters BEFORE semantic search
   * This is much faster than searching everything
   */
  async findFilesWithFilters(filters: SearchFilters): Promise<FileResult[]> {
    const startTime = Date.now()
    console.log(`[Router] Filtered search for: "${filters.query}"`)
    console.log(`[Router] Filters: types=${filters.file_types?.join(',') || 'any'}, location=${filters.location || 'anywhere'}, date=${filters.date_range || 'anytime'}`)

    // Get allowed extensions from file_types filter
    let allowedExtensions: Set<string> | null = null
    if (filters.file_types && filters.file_types.length > 0 && !filters.file_types.includes('any')) {
      allowedExtensions = new Set<string>()
      for (const fileType of filters.file_types) {
        const exts = FILE_TYPE_EXTENSIONS[fileType]
        if (exts) {
          exts.forEach(ext => allowedExtensions!.add(ext.toLowerCase()))
        }
      }
      console.log(`[Router] Allowed extensions: ${[...allowedExtensions].join(', ')}`)
    }

    // Get location path filter
    let locationPath: string | null = null
    if (filters.location && filters.location !== 'anywhere') {
      locationPath = LOCATION_PATHS[filters.location]
      if (locationPath) {
        console.log(`[Router] Filtering to location: ${locationPath}`)
      }
    }

    // Get date cutoff
    let dateCutoff: Date | null = null
    if (filters.date_range && filters.date_range !== 'anytime') {
      const msAgo = DATE_RANGE_MS[filters.date_range]
      if (msAgo) {
        dateCutoff = new Date(Date.now() - msAgo)
        console.log(`[Router] Date cutoff: ${dateCutoff.toISOString()}`)
      }
    }

    // Step 1: Pre-filter files from database
    let allFiles = await db.select().from(semanticFiles)
    const totalFiles = allFiles.length
    console.log(`[Router] Total files in index: ${totalFiles}`)

    // Apply extension filter
    if (allowedExtensions && allowedExtensions.size > 0) {
      allFiles = allFiles.filter(f => {
        const ext = f.extension?.toLowerCase() || ''
        return allowedExtensions!.has(ext)
      })
      console.log(`[Router] After type filter: ${allFiles.length} files`)
    }

    // Apply location filter
    if (locationPath) {
      allFiles = allFiles.filter(f => f.path.startsWith(locationPath!))
      console.log(`[Router] After location filter: ${allFiles.length} files`)
    }

    // Apply date filter (using indexedAt as proxy since we don't store mtime)
    if (dateCutoff) {
      allFiles = allFiles.filter(f => {
        const fileDate = f.indexedAt ? new Date(f.indexedAt) : null
        return fileDate && fileDate >= dateCutoff!
      })
      console.log(`[Router] After date filter: ${allFiles.length} files`)
    }

    // Step 2: If no files after filtering, try relaxing filters
    if (allFiles.length === 0) {
      console.log('[Router] No files after filtering, relaxing filters...')
      // Try without date filter
      if (dateCutoff) {
        allFiles = await db.select().from(semanticFiles)
        if (allowedExtensions && allowedExtensions.size > 0) {
          allFiles = allFiles.filter(f => allowedExtensions!.has(f.extension?.toLowerCase() || ''))
        }
        if (locationPath) {
          allFiles = allFiles.filter(f => f.path.startsWith(locationPath!))
        }
        console.log(`[Router] Without date filter: ${allFiles.length} files`)
      }
    }

    // Step 3: Semantic search on filtered candidates only
    if (allFiles.length === 0) {
      console.log('[Router] No candidates after filtering')
      return []
    }

    const keywords = this.extractKeywords(filters.query)
    const queryVec = await embeddingService.embed(filters.query)

    const scored = allFiles.map(f => {
      const filenameEmb = f.embedding as Buffer | null
      const contentEmb = f.contentEmbedding as Buffer | null

      const filenameScore = filenameEmb ? embeddingService.cosineSimilarity(queryVec, filenameEmb) : 0
      const contentScore = contentEmb ? embeddingService.cosineSimilarity(queryVec, contentEmb) : 0
      const keywordScore = this.calculateKeywordScore(f.path, keywords)

      let score: number
      if (contentEmb) {
        score = FILENAME_WEIGHT * filenameScore + CONTENT_WEIGHT * contentScore + KEYWORD_WEIGHT * keywordScore
      } else {
        score = 0.6 * filenameScore + 0.4 * keywordScore
      }

      // Extract folder path from file path
      const pathParts = f.path.split('/')
      const folderPath = pathParts.slice(0, -1).join('/')

      return {
        id: f.id,
        path: f.path,
        name: f.name,
        extension: f.extension,
        score,
        filenameScore,
        contentScore,
        keywordScore,
        foundAtLevel: 0,
        folderPath
      }
    })

    // Sort and filter by relevance threshold
    scored.sort((a, b) => b.score - a.score)
    const relevantResults = scored.filter(r => r.score >= MIN_RESULT_SCORE).slice(0, 5)

    const elapsedMs = Date.now() - startTime
    console.log(`[Router] Filtered search completed in ${elapsedMs}ms`)
    console.log(`[Router] Searched ${allFiles.length}/${totalFiles} files (${Math.round(allFiles.length / totalFiles * 100)}% of index)`)
    
    if (relevantResults.length > 0) {
      console.log(`[Router] Returning ${relevantResults.length} relevant results (threshold: ${MIN_RESULT_SCORE})`)
    } else if (scored.length > 0) {
      console.log(`[Router] No results above threshold. Best: ${scored[0].name}=${scored[0].score.toFixed(3)}`)
    }

    return relevantResults
  }

  /**
   * LAZY CHUNKING: Generate and cache chunks for files that don't have them yet
   * Only generates chunks for the specified file IDs
   */
  private async ensureChunksExist(fileIds: number[]): Promise<void> {
    // TEMPORARILY DISABLED: Lazy chunking blocks main thread
    // TODO: Re-enable after Worker Thread implementation
    console.log('[Router] Lazy chunking DISABLED - skipping chunk generation')
    return
    
    if (fileIds.length === 0) return

    // Find files that don't have chunks yet (chunkCount = 0)
    const files = await db
      .select({ 
        id: semanticFiles.id, 
        path: semanticFiles.path, 
        name: semanticFiles.name,
        chunkCount: semanticFiles.chunkCount 
      })
      .from(semanticFiles)
      .where(inArray(semanticFiles.id, fileIds))

    const filesNeedingChunks = files.filter(f => !f.chunkCount || f.chunkCount === 0)

    if (filesNeedingChunks.length === 0) {
      return // All files already have chunks
    }

    console.log(`[Router] Generating chunks for ${filesNeedingChunks.length} files (lazy chunking)...`)
    const startTime = Date.now()

    // Process in batches of 3 to avoid OOM but speed up processing
    const BATCH_SIZE = 3
    for (let i = 0; i < filesNeedingChunks.length; i += BATCH_SIZE) {
      const batch = filesNeedingChunks.slice(i, i + BATCH_SIZE)
      await Promise.all(batch.map(file => this.generateChunksForFile(file)))
    }

    const elapsed = Date.now() - startTime
    console.log(`[Router] Chunk generation complete in ${elapsed}ms`)
  }

  /**
   * Helper to generate chunks for a single file with timeout
   */
  private async generateChunksForFile(file: { id: number, path: string, name: string }): Promise<void> {
    const start = Date.now()
    try {
      // 10s timeout for chunk generation
      const chunkProm = contentExtractorService.extractWithChunks(file.path)
      const timeoutProm = new Promise<null>((resolve) => setTimeout(() => resolve(null), 10000))
      
      const chunked = await Promise.race([chunkProm, timeoutProm])

      if (!chunked) {
        console.log(`[Router] Timeout or failed to chunk ${file.name} (${Date.now() - start}ms)`)
        return
      }

      if (chunked.chunks.length > 0) {
        // Insert chunks
        for (const chunk of chunked.chunks) {
          await db.insert(semanticChunks).values({
            fileId: file.id,
            chunkIndex: chunk.chunkIndex,
            content: chunk.content,
            embedding: embeddingService.serializeEmbedding(chunk.embedding),
            charOffset: chunk.charOffset
          })
        }

        // Update file's chunkCount
        await db
          .update(semanticFiles)
          .set({ chunkCount: chunked.chunks.length })
          .where(eq(semanticFiles.id, file.id))
          
        console.log(`[Router] Generated ${chunked.chunks.length} chunks for ${file.name} in ${Date.now() - start}ms`)
      }
    } catch (error) {
      console.log(`[Router] Error chunking file ${file.path} (${Date.now() - start}ms):`, error)
    }
  }

  /**
   * Search across document chunks for deep content matching
   * Uses LAZY CHUNKING:
   * 1. First finds candidate files using file-level search
   * 2. Generates chunks on-demand for those candidates
   * 3. Then searches across the chunks
   */
  async searchChunks(query: string, topK = 10): Promise<ChunkSearchResult[]> {
    console.log(`[Router] Deep content search for: "${query}"`)
    const startTime = Date.now()

    // Step 1: Find candidate files using quick file-level search
    // This narrows down which files to chunk (instead of chunking everything)
    // Aggressively fetch top 25 to cast a wider net for lazy chunking
    const candidateFiles = await this.findRelevantFiles(query, 25)

    if (candidateFiles.length === 0) {
      console.log('[Router] No candidate files found for chunk search')
      return []
    }

    // Filter to only files WITH content (contentScore > 0)
    // Files without extractable content shouldn't be candidates for deep content search
    const filesWithContent = candidateFiles.filter(f => f.contentScore > 0)
    
    if (filesWithContent.length === 0) {
      console.log('[Router] No files with extractable content found')
      return []
    }
    
    const candidateFileIds = filesWithContent.map(f => f.id)
    console.log(`[Router] Found ${filesWithContent.length} candidate files for deep search (${candidateFiles.length - filesWithContent.length} filtered for no content)`)

    // Step 2: LAZY CHUNKING - ensure chunks exist for candidate files
    await this.ensureChunksExist(candidateFileIds)

    // Step 3: Get chunks for these files only
    const chunks = await db
      .select({
        chunkId: semanticChunks.id,
        fileId: semanticChunks.fileId,
        chunkIndex: semanticChunks.chunkIndex,
        content: semanticChunks.content,
        embedding: semanticChunks.embedding,
        charOffset: semanticChunks.charOffset,
        filePath: semanticFiles.path,
        fileName: semanticFiles.name,
        extension: semanticFiles.extension
      })
      .from(semanticChunks)
      .innerJoin(semanticFiles, eq(semanticChunks.fileId, semanticFiles.id))
      .where(inArray(semanticChunks.fileId, candidateFileIds))

    if (chunks.length === 0) {
      console.log('[Router] No chunks generated for candidate files')
      return []
    }

    console.log(`[Router] Searching ${chunks.length} chunks from ${candidateFiles.length} files...`)

    // Embed query
    const queryVec = await embeddingService.embed(query)

    // Extract keywords for hybrid scoring
    const keywords = this.extractKeywords(query)

    // Score all chunks
    const scored = chunks.map(chunk => {
      const chunkEmbedding = chunk.embedding as Buffer
      const semanticScore = embeddingService.cosineSimilarity(queryVec, chunkEmbedding)

      // Keyword boost
      const keywordScore = this.calculateKeywordScore(chunk.content, keywords)

      // Combined score (80% semantic, 20% keyword)
      const score = 0.8 * semanticScore + 0.2 * keywordScore

      return {
        fileId: chunk.fileId,
        filePath: chunk.filePath,
        fileName: chunk.fileName,
        extension: chunk.extension,
        chunkIndex: chunk.chunkIndex,
        chunkContent: chunk.content,
        charOffset: chunk.charOffset,
        score
      }
    })

    // Sort by score and take top K
    scored.sort((a, b) => b.score - a.score)

    // Filter by minimum threshold
    const MIN_CHUNK_SCORE = 0.20
    const relevant = scored.filter(c => c.score >= MIN_CHUNK_SCORE).slice(0, topK)

    const elapsedMs = Date.now() - startTime
    console.log(`[Router] Deep content search completed in ${elapsedMs}ms`)

    if (relevant.length > 0) {
      console.log(`[Router] Found ${relevant.length} relevant chunks (best: ${relevant[0].score.toFixed(3)} in ${relevant[0].fileName})`)
    } else if (scored.length > 0) {
      console.log(`[Router] No chunks above threshold. Best: ${scored[0].score.toFixed(3)} in ${scored[0].fileName}`)
    }

    return relevant
  }

  /**
   * Combined search: files + chunks
   * Returns file results enriched with matching chunk content
   */
  async searchWithContent(query: string): Promise<{
    files: FileResult[]
    chunks: ChunkSearchResult[]
  }> {
    // Run both searches in parallel
    const [files, chunks] = await Promise.all([
      this.findRelevantFiles(query),
      this.searchChunks(query, 5)
    ])

    return { files, chunks }
  }
}

export const fileSearchService = new RouterService()

