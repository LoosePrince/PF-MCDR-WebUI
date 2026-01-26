import { useState, useEffect } from 'react'
import axios from 'axios'

const API_BASE = '/api'

export function useAuth() {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null)
  const [username, setUsername] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    checkLoginStatus()
  }, [])

  const checkLoginStatus = async () => {
    try {
      const response = await axios.get(`${API_BASE}/checkLogin`)
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

      const response = await axios.post(`${API_BASE}/login`, formData, {
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
        message: error.response?.data?.message || '登录失败',
      }
    }
  }

  const logout = async () => {
    try {
      await axios.get('/logout')
      setIsAuthenticated(false)
      setUsername(null)
      window.location.href = '/login'
    } catch (error) {
      console.error('Logout error:', error)
    }
  }

  return {
    isAuthenticated,
    username,
    loading,
    login,
    logout,
    checkLoginStatus,
  }
}
