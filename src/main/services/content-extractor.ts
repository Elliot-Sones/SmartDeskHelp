import { readFile } from 'fs/promises'
import { extname } from 'path'
import { embeddingService } from './embedding'

// Maximum characters to extract for content signature
const MAX_SIGNATURE_LENGTH = 500

// Supported file extensions for content extraction
const TEXT_EXTENSIONS = new Set([
  '.txt', '.md', '.json', '.js', '.ts', '.jsx', '.tsx',
  '.py', '.html', '.css', '.csv', '.xml', '.yaml', '.yml',
  '.sh', '.bash', '.zsh', '.c', '.cpp', '.h', '.hpp',
  '.java', '.go', '.rs', '.rb', '.php', '.swift', '.kt'
])

export interface ContentSignature {
  signature: string        // First ~500 chars of content
  embedding: Float32Array  // Embedding of the content
}

class ContentExtractorService {
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
   */
  private async readTextContent(filePath: string): Promise<string | null> {
    try {
      const buffer = await readFile(filePath)
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
