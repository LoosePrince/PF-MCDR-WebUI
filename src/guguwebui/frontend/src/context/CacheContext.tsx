import React, { createContext, useContext, useState, useCallback, ReactNode } from 'react'

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
  const [cache, setCache] = useState<Map<string, CacheItem<any>>>(new Map())

  const get = useCallback(<T,>(key: string): T | null => {
    const item = cache.get(key)
    if (!item) {
      return null
    }

    // 检查是否过期
    if (item.ttl !== undefined) {
      const elapsed = Date.now() - item.timestamp
      if (elapsed > item.ttl) {
        // 缓存已过期，删除
        setCache(prev => {
          const newCache = new Map(prev)
          newCache.delete(key)
          return newCache
        })
        return null
      }
    }

    return item.data as T
  }, [cache])

  const set = useCallback(<T,>(key: string, data: T, ttl?: number): void => {
    setCache(prev => {
      const newCache = new Map(prev)
      newCache.set(key, {
        data,
        timestamp: Date.now(),
        ttl
      })
      return newCache
    })
  }, [])

  const invalidate = useCallback((key: string): void => {
    setCache(prev => {
      const newCache = new Map(prev)
      newCache.delete(key)
      return newCache
    })
  }, [])

  const clear = useCallback((): void => {
    setCache(new Map())
  }, [])

  return (
    <CacheContext.Provider value={{ get, set, invalidate, clear }}>
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
