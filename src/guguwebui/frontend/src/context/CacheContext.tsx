import React, { createContext, useContext, useRef, useCallback, ReactNode, useMemo } from 'react'

interface CacheItem<T> {
  data: T
  timestamp: number
  ttl?: number // 生存时间（毫秒），undefined表示永久缓存
}

interface CacheContextType {
  get<T>(key: string): T | null
  set<T>(key: string, data: T, ttl?: number): void
  invalidate(key: string): void
  clear(): void
}

const CacheContext = createContext<CacheContextType | undefined>(undefined)

export const CacheProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const cacheRef = useRef<Map<string, CacheItem<any>>>(new Map())

  const get = useCallback(<T,>(key: string): T | null => {
    const item = cacheRef.current.get(key)
    if (!item) {
      return null
    }

    // 检查是否过期
    if (item.ttl !== undefined) {
      const elapsed = Date.now() - item.timestamp
      if (elapsed > item.ttl) {
        // 缓存已过期，删除
        cacheRef.current.delete(key)
        return null
      }
    }

    return item.data as T
  }, [])

  const set = useCallback(<T,>(key: string, data: T, ttl?: number): void => {
    cacheRef.current.set(key, {
      data,
      timestamp: Date.now(),
      ttl
    })
  }, [])

  const invalidate = useCallback((key: string): void => {
    cacheRef.current.delete(key)
  }, [])

  const clear = useCallback((): void => {
    cacheRef.current.clear()
  }, [])

  const value = useMemo(() => ({ get, set, invalidate, clear }), [get, set, invalidate, clear])

  return (
    <CacheContext.Provider value={value}>
      {children}
    </CacheContext.Provider>
  )
}

export const useCache = (): CacheContextType => {
  const context = useContext(CacheContext)
  if (!context) {
    throw new Error('useCache must be used within a CacheProvider')
  }
  return context
}
