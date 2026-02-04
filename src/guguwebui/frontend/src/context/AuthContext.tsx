import React, { createContext, useState, useEffect, useContext } from 'react'
import api, { getBasePath } from '../utils/api'

interface AuthContextType {
  isAuthenticated: boolean | null
  username: string | null
  loading: boolean
  login: (account: string, password: string, remember?: boolean) => Promise<{ success: boolean; message?: string }>
  logout: () => Promise<void>
  checkLoginStatus: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null)
  const [username, setUsername] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    checkLoginStatus()
  }, [])

  const checkLoginStatus = async () => {
    try {
      const response = await api.get('/checkLogin')
      if (response.data.status === 'success') {
        setIsAuthenticated(true)
        setUsername(response.data.username)
      } else {
        setIsAuthenticated(false)
        setUsername(null)
      }
    } catch (error) {
      setIsAuthenticated(false)
      setUsername(null)
    } finally {
      setLoading(false)
    }
  }

  const login = async (account: string, password: string, remember: boolean = false) => {
    try {
      const formData = new FormData()
      formData.append('account', account)
      formData.append('password', password)
      formData.append('remember', remember.toString())

      const response = await api.post('/login', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      })

      if (response.data.status === 'success') {
        setIsAuthenticated(true)
        setUsername(account)
        return { success: true }
      } else {
        return { success: false, message: response.data.message }
      }
    } catch (error: any) {
      return {
        success: false,
        message: error.response?.data?.message || undefined,
      }
    }
  }

    const logout = async () => {
    try {
      // 通过后端 API 主动注销，支持独立模式与挂载模式
      await api.post('/logout')
    } catch (error) {
      console.error('Logout error:', error)
    } finally {
      // 无论后端是否成功，前端都先清理本地登录状态并跳转登录页
      setIsAuthenticated(false)
      setUsername(null)
      // 清除所有可能的 cookie (前端尝试)
      const cookieNames = ['token', 'session'];
      const domains = [window.location.hostname, ''];
      const paths = [getBasePath() || '/', '/', '/guguwebui', '/guguwebui/'];
      
      cookieNames.forEach(name => {
        paths.forEach(path => {
          domains.forEach(domain => {
            document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=${path};${domain ? ` domain=${domain};` : ''}`;
          });
        });
      });

      window.location.href = getBasePath() + '/login'
    }
  }

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated,
        username,
        loading,
        login,
        logout,
        checkLoginStatus,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export const useAuthContext = () => {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuthContext must be used within an AuthProvider')
  }
  return context
}
