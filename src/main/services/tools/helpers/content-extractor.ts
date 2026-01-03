import { readFile } from 'fs/promises'
import { extname } from 'path'
import { embeddingService } from '../../indexing/embedding'

// Maximum characters to extract for content signature (summary)
const MAX_SIGNATURE_LENGTH = 500

// Chunking configuration
const CHUNK_SIZE = 512 // Target chunk size in characters
const CHUNK_OVERLAP = 100 // Overlap between chunks to maintain context
const MIN_CHUNK_SIZE = 100 // Don't create chunks smaller than this
const MAX_CHUNKS_PER_FILE = 50 // Limit chunks to avoid huge files dominating
const MAX_FILE_SIZE_FOR_CHUNKING = 500 * 1024 // 500KB - skip very large files

// Supported file extensions for content extraction
const TEXT_EXTENSIONS = new Set([
  '.txt', '.md', '.json', '.js', '.ts', '.jsx', '.tsx',
  '.py', '.html', '.css', '.csv', '.xml', '.yaml', '.yml',
  '.sh', '.bash', '.zsh', '.c', '.cpp', '.h', '.hpp',
  '.java', '.go', '.rs', '.rb', '.php', '.swift', '.kt'
])

export interface ContentSignature {
  signature: string        // First ~500 chars of content
  embedding: Float32Array  // Embedding of the first chunk (for folder aggregation)
}

export interface ContentChunk {
  content: string          // The chunk text
  embedding: Float32Array  // Embedding of this chunk
  charOffset: number       // Starting position in original document
  chunkIndex: number       // Index of this chunk (0, 1, 2, ...)
}

export interface ChunkedContent {
  signature: string        // First ~500 chars for summary
  firstChunkEmbedding: Float32Array  // Embedding of first chunk (for backwards compat)
  chunks: ContentChunk[]   // All chunks for deep search
}

class ContentExtractorService {
  /**
   * Split content into overlapping chunks for deep search
   * Uses sentence-aware splitting when possible
   */
  private splitIntoChunks(content: string): { text: string; offset: number }[] {
    const chunks: { text: string; offset: number }[] = []

    if (content.length <= CHUNK_SIZE) {
      // Small content, single chunk
      if (content.trim().length >= MIN_CHUNK_SIZE) {
        chunks.push({ text: content.trim(), offset: 0 })
      }
      return chunks
    }

    let position = 0
    let chunkCount = 0

    while (position < content.length && chunkCount < MAX_CHUNKS_PER_FILE) {
      // Calculate chunk end position
      let endPosition = Math.min(position + CHUNK_SIZE, content.length)

      // Try to find a sentence boundary near the end for cleaner chunks
      if (endPosition < content.length) {
        const searchStart = Math.max(position + CHUNK_SIZE - 100, position)
        const searchWindow = content.slice(searchStart, endPosition + 50)

        // Look for sentence endings: . ! ? followed by space or newline
        const sentenceEnd = searchWindow.search(/[.!?]\s/)
        if (sentenceEnd !== -1 && sentenceEnd > 50) {
          endPosition = searchStart + sentenceEnd + 1
        }
      }

      const chunkText = content.slice(position, endPosition).trim()

      if (chunkText.length >= MIN_CHUNK_SIZE) {
        chunks.push({ text: chunkText, offset: position })
        chunkCount++
      }

      // Move position forward with overlap
      position = endPosition - CHUNK_OVERLAP

      // Prevent infinite loop
      if (position <= chunks[chunks.length - 1]?.offset) {
        position = endPosition
      }
    }

    return chunks
  }

  /**
   * Extract content with chunking for deep search
   * Returns signature + all chunks with embeddings
   */
  async extractWithChunks(filePath: string): Promise<ChunkedContent | null> {
    const ext = extname(filePath).toLowerCase()

    try {
      let content: string | null = null

      if (TEXT_EXTENSIONS.has(ext)) {
        // Skip large files for chunking (they'd create too many chunks)
        content = await this.readTextContent(filePath, true)
      } else if (ext === '.pdf') {
        content = await this.readPdfContent(filePath)
      } else if (ext === '.docx') {
        content = await this.readDocxContent(filePath)
      }

      if (!content || content.trim().length === 0) {
        return null
      }

      // Get signature (first 500 chars for summary display)
      const signature = content.slice(0, MAX_SIGNATURE_LENGTH).trim()

      // Split into chunks
      const rawChunks = this.splitIntoChunks(content)

      if (rawChunks.length === 0) {
        return null
      }

      // Embed all chunks in batch for efficiency
      const chunkTexts = rawChunks.map(c => c.text)
      const embeddings = await embeddingService.embedBatch(chunkTexts)

      // Build chunk objects
      const chunks: ContentChunk[] = rawChunks.map((raw, index) => ({
        content: raw.text,
        embedding: embeddings[index],
        charOffset: raw.offset,
        chunkIndex: index
      }))

      return {
        signature,
        firstChunkEmbedding: embeddings[0],
        chunks
      }
    } catch (error) {
      console.log(`[ContentExtractor] Could not extract chunks from ${filePath}:`, error)
      return null
    }
  }

