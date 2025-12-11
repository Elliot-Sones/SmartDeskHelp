import { readFile } from 'fs/promises'
import { extname } from 'path'

// Maximum characters to extract from a file
const MAX_CONTENT_LENGTH = 4000

// Supported file extensions
const TEXT_EXTENSIONS = ['.txt', '.md', '.json', '.js', '.ts', '.py', '.html', '.css', '.csv', '.xml', '.yaml', '.yml']
const PDF_EXTENSION = '.pdf'

interface FileContent {
  text: string
  truncated: boolean
  fileType: string
}

class FileReaderService {
  /**
   * Read and extract text content from a file
   * Returns truncated content if file is too large
   */
  async readFileContent(filePath: string): Promise<FileContent | null> {
    const ext = extname(filePath).toLowerCase()

    try {
      if (TEXT_EXTENSIONS.includes(ext)) {
        return await this.readTextFile(filePath)
      } else if (ext === PDF_EXTENSION) {
        return await this.readPdfFile(filePath)
      } else {
        console.log(`[FileReader] Unsupported file type: ${ext}`)
        return null
      }
    } catch (error) {
      console.error(`[FileReader] Error reading ${filePath}:`, error)
      return null
    }
  }

  /**
   * Read plain text files
   */
  private async readTextFile(filePath: string): Promise<FileContent> {
    const content = await readFile(filePath, 'utf-8')
    const truncated = content.length > MAX_CONTENT_LENGTH
    
    return {
      text: content.slice(0, MAX_CONTENT_LENGTH),
      truncated,
      fileType: 'text'
    }
  }

  /**
   * Read PDF files using pdf-parse
   */
  private async readPdfFile(filePath: string): Promise<FileContent> {
    // pdf-parse v2.4.5 exports PDFParse as named export
    const { PDFParse } = await import('pdf-parse')
    
    const dataBuffer = await readFile(filePath)
    const pdfParser = new PDFParse({ data: new Uint8Array(dataBuffer) })
    
    // Get text content
    const textResult = await pdfParser.getText()
    const text = textResult.text || ''
    
    // Clean up
    await pdfParser.destroy()
    
    const truncated = text.length > MAX_CONTENT_LENGTH
    
    return {
      text: text.slice(0, MAX_CONTENT_LENGTH),
      truncated,
      fileType: 'pdf'
    }
  }

  /**
   * Check if a file type is supported for content reading
   */
  isSupported(filePath: string): boolean {
    const ext = extname(filePath).toLowerCase()
    return TEXT_EXTENSIONS.includes(ext) || ext === PDF_EXTENSION
  }
}

export const fileReaderService = new FileReaderService()
