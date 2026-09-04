import React, { useEffect, useState } from 'react'
import api, { unwrapData } from '../utils/api'

interface IcpRecord {
  icp: string
  url: string
}

interface VersionFooterProps {
  className?: string
}

const VersionFooter: React.FC<VersionFooterProps> = ({ className = '' }) => {
  const [version, setVersion] = useState<string | null>(null)
  const [icpRecords, setIcpRecords] = useState<IcpRecord[]>([])

  useEffect(() => {
    let cancelled = false

    const fetchData = async () => {
      try {
        // 获取版本信息（单项查询 GET /plugins/{plugin_id}，原 ?plugin_id= 过滤参数已移除）
        const pluginResp = await api.get('/plugins/guguwebui')
        if (cancelled) return
        const webui = unwrapData<{ plugin?: { version?: string } }>(pluginResp, {}).plugin
        if (webui && webui.version) {
          setVersion(webui.version)
        }

        // 获取 ICP 备案信息
        const icpResp = await api.get('/config/icp-records')
        if (cancelled) return
        const icpData = unwrapData<{ icp_records?: IcpRecord[] }>(icpResp, {})
        if (Array.isArray(icpData?.icp_records)) {
          setIcpRecords(icpData.icp_records)
        }
      } catch {
        if (!cancelled) {
          setVersion(null)
        }
      }
    }

    fetchData()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className={`flex flex-col items-center gap-1 ${className}`}>
      <p className="text-xs text-slate-400 dark:text-slate-600 font-medium">
        {version ? `GUGUWebUI v${version}` : 'GUGUWebUI'}
      </p>
      {icpRecords.length > 0 && (
        <div className="flex flex-col items-center gap-0.5">
          {icpRecords.map((record, index) => (
            <a
              key={index}
              href={record.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[10px] text-slate-400/80 dark:text-slate-600/80 hover:text-blue-500 transition-colors"
            >
              {record.icp}
            </a>
          ))}
        </div>
      )}
    </div>
  )
}

export default VersionFooter

