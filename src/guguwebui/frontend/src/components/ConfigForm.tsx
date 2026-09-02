import React from 'react'

export type GenericConfigObject = Record<string, unknown>
export type ConfigTranslationTree = Record<string, unknown>

type ConfigFormProps = {
  data: GenericConfigObject
  onChange: (data: GenericConfigObject) => void
  translations?: ConfigTranslationTree
  parentPath?: string
  lang: string
}

export const ConfigForm: React.FC<ConfigFormProps> = ({ data, onChange, translations, parentPath = '', lang }) => {
  if (!data || typeof data !== 'object' || data.type === 'html') return null

  const getTranslation = (key: string) => {
    if (!translations) return { name: key, desc: '' }

    const languageAlternative = lang.replace('-', '_').toLowerCase()
    const translationMap = ((translations as { translations?: Record<string, unknown> }).translations) || {}
    const languageEntries = (translationMap[lang] as Record<string, unknown> | undefined) ||
      (translationMap[languageAlternative] as Record<string, unknown> | undefined) ||
      (translationMap['zh-CN'] as Record<string, unknown> | undefined) ||
      (translationMap.zh_cn as Record<string, unknown> | undefined) ||
      (translationMap['en-US'] as Record<string, unknown> | undefined) ||
      (translationMap.en_us as Record<string, unknown> | undefined) ||
      (Object.values(translationMap)[0] as Record<string, unknown> | undefined) || {}

    const pathParts = (parentPath ? `${parentPath}.${key}` : key).split('.').filter(Boolean)
    let cursor: Record<string, unknown> = languageEntries
    for (let index = 0; index < pathParts.length; index += 1) {
      const node = cursor[pathParts[index]] as Record<string, unknown> | undefined
      if (!node) break
      if (index === pathParts.length - 1) {
        return {
          name: typeof node.name === 'string' ? node.name : key,
          desc: typeof node.desc === 'string' ? node.desc : '',
        }
      }
      cursor = (node.children as Record<string, unknown> | undefined) || {}
    }
    return { name: key, desc: '' }
  }

  const updateValue = (key: string, value: unknown) => onChange({ ...data, [key]: value })

  return (
    <div className="space-y-4">
      {Object.entries(data).map(([key, value]) => {
        const { name, desc } = getTranslation(key)
        if (typeof value === 'boolean') {
          return <div key={key} className="space-y-2 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900"><div className="flex items-center justify-between gap-3"><span className="text-sm font-medium text-slate-700 dark:text-slate-300">{name}</span><button type="button" onClick={() => updateValue(key, !value)} className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${value ? 'bg-blue-600' : 'bg-slate-300 dark:bg-slate-700'}`}><span className={`inline-block h-4 w-4 rounded-full bg-white transition-transform ${value ? 'translate-x-6' : 'translate-x-1'}`} /></button></div>{desc && <p className="text-xs text-slate-500">{desc}</p>}</div>
        }
        if (typeof value === 'string' || typeof value === 'number') {
          return <div key={key} className="space-y-1"><label className="ml-1 text-xs font-bold uppercase text-slate-500">{name}</label>{desc && <p className="mb-1 ml-1 text-[10px] text-slate-400">{desc}</p>}<input type={typeof value === 'number' ? 'number' : 'text'} value={value} onChange={(event) => updateValue(key, typeof value === 'number' ? Number(event.target.value) : event.target.value)} className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm outline-none transition-all focus:ring-2 focus:ring-blue-500/50 dark:border-slate-800 dark:bg-slate-900" /></div>
        }
        if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
          return <div key={key} className="space-y-2"><label className="ml-1 text-xs font-bold uppercase text-slate-500">{name}</label>{desc && <p className="ml-1 text-[10px] text-slate-400">{desc}</p>}<div className="ml-1 border-l-2 border-slate-100 pl-4 dark:border-slate-800"><ConfigForm data={value as GenericConfigObject} onChange={(nextValue) => updateValue(key, nextValue)} translations={translations} parentPath={parentPath ? `${parentPath}.${key}` : key} lang={lang} /></div></div>
        }
        return null
      })}
    </div>
  )
}
