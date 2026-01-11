import { electronApp, is, optimizer } from '@electron-toolkit/utils'
import {
  app,
  BrowserWindow,
  globalShortcut,
  ipcMain,
  screen,
  shell,
  Tray,
  Menu,
  nativeImage
} from 'electron'
import { join } from 'path'
import icon from '../../resources/icon.png?asset'
import { runMigrations, initializeSettings } from './db'
import { registerAllApis } from './api'
import { setMainWindow } from './api/ai/handlers'

let mainWindow: BrowserWindow | null = null
let searchPopup: BrowserWindow | null = null
let tray: Tray | null = null
let windowPosition: 'left' | 'right' = 'right' // Start on the right by default
let isQuitting = false
let isPopupVisible = false

function createWindow(): void {
  // Get the primary display's work area
  const primaryDisplay = screen.getPrimaryDisplay()
  const { height: screenHeight } = primaryDisplay.workAreaSize

  // Window dimensions
  const windowWidth = 375
  const windowHeight = screenHeight

  // Create the browser window.
  mainWindow = new BrowserWindow({
    width: windowWidth,
    height: windowHeight,
    show: false,
    frame: false,
    resizable: true,
    movable: false,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    minWidth: 375,
    maxWidth: 450,
    autoHideMenuBar: true,
    transparent: true,
    vibrancy: 'sidebar',
    visualEffectState: 'active',
    roundedCorners: false,
    ...(process.platform === 'linux' ? { icon } : {}),
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false
    }
  })

  // Make window visible on all workspaces/desktops
  if (process.platform === 'darwin') {
    mainWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })
  }

  mainWindow.on('ready-to-show', () => {
    // Position the window now that it's properly sized
    const primaryDisplay = screen.getPrimaryDisplay()
    const { x: displayX, y: displayY, width: screenWidth } = primaryDisplay.workArea
    const [windowWidth] = mainWindow!.getSize()

    const x = displayX + screenWidth - windowWidth
    const y = displayY // Use the display's y offset (accounts for menu bar)

    mainWindow!.setPosition(x, y)
    // Don't show automatically - wait for the global shortcut
  })

  // Prevent the window from closing (e.g., when pressing Cmd+W)
  // Instead, hide it like the global shortcut does
  // But allow closing when the app is quitting
  mainWindow.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault()
      mainWindow?.hide()
      // On macOS, use app.hide() to properly restore focus to the previous application
      if (process.platform === 'darwin') {
        app.hide()
      }
    }
  })

  // Remove blur handler - window will only hide when shortcut is pressed again
  // This matches Raycast behavior where clicking outside doesn't hide the window

  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  // HMR for renderer base on electron-vite cli.
  // Load the remote URL for development or the local html file for production.
  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

function cycleWindowPosition(): void {
  if (!mainWindow) return

  // Cycle the position state
  windowPosition = windowPosition === 'right' ? 'left' : 'right'

  // Reposition the window
  const primaryDisplay = screen.getPrimaryDisplay()
  const { x: displayX, y: displayY, width: screenWidth } = primaryDisplay.workArea
  const [windowWidth] = mainWindow.getSize()

  const x = windowPosition === 'right' ? displayX + screenWidth - windowWidth : displayX
  const y = displayY

  mainWindow.setPosition(x, y)
}

// Create the small search popup that appears from the menu bar
function createSearchPopup(): void {
  if (searchPopup) return

  const popupWidth = 400
  const popupHeight = 60

  searchPopup = new BrowserWindow({
    width: popupWidth,
    height: popupHeight,
    show: false,
    frame: false,
    resizable: false,
    movable: false,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    transparent: true,
    vibrancy: 'popover',
    visualEffectState: 'active',
    roundedCorners: true,
    hasShadow: true,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false
    }
  })

  // Load the search popup route
  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    searchPopup.loadURL(process.env['ELECTRON_RENDERER_URL'] + '#/search-popup')
  } else {
    searchPopup.loadFile(join(__dirname, '../renderer/index.html'), { hash: '/search-popup' })
  }

  // Hide on blur (click outside)
  searchPopup.on('blur', () => {
    hideSearchPopup()
  })
}

