/**
 * 公告数据：来自 GitHub Release tag "notice"
 * body 为 JSON：{ text, img?, fill? }
 */
export interface NoticeData {
  title: string
  text: string
  img: string | null
  fill: string | null
}

const GITHUB_NOTICE_URL = 'https://api.github.com/repos/PFingan-Code/PF-MCDR-WebUI/releases/tags/notice'

function isSafeUrl(url: string): boolean {
  return /^https?:\/\//i.test(url)
}

/**
 * 从 GitHub API 获取 notice release，解析为 NoticeData；失败返回 null。
 */
export async function fetchNotice(): Promise<NoticeData | null> {
  try {
    const res = await fetch(GITHUB_NOTICE_URL, {
      headers: {
        Accept: 'application/vnd.github.v3+json',
        'User-Agent': 'PF-MCDR-WebUI',
      },
    })
    if (!res.ok) return null
    const data = await res.json()
    const title = typeof data.name === 'string' ? data.name : ''
    const bodyRaw = typeof data.body === 'string' ? data.body : ''
    let text = bodyRaw
    let img: string | null = null
    let fill: string | null = null
    try {
      const parsed = JSON.parse(bodyRaw) as Record<string, unknown>
      if (typeof parsed.text === 'string') text = parsed.text
      if (typeof parsed.img === 'string' && isSafeUrl(parsed.img)) img = parsed.img
      if (typeof parsed.fill === 'string' && isSafeUrl(parsed.fill)) fill = parsed.fill
    } catch {
      // body 非 JSON，text 已为原始 body
    }
    return { title, text, img, fill }
  } catch {
    return null
  }
}
