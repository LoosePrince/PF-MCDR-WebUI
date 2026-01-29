import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './index.css'
import './i18n/config'
import { AuthProvider } from './context/AuthContext'
import { CacheProvider } from './context/CacheContext'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AuthProvider>
      <CacheProvider>
        <App />
      </CacheProvider>
    </AuthProvider>
  </React.StrictMode>,
)
