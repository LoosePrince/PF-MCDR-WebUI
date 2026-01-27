import React, { useEffect, useState } from 'react'
import axios from 'axios'

interface VersionFooterProps {
  className?: string
}

const VersionFooter: React.FC<VersionFooterProps> = ({ className = '' }) => {
  const [version, setVersion] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    const fetchVersion = async () => {
      try {
        const { data } = await axios.get('/api/plugins', {
          params: { plugin_id: 'guguwebui' },
        })
        if (cancelled) return
        const plugins = Array.isArray(data.plugins) ? data.plugins : []
        const webui = plugins[0]
        if (webui && webui.version) {
          setVersion(webui.version)
        }
      } catch {
        if (!cancelled) {
          setVersion(null)
        }
      }
    }

    fetchVersion()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <p className={`text-xs text-slate-400 dark:text-slate-600 font-medium ${className}`}>
      {version ? `GUGUWebUI v${version}` : 'GUGUWebUI'}
    </p>
  )
}

export default VersionFooter

