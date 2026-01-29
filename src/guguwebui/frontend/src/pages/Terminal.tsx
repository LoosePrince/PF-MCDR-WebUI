import React, { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import axios from 'axios'
import {
  Terminal as TerminalIcon,
  RotateCcw,
  Trash2,
  Copy,
  BrainCircuit,
  Settings,
  X,
  Send,
  Loader2,
  Sparkles,
  Bot,
  User,
  AlertTriangle,
  ArrowDown
} from 'lucide-react'

// --- Interfaces ---

interface LogItem {
  line_number?: number
  content: string
  counter?: number // Used for incremental updates
  time?: string
}

interface CommandSuggestion {
  command: string
  description?: string
  display?: string // Optional display text if differ from command
}

interface AIConfig {
  ai_api_key_configured: boolean
}

// --- Components ---

const Terminal: React.FC = () => {
  const { t } = useTranslation()

  // --- State ---
  const [logs, setLogs] = useState<LogItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [serverStatus, setServerStatus] = useState<'online' | 'offline' | 'loading' | 'error'>('loading')
  const [serverVersion, setServerVersion] = useState('')

  // Auto-scroll & Refresh
  const [autoScroll, setAutoScroll] = useState(true)
  const [autoRefresh, setAutoRefresh] = useState(true)
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [initialLoadComplete, setInitialLoadComplete] = useState(false)
  const logsEndRef = useRef<HTMLDivElement>(null)
  const terminalContainerRef = useRef<HTMLDivElement>(null)
  const suggestionsContainerRef = useRef<HTMLDivElement>(null)
  const suggestionItemRefs = useRef<(HTMLButtonElement | null)[]>([])
  const lastLogCounter = useRef<number>(0)

  // Command Input
  const [commandInput, setCommandInput] = useState('')
  const [commandHistory, setCommandHistory] = useState<string[]>([])
  const [historyIndex, setHistoryIndex] = useState(-1)
  const [historyTemp, setHistoryTemp] = useState('')

  // Command Suggestions
  const [suggestions, setSuggestions] = useState<CommandSuggestion[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [selectedSuggestionIndex, setSelectedSuggestionIndex] = useState(-1)
  const suggestionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // AI & Selection
  const [selectionButtonPos, setSelectionButtonPos] = useState<{ x: number, y: number } | null>(null)
  const [selectedText, setSelectedText] = useState('')
  const [showAIModal, setShowAIModal] = useState(false)
  const [aiQuery, setAiQuery] = useState('')
  const [aiLoading, setAiLoading] = useState(false)
  const [aiChatHistory, setAiChatHistory] = useState<{ role: string, content: string }[]>([])

  // API Key Settings
  const [showApiKeyModal, setShowApiKeyModal] = useState(false)
  const [apiKey, setApiKey] = useState('')
  const [hasApiKey, setHasApiKey] = useState(false)

  // Notification
  const [notification, setNotification] = useState<{ msg: string, type: 'success' | 'error' | 'info' } | null>(null)

  // --- Refs & Constants ---
  const MAX_LOGS = 1000
  const REFRESH_INTERVAL = 3000
  const STATUS_INTERVAL = 10000

  // --- Helpers ---
  const showNote = (msg: string, type: 'success' | 'error' | 'info' = 'success') => {
    setNotification({ msg, type })
    setTimeout(() => setNotification(null), 3000)
  }

  const scrollToBottom = () => {
    if (terminalContainerRef.current) {
      terminalContainerRef.current.scrollTop = terminalContainerRef.current.scrollHeight
    }
  }

  // --- Effects ---

  // Initial Load
  useEffect(() => {
    // 创建 AbortController 用于取消请求
    const abortController = new AbortController()
    const signal = abortController.signal

    checkServerStatus(signal)
    loadLogs(signal)
    checkApiKeyStatus(signal)

    // Load history from local storage
    const savedHistory = localStorage.getItem('commandHistory')
    if (savedHistory) {
      try {
        setCommandHistory(JSON.parse(savedHistory))
      } catch (e) {
        console.error('Failed to parse command history', e)
      }
    }

    const statusTimer = setInterval(() => checkServerStatus(signal), STATUS_INTERVAL)

    return () => {
      // 取消所有进行中的请求
      abortController.abort()
      clearInterval(statusTimer)
    }
  }, [])

  // Auto refresh timer (separate effect to handle autoRefresh state properly)
  useEffect(() => {
    if (!autoRefresh) return
    if (!initialLoadComplete) return // Wait for initial load to complete

    // 创建 AbortController 用于取消请求
    const abortController = new AbortController()
    const signal = abortController.signal

    // Immediately fetch once when autoRefresh is enabled and initial load is complete
    fetchNewLogs(signal)

    // Then set up interval for auto refresh
    const refreshTimer = setInterval(() => {
      fetchNewLogs(signal)
    }, REFRESH_INTERVAL)

    return () => {
      // 取消所有进行中的请求
      abortController.abort()
      clearInterval(refreshTimer)
    }
  }, [autoRefresh, initialLoadComplete])

  // Scroll on logs change
  useEffect(() => {
    if (autoScroll) {
      scrollToBottom()
    }
  }, [logs, autoScroll])

  // Auto-scroll suggestions when selected index changes
  useEffect(() => {
    if (showSuggestions && selectedSuggestionIndex >= 0 && suggestionItemRefs.current[selectedSuggestionIndex]) {
      const selectedElement = suggestionItemRefs.current[selectedSuggestionIndex]
      if (selectedElement) {
        selectedElement.scrollIntoView({
          behavior: 'smooth',
          block: 'nearest',
          inline: 'nearest'
        })
      }
    }
  }, [selectedSuggestionIndex, showSuggestions])

  // Handle Selection for Floating Button
  useEffect(() => {
    const handleSelection = () => {
      const selection = window.getSelection()
      if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
        setSelectionButtonPos(null)
        return
      }

      const text = selection.toString().trim()
      if (!text) {
        setSelectionButtonPos(null)
        return
      }

      // Check if selection is inside terminal
      if (terminalContainerRef.current && terminalContainerRef.current.contains(selection.anchorNode)) {
        const range = selection.getRangeAt(0)
        const rect = range.getBoundingClientRect()
        // Position relative to viewport is returned by getBoundingClientRect
        // We need to adjust layout or use fixed positioning. 
        // Let's use fixed positioning for the button.
        if (rect.width > 0 && rect.height > 0) {
          setSelectionButtonPos({
            x: rect.left + rect.width / 2,
            y: rect.bottom + 10
          })
          setSelectedText(text)
        }
      } else {
        setSelectionButtonPos(null)
      }
    }

    document.addEventListener('mouseup', handleSelection)
    document.addEventListener('selectionchange', handleSelection) // Optional, but smoother

    return () => {
      document.removeEventListener('mouseup', handleSelection)
      document.removeEventListener('selectionchange', handleSelection)
    }
  }, [])

  // --- API Calls ---

  const checkServerStatus = async (signal?: AbortSignal) => {
    try {
      const res = await axios.get('/api/get_server_status', { signal })
      setServerStatus(res.data.status || 'offline')
      setServerVersion(res.data.version || '')
    } catch (e: any) {
      // 忽略取消的请求错误
      if (axios.isCancel(e) || e.name === 'AbortError' || e.code === 'ERR_CANCELED') {
        return
      }
      setServerStatus('error')
    }
  }

  const checkApiKeyStatus = async (signal?: AbortSignal) => {
    try {
      const res = await axios.get('/api/get_web_config', { signal })
      const config: AIConfig = res.data
      setHasApiKey(!!config.ai_api_key_configured)
    } catch (e: any) {
      // 忽略取消的请求错误
      if (axios.isCancel(e) || e.name === 'AbortError' || e.code === 'ERR_CANCELED') {
        return
      }
      console.error('Failed to check API key status', e)
    }
  }

  const loadLogs = async (signal?: AbortSignal) => {
    setIsLoading(true)
    try {
      const res = await axios.get('/api/server_logs', { params: { max_lines: 500 }, signal })
      if (res.data.status === 'success') {
        const newLogs: LogItem[] = res.data.logs || []
        setLogs(newLogs)
        if (newLogs.length > 0) {
          lastLogCounter.current = newLogs[newLogs.length - 1].counter || 0
        }
      }
    } catch (e: any) {
      // 忽略取消的请求错误
      if (axios.isCancel(e) || e.name === 'AbortError' || e.code === 'ERR_CANCELED') {
        return
      }
      showNote(t('page.terminal.msg.load_logs_failed'), 'error')
    } finally {
      setIsLoading(false)
      setInitialLoadComplete(true)
    }
  }

  const fetchNewLogs = async (signal?: AbortSignal) => {
    // Prevent fetching if we are already loading initial logs
    if (isLoading) return

    try {
      const res = await axios.get('/api/new_logs', {
        params: {
          last_counter: lastLogCounter.current,
          max_lines: 100
        },
        signal
      })

      if (res.data.status === 'success' && res.data.new_logs_count > 0) {
        const newItems: LogItem[] = res.data.logs
        if (newItems.length === 0) return

        // Filter duplicates using functional update to avoid stale closure
        setLogs(prev => {
          const currentCounters = new Set(prev.slice(-200).map(l => l.counter))
          const uniqueNew = newItems.filter(l => l.counter === undefined || !currentCounters.has(l.counter))

          if (uniqueNew.length > 0) {
            const combined = [...prev, ...uniqueNew]
            lastLogCounter.current = res.data.last_counter
            return combined.length > MAX_LOGS ? combined.slice(combined.length - MAX_LOGS) : combined
          }
          return prev
        })
      }
    } catch (e: any) {
      // 忽略取消的请求错误
      if (axios.isCancel(e) || e.name === 'AbortError' || e.code === 'ERR_CANCELED') {
        return
      }
      console.error('Error fetching new logs', e)
    }
  }

  const sendCommand = async () => {
    const cmd = commandInput.trim()
    if (!cmd) return

    // Forbidden commands check
    const forbidden = ['!!MCDR plugin reload guguwebui', '!!MCDR plugin unload guguwebui', 'stop']
    if (forbidden.includes(cmd)) {
      showNote(t('page.terminal.msg.forbidden_command'), 'error')
      return
    }

    try {
      const res = await axios.post('/api/send_command', { command: cmd })
      if (res.data.status === 'success') {
        // Update History
        setCommandHistory(prev => {
          const newHist = [cmd, ...prev.filter(c => c !== cmd)].slice(0, 50)
          localStorage.setItem('commandHistory', JSON.stringify(newHist))
          return newHist
        })
        setHistoryIndex(-1)
        setCommandInput('')
        // Show feedback if available, otherwise just show success message
        const feedback = res.data.feedback || res.data.message || ''
        if (feedback) {
          showNote(`${t('page.terminal.msg.command_sent_prefix')}${feedback}`, 'success')
        } else {
          showNote(t('page.terminal.msg.command_sent'), 'success')
        }
      } else {
        showNote(res.data.message || t('page.terminal.msg.send_failed'), 'error')
      }
    } catch (e) {
      showNote(t('page.terminal.msg.send_failed'), 'error')
    }
  }

  const fetchSuggestions = async (input: string) => {
    if (!input.startsWith('!!')) {
      setSuggestions([])
      setShowSuggestions(false)
      return
    }

    // Debounce handled by caller or simple timer here
    try {
      const res = await axios.get('/api/command_suggestions', { params: { input } })
      if (res.data.status === 'success') {
        const list = res.data.suggestions || []
        setSuggestions(list)
        setShowSuggestions(list.length > 0)
        setSelectedSuggestionIndex(0) // Reset selection
        // Reset refs array when suggestions change
        suggestionItemRefs.current = []
      }
    } catch (e) {
      // ignore errors for suggestions
    }
  }

  // --- Event Handlers ---

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value
    setCommandInput(val)

    if (suggestionTimerRef.current) clearTimeout(suggestionTimerRef.current)
    suggestionTimerRef.current = setTimeout(() => fetchSuggestions(val), 300)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    // Suggestions Navigation
    if (showSuggestions && suggestions.length > 0) {
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSelectedSuggestionIndex(prev => (prev - 1 + suggestions.length) % suggestions.length)
        return
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSelectedSuggestionIndex(prev => (prev + 1) % suggestions.length)
        return
      }
      if (e.key === 'Tab' || e.key === 'Enter') {
        e.preventDefault()
        applySuggestion(suggestions[selectedSuggestionIndex])
        return
      }
      if (e.key === 'Escape') {
        setShowSuggestions(false)
        return
      }
    }

    // History Navigation
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      if (historyIndex === -1) setHistoryTemp(commandInput)

      if (historyIndex < commandHistory.length - 1) {
        const nextIdx = historyIndex + 1
        setHistoryIndex(nextIdx)
        setCommandInput(commandHistory[nextIdx])
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (historyIndex > 0) {
        const nextIdx = historyIndex - 1
        setHistoryIndex(nextIdx)
        setCommandInput(commandHistory[nextIdx])
      } else if (historyIndex === 0) {
        setHistoryIndex(-1)
        setCommandInput(historyTemp)
      }
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (!showSuggestions) sendCommand()
    } else if (e.key === 'Tab') {
      e.preventDefault() // prevent focus loss
      if (commandInput.startsWith('!!')) {
        fetchSuggestions(commandInput)
      }
    }
  }

  const applySuggestion = (sugg: CommandSuggestion) => {
    if (!sugg) return
    // Simple logic: if suggestion has <args>, keep text before <
    let newVal = sugg.command
    if (sugg.command.includes('<') && sugg.command.includes('>')) {
      newVal = sugg.command.split('<')[0].trim()
    }
    setCommandInput(newVal)
    setShowSuggestions(false)
  }

  // --- AI Logic ---

  const openAIModal = () => {
    // Clear previous session if it's a fresh open
    if (!showAIModal) {
      setAiChatHistory([])
    }

    setShowAIModal(true)
    // Force reset input
    setAiQuery('')
  }

  const submitAiQuery = async () => {
    if (aiLoading) return
    setAiLoading(true)

    const query = aiQuery.trim() || t('page.terminal.msg.default_ai_query')
    const context = selectedText || logs.slice(-200).map(l => l.content).join('\n')

    try {
      // Deepseek (Self-hosted proxy in backend)
      const payload: any = {
        query: `${query}\n\nContext Logs:\n${context}`,
        system_prompt: t('page.terminal.msg.system_prompt'),
      }
      if (aiChatHistory.length > 0) {
        payload.chat_history = aiChatHistory
      }

      const res = await axios.post('/api/deepseek', payload)
      if (res.data.status === 'success') {
        const answer = res.data.answer
        setAiChatHistory(prev => [
          ...prev,
          { role: 'user', content: query },
          { role: 'assistant', content: answer }
        ].slice(-10))
      } else {
        const errorMsg = `Error: ${res.data.message}`
        setAiChatHistory(prev => [
          ...prev,
          { role: 'user', content: query },
          { role: 'assistant', content: errorMsg }
        ].slice(-10))
      }
    } catch (e: any) {
      const errorMsg = `Request Failed: ${e.message}`
      setAiChatHistory(prev => [
        ...prev,
        { role: 'user', content: query },
        { role: 'assistant', content: errorMsg }
      ].slice(-10))
    } finally {
      setAiLoading(false)
    }
  }

  // --- Render Helpers ---

  const getLogClass = (content: string) => {
    if (content.includes('INFO') || content.includes('[I]')) return 'text-slate-300' // Default/Info
    if (content.includes('WARN') || content.includes('[W]')) return 'text-amber-400'
    if (content.includes('ERROR') || content.includes('[E]')) return 'text-rose-500 font-bold'
    if (content.includes('SUCCESS')) return 'text-emerald-400'
    if (content.includes('Command')) return 'text-blue-400'
    if (content.match(/<\w+>/)) return 'text-purple-300' // User names etc?
    return 'text-slate-400'
  }

  return (
    <div className="h-[calc(100vh-8rem)] flex flex-col gap-4 animate-in fade-in slide-in-from-bottom-4 duration-500">

      {/* Header / Config Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-white dark:bg-slate-900 p-3 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm shrink-0">
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-xl text-white shadow-lg shadow-purple-500/20 transition-all ${serverStatus === 'online' ? 'bg-emerald-500' : serverStatus === 'offline' ? 'bg-rose-500' : 'bg-amber-500'}`}>
            <TerminalIcon size={20} />
          </div>
          <div>
            <h2 className="font-bold text-slate-900 dark:text-white flex items-center gap-2">
              {t('nav.terminal')}
              {serverVersion && <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500 font-mono">{serverVersion}</span>}
            </h2>
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <span className={`w-2 h-2 rounded-full ${serverStatus === 'online' ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400'}`} />
              <span className="uppercase">
                {serverStatus === 'online'
                  ? t('nav.status_online')
                  : serverStatus === 'offline'
                    ? t('nav.status_offline')
                    : serverStatus === 'loading'
                      ? t('nav.status_loading')
                      : serverStatus === 'error'
                        ? t('nav.status_error')
                        : serverStatus}
              </span>
              {isLoading && <Loader2 size={12} className="animate-spin ml-1" />}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setAutoScroll(!autoScroll)}
            className={`flex items-center gap-2 px-3 py-2 rounded-lg border transition-all ${autoScroll ? 'bg-blue-50 dark:bg-blue-900/30 border-blue-200 dark:border-blue-800 text-blue-600 dark:text-blue-400' : 'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-400'}`}
            title={t('page.terminal.tooltip.auto_scroll')}
          >
            <ArrowDown size={18} />
            <span className="hidden sm:inline text-xs font-medium">{t('page.terminal.tooltip.auto_scroll')}</span>
          </button>
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`flex items-center gap-2 px-3 py-2 rounded-lg border transition-all ${autoRefresh ? 'bg-emerald-50 dark:bg-emerald-900/30 border-emerald-200 dark:border-emerald-800 text-emerald-600 dark:text-emerald-400' : 'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-400'}`}
            title={t('page.terminal.tooltip.auto_refresh')}
          >
            <RotateCcw size={18} className={autoRefresh ? 'animate-spin-slow' : ''} />
            <span className="hidden sm:inline text-xs font-medium">{t('page.terminal.tooltip.auto_refresh')}</span>
          </button>

          <div className="h-6 w-px bg-slate-200 dark:bg-slate-700 mx-1" />

          <button
            onClick={() => {
              const text = logs.map(l => l.content).join('\n')
              navigator.clipboard.writeText(text)
              showNote(t('page.terminal.msg.copy_success'))
            }}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-500 hover:text-blue-500 hover:border-blue-300 transition-all"
            title={t('page.terminal.tooltip.copy_logs')}
          >
            <Copy size={18} />
            <span className="hidden sm:inline text-xs font-medium">{t('page.terminal.tooltip.copy_logs')}</span>
          </button>
          <button
            onClick={() => setLogs([])}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-500 hover:text-rose-500 hover:border-rose-300 transition-all"
            title={t('page.terminal.tooltip.clear_terminal')}
          >
            <Trash2 size={18} />
            <span className="hidden sm:inline text-xs font-medium">{t('page.terminal.tooltip.clear_terminal')}</span>
          </button>

          <div className="h-6 w-px bg-slate-200 dark:bg-slate-700 mx-1" />

          <button
            onClick={openAIModal}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gradient-to-r from-purple-600 to-indigo-600 text-white font-bold text-sm shadow-md shadow-purple-500/20 hover:shadow-lg hover:scale-105 transition-all"
          >
            <BrainCircuit size={18} />
            <span className="hidden sm:inline">{t('page.terminal.ai_modal.title')}</span>
          </button>
          <button
            onClick={() => setShowApiKeyModal(true)}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-500 hover:text-slate-900 dark:hover:text-white transition-all"
            title={t('page.terminal.tooltip.ai_settings')}
          >
            <Settings size={18} />
            <span className="hidden sm:inline text-xs font-medium">{t('page.terminal.tooltip.ai_settings')}</span>
          </button>
        </div>
      </div>

      {/* Terminal Area */}
      <div className="flex-1 relative bg-[#0c0c0c] rounded-2xl border border-slate-800 shadow-inner overflow-hidden flex flex-col font-mono text-sm leading-relaxed group">
        <div
          ref={terminalContainerRef}
          className="flex-1 overflow-y-auto p-4 space-y-0.5 custom-scrollbar scroll-smooth"
        >
          {logs.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-slate-600 gap-3 opacity-50">
              <TerminalIcon size={48} />
              <p>{t('page.terminal.empty')}</p>
            </div>
          ) : (
            logs.map((log, idx) => (
              <div key={`${log.counter || idx}-${log.time}`} className={`break-words whitespace-pre-wrap ${getLogClass(log.content)} hover:bg-white/5`}>
                <span className="select-none opacity-30 mr-3 text-xs w-8 inline-block text-right">{log.line_number || idx + 1}</span>
                {log.content}
              </div>
            ))
          )}
          <div ref={logsEndRef} />
        </div>

        {/* Input Area */}
        <div className="p-3 bg-[#151515] border-t border-slate-800 flex gap-0 relative z-20">
          {showSuggestions && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="absolute bottom-full left-3 mb-2 w-96 max-w-[90vw] bg-slate-800 border border-slate-700 rounded-lg shadow-xl overflow-hidden flex flex-col z-50 max-h-60"
            >
              <div className="px-3 py-2 bg-slate-900/50 border-b border-slate-700 text-xs text-slate-400 font-bold flex justify-between">
                <span>{t('page.terminal.suggestions.title')}</span>
                <span className="text-[10px] opacity-60">{t('page.terminal.suggestions.hint')}</span>
              </div>
              <div ref={suggestionsContainerRef} className="overflow-y-auto p-1">
                {suggestions.map((s, i) => (
                  <button
                    key={i}
                    ref={(el) => {
                      suggestionItemRefs.current[i] = el
                    }}
                    onClick={() => applySuggestion(s)}
                    className={`w-full text-left px-3 py-2 text-sm font-mono flex items-center justify-between rounded ${i === selectedSuggestionIndex ? 'bg-purple-600 text-white' : 'text-slate-300 hover:bg-slate-700'}`}
                  >
                    <span>{s.command}</span>
                    {s.description && <span className="text-xs opacity-50 truncate ml-4 max-w-[50%]">{s.description}</span>}
                  </button>
                ))}
              </div>
            </motion.div>
          )}

          <div className="flex-1 relative flex items-center bg-[#0c0c0c] border border-slate-700 focus-within:border-purple-500 rounded-l-lg transition-colors">
            <span className="pl-3 pr-2 text-emerald-500 font-bold select-none">{'>'}</span>
            <input
              type="text"
              value={commandInput}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              className="w-full bg-transparent border-none focus:ring-0 text-slate-200 placeholder-slate-600 h-10 font-mono outline-none"
              placeholder={t('page.terminal.placeholder')}
              autoComplete="off"
              spellCheck="false"
            />
          </div>
          <button
            onClick={sendCommand}
            className="bg-purple-600 hover:bg-purple-700 text-white px-6 rounded-r-lg font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            disabled={!commandInput.trim()}
          >
            {t('common.send')}
          </button>
        </div>

        {/* Floating Action Button for Selection */}
        <AnimatePresence>
          {selectionButtonPos && (
            <motion.button
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0, opacity: 0 }}
              style={{
                position: 'fixed',
                left: selectionButtonPos.x,
                top: selectionButtonPos.y,
                transform: 'translateX(-50%)'
              }}
              className="z-50 bg-slate-900 border border-slate-700 text-white px-3 py-1.5 rounded-full shadow-2xl flex items-center gap-2 hover:bg-purple-600 hover:border-purple-500 transition-all cursor-pointer"
              onMouseDown={(e) => {
                e.preventDefault()
                e.stopPropagation() // prevent selection clear
                // openAIModal(selectedText)
                openAIModal()
                setSelectionButtonPos(null) // hide formatting
              }}
            >
              <Sparkles size={14} className="text-yellow-400" />
              <span className="text-xs font-bold whitespace-nowrap">{t('page.terminal.selection.ask_ai')}</span>
            </motion.button>
          )}
        </AnimatePresence>
      </div>

      {/* AI Modal */}
      <Modal isOpen={showAIModal} onClose={() => setShowAIModal(false)} title={t('page.terminal.ai_modal.title')} maxWidth="max-w-3xl">
        <div className="space-y-4">
          <div className="flex gap-2 mb-2 p-1 bg-slate-100 dark:bg-slate-800 rounded-lg w-fit text-xs font-bold text-purple-600 dark:text-purple-400">
            {t('page.terminal.ai_modal.mode_api')}
          </div>

          {!hasApiKey && (
            <div className="bg-amber-50 dark:bg-amber-900/20 text-amber-600 dark:text-amber-400 p-3 rounded-lg text-sm flex items-center gap-2">
              <AlertTriangle size={16} />
              <span>{t('page.terminal.ai_modal.api_unconfigured_warning')}</span>
              <button onClick={() => setShowApiKeyModal(true)} className="underline hover:text-amber-700">
                {t('page.terminal.ai_modal.api_configure_now')}
              </button>
            </div>
          )}

          {/* Context preview */}
          {showAIModal && (
            <div className="bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800 rounded-xl p-3 text-xs text-slate-600 dark:text-slate-300 max-h-40 overflow-y-auto">
              <div className="font-semibold mb-2">
                {t('page.terminal.ai_modal.context_title')}
              </div>
              <pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-snug opacity-90">
                {(selectedText || logs.slice(-200).map(l => l.content).join('\n'))}
              </pre>
            </div>
          )}

          <div className="h-64 overflow-y-auto bg-slate-50 dark:bg-slate-950/50 rounded-xl p-4 border border-slate-200 dark:border-slate-800 flex flex-col gap-3">
            {/* Chat history */}
            {aiChatHistory.map((msg, i) => (
              <div key={i} className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${msg.role === 'user' ? 'bg-slate-200 dark:bg-slate-800' : 'bg-purple-100 dark:bg-purple-900/30 text-purple-600'}`}>
                  {msg.role === 'user' ? <User size={16} /> : <Bot size={16} />}
                </div>
                <div className={`p-3 rounded-2xl text-sm max-w-[80%] ${msg.role === 'user' ? 'bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 rounded-tr-none' : 'bg-white dark:bg-slate-900 border border-slate-100 dark:border-slate-800 shadow-sm rounded-tl-none'}`}>
                  <div className="markdown-body prose prose-invert max-w-none">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      rehypePlugins={[rehypeRaw]}
                    >
                      {msg.content}
                    </ReactMarkdown>
                  </div>
                </div>
              </div>
            ))}

            {aiLoading && (
              <div className="flex gap-3">
                <div className="w-8 h-8 rounded-full bg-purple-100 dark:bg-purple-900/30 text-purple-600 flex items-center justify-center shrink-0 animate-pulse">
                  <Bot size={16} />
                </div>
                <div className="p-3 bg-gray-50 dark:bg-slate-800/50 rounded-2xl rounded-tl-none flex items-center gap-2">
                  <Loader2 size={16} className="animate-spin text-purple-500" />
                  <span className="text-xs text-slate-500">{t('page.terminal.ai_modal.thinking')}</span>
                </div>
              </div>
            )}
          </div>

          <div className="flex gap-2">
            <input
              type="text"
              value={aiQuery}
              onChange={(e) => setAiQuery(e.target.value)}
              placeholder={t('page.terminal.ai_modal.input_placeholder')}
              className="flex-1 bg-slate-100 dark:bg-slate-800 border-transparent focus:border-purple-500 focus:bg-white dark:focus:bg-slate-900 rounded-xl px-4 text-sm"
              onKeyDown={(e) => e.key === 'Enter' && submitAiQuery()}
            />
            <button
              onClick={submitAiQuery}
              disabled={aiLoading}
              className="bg-purple-600 hover:bg-purple-700 text-white p-3 rounded-xl disabled:opacity-50 transition-colors"
            >
              <Send size={18} />
            </button>
          </div>
        </div>
      </Modal>

      {/* API Key Modal */}
      <Modal isOpen={showApiKeyModal} onClose={() => setShowApiKeyModal(false)} title={t('page.terminal.ai_modal.settings')}>
        <div className="space-y-4">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {t('page.terminal.ai_modal.settings_desc')}
          </p>
          <div>
            <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
              {t('page.terminal.ai_modal.api_key_label')}
            </label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              className="w-full bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm font-mono"
              placeholder={t('page.terminal.ai_modal.api_key_placeholder')}
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button onClick={() => setShowApiKeyModal(false)} className="px-4 py-2 text-sm text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg font-medium">{t('common.cancel')}</button>
            <button
              onClick={async () => {
                try {
                  const res = await axios.post('/api/save_web_config', { action: 'config', ai_api_key: apiKey.trim() })
                  if (res.data.status === 'success') {
                    showNote(t('page.terminal.ai_modal.save_success'), 'success')
                    setHasApiKey(true)
                    setShowApiKeyModal(false)
                  } else {
                    showNote(t('page.terminal.ai_modal.save_failed'), 'error')
                  }
                } catch (e) {
                  showNote(t('page.terminal.ai_modal.save_error'), 'error')
                }
              }}
              className="px-4 py-2 text-sm bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-bold shadow-md shadow-purple-500/20"
            >
              {t('common.save')}
            </button>
          </div>
        </div>
      </Modal>

      {/* Global Notification Toast */}
      <AnimatePresence>
        {notification && (
          <motion.div
            initial={{ opacity: 0, y: 50, x: '-50%' }}
            animate={{ opacity: 1, y: 0, x: '-50%' }}
            exit={{ opacity: 0, y: 50, x: '-50%' }}
            className={`fixed bottom-6 left-1/2 z-[100] px-4 py-2 rounded-full shadow-lg border flex items-center gap-2 text-sm font-medium ${notification.type === 'error' ? 'bg-white dark:bg-slate-900 border-rose-200 text-rose-600' :
                notification.type === 'success' ? 'bg-white dark:bg-slate-900 border-emerald-200 text-emerald-600' :
                  'bg-white dark:bg-slate-900 border-slate-200 text-slate-600'
              }`}
          >
            {notification.type === 'error' ? <AlertTriangle size={16} /> : <div className="w-2 h-2 rounded-full bg-current" />}
            {notification.msg}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// Simple Modal Component (Internal)
const Modal: React.FC<{
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  maxWidth?: string;
}> = ({ isOpen, onClose, title, children, maxWidth = 'max-w-md' }) => {
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
      />
      <motion.div
        initial={{ scale: 0.95, opacity: 0, y: 20 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={{ scale: 0.95, opacity: 0, y: 20 }}
        className={`relative bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-800 w-full ${maxWidth} p-6 overflow-y-auto max-h-[85vh]`}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xl font-bold text-slate-900 dark:text-white line-clamp-1">{title}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1.5 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">
            <X size={20} />
          </button>
        </div>
        {children}
      </motion.div>
    </div>
  );
};

export default Terminal