  /**
   * Batch extract with chunking for multiple files
   */
  async extractBatchWithChunks(filePaths: string[]): Promise<(ChunkedContent | null)[]> {
    if (filePaths.length === 0) return []

    // Process files in parallel but with some concurrency control
    const results: (ChunkedContent | null)[] = []

    for (const filePath of filePaths) {
      const result = await this.extractWithChunks(filePath)
      results.push(result)
    }

    return results
  }

  /**
   * Extract content signature from a single file
   * Returns null for unsupported file types
   */
  async extractSignature(filePath: string): Promise<ContentSignature | null> {
    const ext = extname(filePath).toLowerCase()
    
    try {
      let content: string | null = null
      
      if (TEXT_EXTENSIONS.has(ext)) {
        content = await this.readTextContent(filePath)
      } else if (ext === '.pdf') {
        content = await this.readPdfContent(filePath)
      } else if (ext === '.docx') {
        content = await this.readDocxContent(filePath)
      }
      
      if (!content || content.trim().length === 0) {
        return null
      }
      
      // Truncate to signature length
      const signature = content.slice(0, MAX_SIGNATURE_LENGTH).trim()
      
      // Embed the content signature
      const embedding = await embeddingService.embed(signature)
      
      return { signature, embedding }
    } catch (error) {
      console.log(`[ContentExtractor] Could not extract from ${filePath}:`, error)
      return null
    }
  }

  /**
   * Extract content signatures from multiple files in batch
   * More efficient for bulk indexing
   */
  async extractBatch(filePaths: string[]): Promise<(ContentSignature | null)[]> {
    if (filePaths.length === 0) return []

    // First, extract raw content from all files
    const contents: (string | null)[] = await Promise.all(
      filePaths.map(async (filePath) => {
        const ext = extname(filePath).toLowerCase()
        
        try {
          if (TEXT_EXTENSIONS.has(ext)) {
            return await this.readTextContent(filePath)
          } else if (ext === '.pdf') {
            return await this.readPdfContent(filePath)
          } else if (ext === '.docx') {
            return await this.readDocxContent(filePath)
          }
          return null
        } catch {
          return null
        }
      })
    )

    // Separate valid and invalid content
    const validIndices: number[] = []
    const validSignatures: string[] = []
    
    for (let i = 0; i < contents.length; i++) {
      const content = contents[i]
      if (content && content.trim().length > 0) {
        validIndices.push(i)
        validSignatures.push(content.slice(0, MAX_SIGNATURE_LENGTH).trim())
      }
    }

    // Batch embed all valid signatures
    const embeddings = validSignatures.length > 0
      ? await embeddingService.embedBatch(validSignatures)
      : []

    // Build result array with nulls for unsupported files
    const results: (ContentSignature | null)[] = new Array(filePaths.length).fill(null)
    
    for (let i = 0; i < validIndices.length; i++) {
      const originalIndex = validIndices[i]
      results[originalIndex] = {
        signature: validSignatures[i],
        embedding: embeddings[i]
      }
    }

    return results
  }

  /**
   * Read plain text file content
   * Skip files larger than MAX_FILE_SIZE_FOR_CHUNKING
   */
  private async readTextContent(filePath: string, skipLargeFiles = false): Promise<string | null> {
    try {
      const buffer = await readFile(filePath)

      // Skip very large files for chunking
      if (skipLargeFiles && buffer.length > MAX_FILE_SIZE_FOR_CHUNKING) {
        return null
      }

      // Check if buffer looks like binary (has null bytes in first 8KB)
      const sample = buffer.slice(0, 8192)
      if (sample.includes(0)) {
        return null // Binary file
      }
      return buffer.toString('utf-8')
    } catch {
      return null
    }
  }

  /**
   * Read PDF file content
   */
  private async readPdfContent(filePath: string): Promise<string | null> {
    try {
      const { PDFParse } = await import('pdf-parse')
      const dataBuffer = await readFile(filePath)
      const pdfParser = new PDFParse({ data: new Uint8Array(dataBuffer) })
      const textResult = await pdfParser.getText()
      await pdfParser.destroy()
      return textResult.text || null
    } catch {
      return null
    }
  }

  /**
   * Read DOCX file content using mammoth
   */
  private async readDocxContent(filePath: string): Promise<string | null> {
    try {
      const mammoth = await import('mammoth')
      const result = await mammoth.extractRawText({ path: filePath })
      return result.value || null
    } catch {
      return null
    }
  }

  /**
   * Check if a file type is supported for content extraction
   */
  isSupported(filePath: string): boolean {
    const ext = extname(filePath).toLowerCase()
    return TEXT_EXTENSIONS.has(ext) || ext === '.pdf' || ext === '.docx'
  }
}

export const contentExtractorService = new ContentExtractorService()
