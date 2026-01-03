import { parentPort, workerData } from 'worker_threads'
import { readFile } from 'fs/promises'
import { extname } from 'path'
import { PDFParse } from 'pdf-parse' // Need to verify import style
import * as mammoth from 'mammoth'

// Handle messages from main thread
parentPort?.on('message', async (filePath: string) => {
  try {
    const content = await extractContent(filePath)
    parentPort?.postMessage({ success: true, content })
  } catch (error) {
    parentPort?.postMessage({ success: false, error: String(error) })
  }
})

async function extractContent(filePath: string): Promise<string | null> {
  const ext = extname(filePath).toLowerCase()
  
  if (ext === '.pdf') {
    return await readPdfContent(filePath)
  } else if (ext === '.docx') {
    return await readDocxContent(filePath)
  } else if (['.txt', '.md', '.json', '.js', '.ts', '.py', '.yml', '.yaml'].includes(ext)) {
    return await readFile(filePath, 'utf-8')
  }
  
  return null
}

async function readPdfContent(filePath: string): Promise<string | null> {
  try {
    // Dynamic import might be needed if using ESM/CJS mix, but worker is usually compiled
    // Using simple require/import logic for now based on previous code
    const pdf = require('pdf-parse')
    const dataBuffer = await readFile(filePath)
    const data = await pdf(dataBuffer)
    return data.text
  } catch (error) {
    console.error('PDF Parse Error:', error)
    throw error
  }
}

async function readDocxContent(filePath: string): Promise<string | null> {
  try {
    const result = await mammoth.extractRawText({ path: filePath })
    return result.value
  } catch (error) {
    console.error('Docx Parse Error:', error)
    throw error
  }
}
