import { db } from '../db'
import { semanticFolders, semanticFiles } from '../db/schema'
import { embeddingService } from './embedding'
import { eq, isNull } from 'drizzle-orm'

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

// Minimum score for a folder to be considered a match (lowered to allow more exploration)
const FOLDER_THRESHOLD = 0.05

// Weights for hybrid scoring (filename + content + keyword)
const FILENAME_WEIGHT = 0.35
const CONTENT_WEIGHT = 0.35
const KEYWORD_WEIGHT = 0.30

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
  async findRelevantFiles(query: string): Promise<FileResult[]> {
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
      console.log(`[Router] Exploring: ${pathStr} (depth ${currentNode.depth})`)

      // Collect file candidates from this folder
      const filesInFolder = await this.searchFilesInFolder(
        queryVec,
        currentNode.folderId,
        currentNode.depth,
        keywords,
        pathStr
      )

      if (filesInFolder.length > 0) {
        console.log(
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
          console.log(
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
      const best = uniqueCandidates[0]
      console.log(
        `[Router] Best match: ${best.name} (hybrid=${(best.score * 100).toFixed(1)}%, filename=${(best.filenameScore * 100).toFixed(1)}%, content=${(best.contentScore * 100).toFixed(1)}%, keyword=${(best.keywordScore * 100).toFixed(1)}%)`
      )
      console.log(`[Router] Found in: ${best.folderPath}`)
      console.log(
        `[Router] Top 5 candidates: ${uniqueCandidates
          .slice(0, 5)
          .map((c) => `${c.name}=${c.score.toFixed(3)}`)
          .join(', ')}`
      )

      return uniqueCandidates.slice(0, 5)
    }

    console.log('[Router] No matching files found')
    return []
  }
}

export const routerService = new RouterService()
