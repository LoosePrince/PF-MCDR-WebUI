import { useEffect, useMemo, useState } from 'react'

export type ThemeMode = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'guguwebui-theme'

function getSystemPrefersDark() {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
}

function computeIsDark(mode: ThemeMode) {
  if (mode === 'dark') return true
  if (mode === 'light') return false
  return getSystemPrefersDark()
}

function applyThemeClass(isDark: boolean) {
  document.documentElement.classList.toggle('dark', isDark)
  // 让表单/滚动条等原生控件也跟随，减少“半亮半暗”观感
  document.documentElement.style.colorScheme = isDark ? 'dark' : 'light'
}

export function useTheme() {
  const [mode, setMode] = useState<ThemeMode>(() => {
    const saved = localStorage.getItem(STORAGE_KEY) as ThemeMode | null
    return saved === 'light' || saved === 'dark' || saved === 'system' ? saved : 'system'
  })

  // 首屏脚本已提前写入 html，React 这里直接以当前 DOM 为准，避免二次抖动
  const [isDark, setIsDark] = useState<boolean>(() => document.documentElement.classList.contains('dark'))

  useEffect(() => {
    const nextIsDark = computeIsDark(mode)
    setIsDark(nextIsDark)
    applyThemeClass(nextIsDark)
    localStorage.setItem(STORAGE_KEY, mode)
  }, [mode])

  // 跟随系统模式时，监听系统主题变化
  useEffect(() => {
    if (mode !== 'system') return

    const mql = window.matchMedia?.('(prefers-color-scheme: dark)')
    if (!mql) return

    const handler = () => {
      const nextIsDark = computeIsDark('system')
      setIsDark(nextIsDark)
      applyThemeClass(nextIsDark)
    }

    // 现代浏览器：MediaQueryList change 事件
    mql.addEventListener('change', handler)
    return () => mql.removeEventListener('change', handler)
  }, [mode])

  const label = useMemo(() => {
    if (mode === 'system') return '跟随系统'
    return mode === 'dark' ? '深色' : '浅色'
  }, [mode])

  const cycle = () => {
    setMode((prev) => (prev === 'system' ? 'light' : prev === 'light' ? 'dark' : 'system'))
  }

  return { mode, setMode, isDark, label, cycle }
}

