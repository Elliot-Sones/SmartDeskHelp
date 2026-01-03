import { useEffect, useRef, useState } from 'react'
import '../../assets/search-popup.css'

export function SearchPopup(): JSX.Element {
    const inputRef = useRef<HTMLInputElement>(null)
    const [query, setQuery] = useState('')

    // Focus input when popup opens
    useEffect(() => {
        const focusHandler = (): void => {
            inputRef.current?.focus()
        }

        // Listen for focus request from main process
        window.electron.ipcRenderer.on('focus-search-input', focusHandler)

        // Initial focus
        setTimeout(() => inputRef.current?.focus(), 100)

        return () => {
            window.electron.ipcRenderer.removeListener('focus-search-input', focusHandler)
        }
    }, [])

    // Handle keyboard shortcuts
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent): void => {
            if (e.key === 'Escape') {
                window.electron.ipcRenderer.send('popup:close')
            }
            // NOTE: Enter key is handled by form onSubmit, not here (to avoid double submission)
        }

        document.addEventListener('keydown', handleKeyDown)
        return () => document.removeEventListener('keydown', handleKeyDown)
    }, [])

    const handleSubmit = (e: React.FormEvent): void => {
        e.preventDefault()
        if (query.trim()) {
            window.electron.ipcRenderer.send('popup:submit', query.trim())
        }
    }

    const handleExpand = (): void => {
        window.electron.ipcRenderer.send('popup:expand')
    }

    return (
        <div className="search-popup">
            <form onSubmit={handleSubmit} className="search-popup-form">
                <div className="search-icon">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <circle cx="11" cy="11" r="8" />
                        <path d="M21 21l-4.35-4.35" />
                    </svg>
                </div>
                <input
                    ref={inputRef}
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Ask Minnie anything..."
                    className="search-popup-input"
                    autoFocus
                />
                <button
                    type="button"
                    onClick={handleExpand}
                    className="expand-button"
                    title="Open full view (⌘⇧K)"
                >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polyline points="15 3 21 3 21 9" />
                        <polyline points="9 21 3 21 3 15" />
                        <line x1="21" y1="3" x2="14" y2="10" />
                        <line x1="3" y1="21" x2="10" y2="14" />
                    </svg>
                </button>
            </form>
        </div>
    )
}
