/**
 * RText (Raw JSON Text) 解析器 - TypeScript/React 版本
 * 支持Minecraft的文本组件格式，包括颜色、样式、点击事件、悬停事件等
 * 
 * 基于Minecraft Wiki: https://zh.minecraft.wiki/w/文本组件
 */

import React, { ReactNode } from 'react'

// Minecraft颜色映射
const COLORS: Record<string, string> = {
  'black': '#000000',
  'dark_blue': '#0000AA',
  'dark_green': '#00AA00',
  'dark_aqua': '#00AAAA',
  'dark_red': '#AA0000',
  'dark_purple': '#AA00AA',
  'gold': '#FFAA00',
  'gray': '#AAAAAA',
  'dark_gray': '#555555',
  'blue': '#5555FF',
  'green': '#55FF55',
  'aqua': '#55FFFF',
  'red': '#FF5555',
  'light_purple': '#FF55FF',
  'yellow': '#FFFF55',
  'white': '#FFFFFF'
}

// RText 组件类型定义
interface RTextComponent {
  text?: string
  translate?: string
  keybind?: string
  score?: {
    name?: string
    value?: number
  }
  selector?: string
  nbt?: string
  color?: string
  font?: string
  bold?: boolean
  italic?: boolean
  underlined?: boolean
  strikethrough?: boolean
  obfuscated?: boolean
  insertion?: string
  clickEvent?: {
    action: 'open_url' | 'run_command' | 'suggest_command' | 'change_page' | 'copy_to_clipboard'
    value: string
  }
  hoverEvent?: {
    action: 'show_text' | 'show_item' | 'show_entity'
    value: string | RTextComponent | RTextComponent[]
  }
  extra?: RTextComponent[]
}

type RTextData = string | RTextComponent | RTextComponent[]

interface ParseOptions {
  onCommandClick?: (command: string) => void
  onCommandSuggest?: (command: string) => void
}

/**
 * 解析颜色
 */
function parseColor(color: string): string {
  if (color.startsWith('#')) {
    return color
  }
  return COLORS[color] || color
}

/**
 * 处理本地化文本
 */
function handleTranslate(component: RTextComponent): string {
  return `[${component.translate}]`
}

/**
 * 处理记分板数据
 */
function handleScore(component: RTextComponent): string {
  const score = component.score!
  return `${score.name || 'Unknown'}: ${score.value || 0}`
}

/**
 * 处理实体选择器
 */
function handleSelector(component: RTextComponent): string {
  return `[@${component.selector}]`
}

/**
 * 处理NBT数据
 */
function handleNBT(component: RTextComponent): string {
  return `[NBT: ${component.nbt}]`
}

/**
 * 处理点击事件
 */
function handleClickEvent(
  clickEvent: RTextComponent['clickEvent'],
  options?: ParseOptions
): {
  onClick?: () => void
  style?: React.CSSProperties
  className?: string
} {
  if (!clickEvent) return {}

  const { action, value } = clickEvent

  switch (action) {
    case 'open_url':
      return {
        onClick: () => window.open(value, '_blank')
      }
    case 'run_command':
      return {
        onClick: () => {
          if (options?.onCommandClick) {
            options.onCommandClick(value)
          } else {
            console.log('执行命令:', value)
          }
        },
        style: { cursor: 'pointer' }
      }
    case 'suggest_command':
      return {
        onClick: () => {
          if (options?.onCommandSuggest) {
            options.onCommandSuggest(value)
          } else {
            console.log('建议命令:', value)
          }
        },
        style: { cursor: 'pointer' }
      }
    case 'change_page':
      return {
        onClick: () => {
          console.log('改变页面到:', value)
        },
        style: { cursor: 'pointer' }
      }
    case 'copy_to_clipboard':
      return {
        onClick: async () => {
          try {
            await navigator.clipboard.writeText(value)
            console.log('已复制到剪贴板:', value)
          } catch (err) {
            console.error('复制失败:', err)
          }
        },
        style: { cursor: 'pointer' }
      }
    default:
      return {}
  }
}

/**
 * 处理悬停事件
 */
function handleHoverEvent(
  hoverEvent: RTextComponent['hoverEvent']
): {
  title?: string
  'data-hover-content'?: string
} {
  if (!hoverEvent) return {}

  const { action, value } = hoverEvent

  switch (action) {
    case 'show_text':
      let text = ''
      if (typeof value === 'string') {
        text = value
      } else if (typeof value === 'object') {
        // 将 RText 组件转换为纯文本用于 title
        const textParts: string[] = []
        const extractText = (comp: RTextComponent | RTextComponent[]): void => {
          if (Array.isArray(comp)) {
            comp.forEach(c => extractText(c))
          } else {
            if (comp.text) textParts.push(comp.text)
            if (comp.extra) extractText(comp.extra)
          }
        }
        extractText(value as RTextComponent | RTextComponent[])
        text = textParts.join('')
      }
      return {
        title: text,
        'data-hover-content': text
      }
    case 'show_item':
      return {
        title: `物品: ${JSON.stringify(value)}`
      }
    case 'show_entity':
      return {
        title: `实体: ${JSON.stringify(value)}`
      }
    default:
      return {}
  }
}

