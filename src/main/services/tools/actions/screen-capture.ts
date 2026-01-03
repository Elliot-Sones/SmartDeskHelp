/**
 * Screen Capture Service
 * Captures screenshots using Electron's desktopCapturer API
 * Used by the "see" tool to provide visual context to the LLM
 */

import { desktopCapturer, screen } from 'electron'

class ScreenCaptureService {
  /**
   * Capture the primary display as a base64-encoded PNG
   * Returns a data URL that can be sent directly to vision models
   */
  async captureScreen(): Promise<string> {
    try {
      const primaryDisplay = screen.getPrimaryDisplay()
      const { width, height } = primaryDisplay.size

      console.log(`[ScreenCapture] Capturing screen: ${width}x${height}`)

      // Get screen sources
      const sources = await desktopCapturer.getSources({
        types: ['screen'],
        thumbnailSize: { width, height }
      })

      if (sources.length === 0) {
        throw new Error('No screen sources available')
      }

      // Get the primary display source (usually the first one)
      const primarySource = sources[0]

      // Convert thumbnail to base64 data URL
      const thumbnail = primarySource.thumbnail
      const dataUrl = thumbnail.toDataURL()

      console.log(
        `[ScreenCapture] Captured screen: ${thumbnail.getSize().width}x${thumbnail.getSize().height}`
      )

      return dataUrl
    } catch (error) {
      console.error('[ScreenCapture] Failed to capture screen:', error)
      throw error
    }
  }

  /**
   * Capture and return just the base64 data (without data URL prefix)
   * Useful for APIs that expect raw base64
   */
  async captureScreenBase64(): Promise<string> {
    const dataUrl = await this.captureScreen()
    // Remove the "data:image/png;base64," prefix
    return dataUrl.replace(/^data:image\/\w+;base64,/, '')
  }
}

export const screenCaptureService = new ScreenCaptureService()