function getPopupPosition(): { x: number; y: number } {
  if (!tray) return { x: 0, y: 0 }
  
  const trayBounds = tray.getBounds()
  const popupWidth = 400
  
  // Position centered below the tray icon
  const x = Math.round(trayBounds.x + trayBounds.width / 2 - popupWidth / 2)
  const y = trayBounds.y + trayBounds.height + 4 // 4px gap below tray
  
  return { x, y }
}

function toggleSearchPopup(): void {
  if (!searchPopup) {
    createSearchPopup()
  }
  
  if (isPopupVisible) {
    hideSearchPopup()
  } else {
    showSearchPopup()
  }
}

function showSearchPopup(): void {
  if (!searchPopup) return
  
  const { x, y } = getPopupPosition()
  searchPopup.setPosition(x, y)
  searchPopup.show()
  searchPopup.focus()
  isPopupVisible = true
  
  // Tell the renderer to focus the input
  searchPopup.webContents.send('focus-search-input')
}

function hideSearchPopup(): void {
  if (!searchPopup) return
  searchPopup.hide()
  isPopupVisible = false
}

function showFullWindow(query?: string): void {
  hideSearchPopup()
  
  if (!mainWindow) return
  
  // Reposition window
  const primaryDisplay = screen.getPrimaryDisplay()
  const { x: displayX, y: displayY, width: screenWidth } = primaryDisplay.workArea
  const [windowWidth] = mainWindow.getSize()

  const x = windowPosition === 'right' ? displayX + screenWidth - windowWidth : displayX
  const y = displayY

  mainWindow.setPosition(x, y)
  mainWindow.show()
  mainWindow.focus()
  
  // If query provided, send it to the main window
  if (query) {
    mainWindow.webContents.send('submit-query-from-popup', query)
  }
}

function createTray(): void {
  const iconPath = join(__dirname, '../../resources/dock-icon.png')
  const trayIcon = nativeImage.createFromPath(iconPath)
  const scaledIcon = trayIcon.resize({ width: 20, height: 20 })

  tray = new Tray(scaledIcon)
  
  // Click on tray icon shows the search popup
  tray.on('click', () => {
    toggleSearchPopup()
  })

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Minnie — ' + app.getVersion(),
      enabled: false
    },
    {
      type: 'separator'
    },
    {
      label: 'Quick Search',
      accelerator: 'CmdOrCtrl+K',
      click: () => {
        toggleSearchPopup()
      }
    },
    {
      label: 'Open Full View',
      accelerator: 'CmdOrCtrl+Shift+K',
      click: () => {
        showFullWindow()
      }
    },
    {
      label: 'Cycle Window Position',
      accelerator: 'CmdOrCtrl+J',
      click: () => {
        cycleWindowPosition()
      }
    },
    {
      type: 'separator'
    },
    {
      label: 'Close Window',
      accelerator: 'CmdOrCtrl+W',
      click: () => {
        hideSearchPopup()
        if (mainWindow?.isVisible()) {
          mainWindow.hide()
          if (process.platform === 'darwin') {
            app.hide()
          }
        }
      }
    },
    {
      label: 'Quit',
      accelerator: 'CmdOrCtrl+Q',
      click: () => {
        app.quit()
      }
    }
  ])

  tray.setContextMenu(contextMenu)
}

