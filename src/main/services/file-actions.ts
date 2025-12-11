import { shell } from 'electron'

export async function openFile(filePath: string): Promise<boolean> {
  try {
    const result = await shell.openPath(filePath)
    if (result) {
      // shell.openPath returns an error string if it fails, empty string on success
      console.error('[FileActions] Failed to open file:', result)
      return false
    }
    console.log(`[FileActions] Opened: ${filePath}`)
    return true
  } catch (error) {
    console.error('[FileActions] Error opening file:', error)
    return false
  }
}
