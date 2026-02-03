import React from 'react'
import { useTranslation } from 'react-i18next'
import { motion } from 'framer-motion'
import { Info, Github, BookOpen, HeartHandshake } from 'lucide-react'

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.08 },
  },
}

const itemVariants = {
  hidden: { y: 12, opacity: 0 },
  visible: { y: 0, opacity: 1 },
}

const About: React.FC = () => {
  const { t } = useTranslation()

  return (
    <motion.div
      className="space-y-8"
      variants={containerVariants}
      initial="hidden"
      animate="visible"
    >
      {/* Header */}
      <motion.div variants={itemVariants} className="space-y-2">
        <h1 className="text-3xl font-bold text-slate-900 dark:text-white">
          {t('nav.about')}
        </h1>
        <p className="text-slate-600 dark:text-slate-400 max-w-2xl">
          {t('page.about.subtitle')}
        </p>
      </motion.div>

      {/* Intro card */}
      <motion.div
        variants={itemVariants}
        className="relative overflow-hidden bg-white dark:bg-slate-900 rounded-3xl p-6 border border-slate-200 dark:border-slate-800 shadow-sm"
      >
        <div className="absolute -right-20 -top-20 w-64 h-64 bg-blue-500/5 rounded-full blur-3xl" />
        <div className="absolute -left-16 -bottom-24 w-64 h-64 bg-emerald-500/5 rounded-full blur-3xl" />

        <div className="relative z-10 flex flex-col md:flex-row md:items-center gap-6">
          <div className="flex-shrink-0">
            <div className="w-14 h-14 rounded-2xl bg-blue-600 text-white flex items-center justify-center shadow-lg shadow-blue-500/30">
              <Info className="w-7 h-7" />
            </div>
          </div>
          <div className="space-y-2">
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">
              {t('app.name')}
            </h2>
            <p className="text-slate-600 dark:text-slate-300 leading-relaxed">
              {t('app.desc')}
            </p>
          </div>
        </div>
      </motion.div>

      {/* Content grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* WebUI Sources */}
        <motion.div
          variants={itemVariants}
          className="bg-white dark:bg-slate-900 rounded-3xl p-6 border border-slate-200 dark:border-slate-800 shadow-sm space-y-4"
        >
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-purple-500/10 text-purple-600 dark:text-purple-300 flex items-center justify-center">
              <BookOpen className="w-5 h-5" />
            </div>
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
              {t('page.about.source_title')}
            </h3>
          </div>
          <div className="space-y-3 text-sm text-slate-600 dark:text-slate-300">
            <p>{t('page.about.source_desc')}</p>
          </div>
        </motion.div>

        {/* Open source / links */}
        <motion.div
          variants={itemVariants}
          className="bg-white dark:bg-slate-900 rounded-3xl p-6 border border-slate-200 dark:border-slate-800 shadow-sm space-y-4"
        >
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-slate-800/5 dark:bg-slate-50/5 text-slate-800 dark:text-slate-100 flex items-center justify-center">
              <Github className="w-5 h-5" />
            </div>
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
              {t('page.about.opensource_title')}
            </h3>
          </div>
          <p className="text-sm text-slate-600 dark:text-slate-300">
            {t('page.about.opensource_desc')}
          </p>
          <div className="flex flex-wrap gap-2">
            <a
              href="https://github.com/LoosePrince/PF-MCDR-WebUI"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 hover:bg-slate-700 dark:hover:bg-slate-200 transition-colors"
            >
              <Github className="w-3.5 h-3.5" />
              {t('page.about.github_repo')}
            </a>
            <a
              href="https://github.com/LoosePrince/PF-MCDR-WebUI/issues"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
            >
              {t('page.about.issue_tracker')}
            </a>
          </div>
        </motion.div>

        {/* Thanks / community + tables */}
        <motion.div
          variants={itemVariants}
          className="bg-white dark:bg-slate-900 rounded-3xl p-6 border border-slate-200 dark:border-slate-800 shadow-sm space-y-6 md:col-span-2"
        >
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-300 flex items-center justify-center">
              <HeartHandshake className="w-5 h-5" />
            </div>
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
              {t('page.about.thanks_title')}
            </h3>
          </div>
          <p className="text-sm text-slate-600 dark:text-slate-300">
            {t('page.about.thanks_desc')}
          </p>
          {/* 引用旧版 about.html 中的表格内容 */}
          <div className="space-y-6 text-sm">
            {/* 依赖与项目 */}
            <div className="space-y-3">
              <h4 className="text-sm font-semibold text-slate-900 dark:text-white">
                {t('page.about.contribute.title')}
              </h4>
              <div className="overflow-x-auto rounded-2xl border border-slate-200 dark:border-slate-800">
                <table className="min-w-full text-left text-xs md:text-sm table-fixed">
                  <colgroup>
                    <col className="w-40 md:w-56" />
                    <col className="w-auto" />
                  </colgroup>
                  <thead className="bg-slate-50 dark:bg-slate-900/60">
                    <tr>
                      <th className="px-4 py-2 font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide">
                        {t('page.about.contribute.project')}
                      </th>
                      <th className="px-4 py-2 font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide">
                        {t('page.about.contribute.desc')}
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800 bg-white dark:bg-slate-900">
                    <tr>
                      <td className="px-4 py-2">
                        <a
                          href="https://mcdreforged.com/zh-CN/plugins"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 dark:text-blue-400 hover:underline"
                        >
                          {t('page.about.contribute.items.mcdr_repo')}
                        </a>
                      </td>
                      <td className="px-4 py-2 text-slate-600 dark:text-slate-300">
                        {t('page.about.contribute.items.mcdr_repo_desc')}
                      </td>
                    </tr>
                    <tr>
                      <td className="px-4 py-2">
                        <a
                          href="https://github.com/Spark-Code-China/MC-Server-Info"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 dark:text-blue-400 hover:underline"
                        >
                          MC-Server-Info
                        </a>
                      </td>
                      <td className="px-4 py-2 text-slate-600 dark:text-slate-300">
                        {t('page.about.contribute.items.mc_server_info')}
                      </td>
                    </tr>
                    <tr>
                      <td className="px-4 py-2">
                        <a
                          href="https://mcdreforged.com/"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 dark:text-blue-400 hover:underline"
                        >
                          {t('page.about.contribute.items.mcdreforged')}
                        </a>
                      </td>
                      <td className="px-4 py-2 text-slate-600 dark:text-slate-300">
                        {t('page.about.contribute.items.mcdreforged_desc')}
                      </td>
                    </tr>
                    <tr>
                      <td className="px-4 py-2">
                        <a
                          href="https://github.com/zauberzeug/nicegui/issues/1956"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 dark:text-blue-400 hover:underline"
                        >
                          {t('page.about.contribute.items.wolfgangfahl')}
                        </a>
                      </td>
                      <td className="px-4 py-2 text-slate-600 dark:text-slate-300">
                        {t('page.about.contribute.items.wolfgangfahl_desc')}
                      </td>
                    </tr>
                    <tr>
                      <td className="px-4 py-2">
                        <a
                          href="https://zh.minecraft.wiki/w/文本组件"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 dark:text-blue-400 hover:underline"
                        >
                          {t('page.about.contribute.items.minecraft_wiki')}
                        </a>
                      </td>
                      <td className="px-4 py-2 text-slate-600 dark:text-slate-300">
                        {t('page.about.contribute.items.minecraft_wiki_desc')}
                      </td>
                    </tr>
                    <tr>
                      <td className="px-4 py-2">
                        <a
                          href="https://github.com/py-mine/mcstatus"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 dark:text-blue-400 hover:underline"
                        >
                          mcstatus
                        </a>
                      </td>
                      <td className="px-4 py-2 text-slate-600 dark:text-slate-300">
                        {t('page.about.contribute.items.mcstatus_desc')}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* 主要贡献者 */}
            <div className="space-y-3">
              <h4 className="text-sm font-semibold text-slate-900 dark:text-white">
                {t('page.about.thanks.contributors_title')}
              </h4>
              <div className="overflow-x-auto rounded-2xl border border-slate-200 dark:border-slate-800">
                <table className="min-w-full text-left text-xs md:text-sm table-fixed">
                  <colgroup>
                    <col className="w-40 md:w-56" />
                    <col className="w-auto" />
                  </colgroup>
                  <thead className="bg-slate-50 dark:bg-slate-900/60">
                    <tr>
                      <th className="px-4 py-2 font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide">
                        {t('page.about.thanks.contributor')}
                      </th>
                      <th className="px-4 py-2 font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide">
                        {t('page.about.thanks.desc')}
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800 bg-white dark:bg-slate-900">
                    <tr>
                      <td className="px-4 py-2">
                        <a
                          href="https://github.com/LoosePrince"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 dark:text-blue-400 hover:underline"
                        >
                          树梢 (LoosePrince)
                        </a>
                      </td>
                      <td className="px-4 py-2 text-slate-600 dark:text-slate-300">
                        {t('page.about.thanks.items.looseprince_desc')}
                      </td>
                    </tr>
                    <tr>
                      <td className="px-4 py-2">
                        <a
                          href="https://github.com/XueK66"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 dark:text-blue-400 hover:underline"
                        >
                          雪开 (XueK66)
                        </a>
                      </td>
                      <td className="px-4 py-2 text-slate-600 dark:text-slate-300">
                        {t('page.about.thanks.items.xuek66_desc')}
                      </td>
                    </tr>
                    <tr>
                      <td className="px-4 py-2">
                        <a
                          href="https://github.com/LoosePrince/PF-MCDR-WebUI/graphs/contributors"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 dark:text-blue-400 hover:underline"
                        >
                          {t('page.about.thanks.items.contributors_link')}
                        </a>
                      </td>
                      <td className="px-4 py-2 text-slate-600 dark:text-slate-300">
                        {t('page.about.thanks.items.contributors_link_desc')}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* 社区与工具致谢 */}
            <div className="space-y-3">
              <h4 className="text-sm font-semibold text-slate-900 dark:text-white">
                {t('page.about.thanks.community_title')}
              </h4>
              <div className="overflow-x-auto rounded-2xl border border-slate-200 dark:border-slate-800">
                <table className="min-w-full text-left text-xs md:text-sm table-fixed">
                  <colgroup>
                    <col className="w-40 md:w-56" />
                    <col className="w-auto" />
                  </colgroup>
                  <thead className="bg-slate-50 dark:bg-slate-900/60">
                    <tr>
                      <th className="px-4 py-2 font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide">
                        {t('page.about.thanks.contributor')}
                      </th>
                      <th className="px-4 py-2 font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide">
                        {t('page.about.thanks.desc')}
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800 bg-white dark:bg-slate-900">
                    <tr>
                      <td className="px-4 py-2">
                        <span className="text-blue-600 dark:text-blue-400">
                          {t('page.about.thanks.items.feedbackers')}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-slate-600 dark:text-slate-300">
                        {t('page.about.thanks.items.feedbackers_desc')}
                      </td>
                    </tr>
                    <tr>
                      <td className="px-4 py-2">
                        <a
                          href="https://cursor.com/"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 dark:text-blue-400 hover:underline"
                        >
                          Cursor
                        </a>
                      </td>
                      <td className="px-4 py-2 text-slate-600 dark:text-slate-300">
                        {t('page.about.thanks.items.cursor')}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </motion.div>
  )
}

export default About
