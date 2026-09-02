import { Boxes } from 'lucide-react'
import React, { useState } from 'react'
import api from '../utils/api'

type ModIconMetadata = {
  filename: string
  has_icon?: boolean
}

export const ModIcon: React.FC<{ mod: ModIconMetadata; size?: 'small' | 'large' }> = ({ mod, size = 'small' }) => {
  const [failed, setFailed] = useState(false)
  const className = size === 'large' ? 'h-16 w-16' : 'h-9 w-9'
  const iconUrl = mod.has_icon && !failed ? `${api.defaults.baseURL}/mods/icon?filename=${encodeURIComponent(mod.filename)}` : ''

  if (iconUrl) {
    return <img src={iconUrl} alt="" onError={() => setFailed(true)} className={`${className} shrink-0 rounded-lg bg-slate-100 object-contain dark:bg-slate-800`} />
  }

  return <div className={`${className} flex shrink-0 items-center justify-center rounded-lg bg-blue-50 dark:bg-blue-900/20`}><Boxes className={size === 'large' ? 'h-8 w-8 text-blue-600' : 'h-5 w-5 text-blue-600'} /></div>
}
