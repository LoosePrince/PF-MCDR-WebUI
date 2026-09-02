import { Loader2 } from 'lucide-react'
import React, { useEffect, useState } from 'react'

type CodeMirrorEditorProps = {
  value: string
  onChange: (value: string) => void
  theme: 'light' | 'dark'
  height?: string
}

export const CodeMirrorEditor: React.FC<CodeMirrorEditorProps> = ({ value, onChange, theme, height = '400px' }) => {
  const [CodeMirror, setCodeMirror] = useState<unknown>(null)
  const [jsonLang, setJsonLang] = useState<(() => unknown) | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      import('@uiw/react-codemirror'),
      import('@codemirror/lang-json'),
    ]).then(([codemirrorModule, jsonModule]) => {
      setCodeMirror(() => codemirrorModule.default)
      setJsonLang(() => jsonModule.json)
      setLoading(false)
    })
  }, [])

  if (loading || !CodeMirror || !jsonLang) {
    return <div className="flex h-[400px] items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-blue-500" /></div>
  }

  const CodeMirrorComponent = CodeMirror as React.ComponentType<{
    value: string
    height?: string
    extensions?: unknown[]
    theme?: string
    onChange?: (value: string) => void
  }>

  return <CodeMirrorComponent value={value} height={height} extensions={[jsonLang()]} theme={theme} onChange={onChange} />
}
