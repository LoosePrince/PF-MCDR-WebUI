/**
 * 项目与官网链接常量（单一定义，供 About、MCDRConfig、notice 等引用）
 * 与后端 guguwebui.constant 中的 URL 保持一致
 */
export const PROJECT_GITHUB_URL = 'https://github.com/PFingan-Code/PF-MCDR-WebUI'
export const PROJECT_GITHUB_ISSUES_URL = `${PROJECT_GITHUB_URL}/issues`
export const PROJECT_GITHUB_CONTRIBUTORS_URL = `${PROJECT_GITHUB_URL}/graphs/contributors`

export const MCDR_SITE_URL = 'https://mcdreforged.com'
export const MCDR_PLUGINS_PAGE_URL = 'https://mcdreforged.com/zh-CN/plugins'

/** GitHub API: 公告来自 repo 的 release tag "notice" */
const PROJECT_GITHUB_REPO_SLUG = 'PFingan-Code/PF-MCDR-WebUI'
export const GITHUB_NOTICE_URL = `https://api.github.com/repos/${PROJECT_GITHUB_REPO_SLUG}/releases/tags/notice`