/**
 * 解析单个 RText 组件为 React 元素
 */
function parseComponent(
  component: RTextComponent,
  parseCallback: (data: RTextData) => ReactNode,
  options?: ParseOptions
): ReactNode {
  // 处理文本内容
  let text = ''
  if (component.text !== undefined) {
    text = component.text
  } else if (component.translate !== undefined) {
    text = handleTranslate(component)
  } else if (component.keybind !== undefined) {
    text = `[${component.keybind}]`
  } else if (component.score !== undefined) {
    text = handleScore(component)
  } else if (component.selector !== undefined) {
    text = handleSelector(component)
  } else if (component.nbt !== undefined) {
    text = handleNBT(component)
  }

  // 构建样式
  const styles: React.CSSProperties = {}
  const classes: string[] = []

  // 处理颜色
  if (component.color) {
    styles.color = parseColor(component.color)
  }

  // 处理字体
  if (component.font) {
    styles.fontFamily = component.font
  }

  // 处理样式
  if (component.bold) styles.fontWeight = 'bold'
  if (component.italic) styles.fontStyle = 'italic'
  if (component.underlined) styles.textDecoration = 'underline'
  if (component.strikethrough) styles.textDecoration = 'line-through'
  if (component.obfuscated) {
    styles.fontFamily = 'monospace'
    classes.push('rtext-obfuscated')
  }

  // 处理点击事件
  const clickHandler = handleClickEvent(component.clickEvent, options)

  // 处理悬停事件
  const hoverAttrs = handleHoverEvent(component.hoverEvent)

  // 合并样式
  const finalStyle: React.CSSProperties = {
    ...styles,
    ...clickHandler.style
  }

  // 合并类名
  const finalClassName = [
    ...classes,
    hoverAttrs['data-hover-content'] ? 'rtext-hoverable' : '',
    clickHandler.className || ''
  ].filter(Boolean).join(' ')

  // 构建属性
  const props: React.HTMLAttributes<HTMLSpanElement> = {
    style: Object.keys(finalStyle).length > 0 ? finalStyle : undefined,
    className: finalClassName || undefined,
    onClick: clickHandler.onClick,
    title: hoverAttrs.title,
    ...(hoverAttrs['data-hover-content'] ? { 'data-hover-content': hoverAttrs['data-hover-content'] } : {})
  }

  // 构建子元素
  const children: ReactNode[] = []
  
  if (text) {
    children.push(text)
  }

  // 处理子组件
  if (component.extra && Array.isArray(component.extra)) {
    component.extra.forEach((child, idx) => {
      children.push(
        <React.Fragment key={idx}>
          {parseCallback(child)}
        </React.Fragment>
      )
    })
  }

  // 如果有样式或事件，包装在 span 中
  if (Object.keys(finalStyle).length > 0 || finalClassName || clickHandler.onClick || hoverAttrs.title) {
    return (
      <span {...props}>
        {children}
      </span>
    )
  }

  // 否则直接返回文本
  return <>{children}</>
}

/**
 * 解析 RText 数据为 React 元素
 */
export function parseRText(
  rtext: RTextData,
  options?: ParseOptions
): ReactNode {
  if (!rtext) return null

  try {
    // 如果是字符串，直接返回
    if (typeof rtext === 'string') {
      return rtext
    }

    // 如果是数组，递归解析每个元素
    if (Array.isArray(rtext)) {
      return (
        <>
          {rtext.map((item, idx) => (
            <React.Fragment key={idx}>
              {parseRText(item, options)}
            </React.Fragment>
          ))}
        </>
      )
    }

    // 如果是对象，解析为组件
    if (typeof rtext === 'object') {
      return parseComponent(rtext, (data) => parseRText(data, options), options)
    }

    return String(rtext)
  } catch (error) {
    console.error('RText解析错误:', error)
    return String(rtext)
  }
}

/**
 * RText 解析器类（兼容旧 API）
 */
export class RTextParser {
  private options?: ParseOptions

  constructor(options?: ParseOptions) {
    this.options = options
  }

  parse(rtext: RTextData): ReactNode {
    return parseRText(rtext, this.options)
  }
}

// 导出类型供外部使用
export type { RTextComponent, RTextData, ParseOptions }