// This method will be called when Electron has finished
// initialization and is ready to create browser windows.
// Some APIs can only be used after this event occurs.
app.whenReady().then(async () => {
  // === CRITICAL PATH: DB + IPC handlers first (fast startup) ===
  await runMigrations()
  await initializeSettings()
  registerAllApis()

  // === BACKGROUND SERVICES ===
  setImmediate(async () => {
    const { spawn } = await import('child_process')
    const { join } = await import('path')
    
    const functionGemmaScript = join(__dirname, '../../python/function_gemma_server.py')
    const indexerScript = join(__dirname, '../../python/leann_indexer.py')

    // 1. Start FunctionGemma Server (Routing)
    console.log(`[Startup] Starting FunctionGemma: python3 ${functionGemmaScript}`)
    const functionServer = spawn('python3', [functionGemmaScript], { stdio: 'inherit' })
    functionServer.on('error', (e) => console.error('[Startup] FunctionGemma failed:', e))

    // 2. T5Gemma Server - DISABLED (using Claude instead until fine-tuning complete)
    
    // Ensure servers are killed when app quits
    app.on('before-quit', () => {
      functionServer.kill()
    })

    // 3. Check & Run Indexer if needed (now with memory-safe batching)
    console.log('[Startup] Checking LEANN index status...')
    try {
      const { leannClient } = await import('./services/leann')
      
      let status: { indexed: boolean; path: string | null } = { indexed: false, path: null }
      try {
         // Give server 2s to warmup
         await new Promise(r => setTimeout(r, 2000))
         status = await leannClient.getIndexStatus()
      } catch (e) {
         console.log('[Startup] Could not contact server for index status, assuming new.')
      }

      if (status.indexed) {
        console.log(`[Startup] LEANN index ready at: ${status?.path}`)
      } else {
        console.log('[Startup] LEANN index not found. STARTING INDEXER...')
        console.log(`[Startup] Spawning indexer: python3 ${indexerScript}`)
        
        const indexer = spawn('python3', [indexerScript, '--verbose'], { stdio: 'inherit' })
        indexer.on('close', (code) => console.log(`[Startup] Indexer finished with code ${code}`))
      }
    } catch (error) {
      console.error('[Startup] Initialization check failed:', error)
    }
  })

  // Set app user model id for windows
  electronApp.setAppUserModelId('com.electron')

  // Default open or close DevTools by F12 in development
  // and ignore CommandOrControl + R in production.
  // see https://github.com/alex8088/electron-toolkit/tree/master/packages/utils
  app.on('browser-window-created', (_, window) => {
    optimizer.watchWindowShortcuts(window)
  })

  // IPC handlers for search popup
  ipcMain.on('ping', () => console.log('pong'))
  
  // Popup requests to expand to full window
  ipcMain.on('popup:expand', () => {
    showFullWindow()
  })
  
  // Popup submits a query - expand and pass query to main window
  ipcMain.on('popup:submit', (_event, query: string) => {
    showFullWindow(query)
  })
  
  // Popup requests to close
  ipcMain.on('popup:close', () => {
    hideSearchPopup()
  })

  createWindow()

  // Pass window reference to handlers
  if (mainWindow) {
    setMainWindow(mainWindow)
  }

  // Create menu bar icon on macOS
  if (process.platform === 'darwin') {
    createTray()
  }
  
  // Create search popup (hidden initially)
  createSearchPopup()

  // Register global shortcut Cmd/Ctrl+K for quick search popup
  const ret = globalShortcut.register('CommandOrControl+K', () => {
    toggleSearchPopup()
  })

  if (!ret) {
    console.log('CommandOrControl+K shortcut registration failed')
  }
  
  // Register Cmd/Ctrl+Shift+K for full window
  const retFull = globalShortcut.register('CommandOrControl+Shift+K', () => {
    showFullWindow()
  })

  if (!retFull) {
    console.log('CommandOrControl+Shift+K shortcut registration failed')
  }

  // Register global shortcut Control+J to cycle window position
  const ret2 = globalShortcut.register('CommandOrControl+J', () => {
    cycleWindowPosition()
  })

  if (!ret2) {
    console.log('CommandOrControl+J shortcut registration failed')
  }

  app.on('activate', function () {
    // On macOS it's common to re-create a window in the app when the
    // dock icon is clicked and there are no other windows open.
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

// Keep the app running in the background even when all windows are closed
// This allows the global shortcut to work at all times
app.on('window-all-closed', () => {
  // Don't quit the app - keep it running in the background for the global shortcut
  // Users can quit via Cmd+Q or the menu
})

// Set flag before quitting to allow window to close
app.on('before-quit', () => {
  isQuitting = true
})

// Clean up global shortcuts when app is quitting
app.on('will-quit', () => {
  globalShortcut.unregisterAll()
})

// In this file you can include the rest of your app's specific main process
// code. You can also put them in separate files and require them here.
