import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Puzzle, Loader2, AlertCircle } from 'lucide-react';
import axios from 'axios';

const PluginPage: React.FC = () => {
  const { pluginId } = useParams<{ pluginId: string }>();
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [htmlContent, setHtmlContent] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchPluginPage = async () => {
      if (!pluginId) return;
      
      setLoading(true);
      setError(null);
      try {
        // 先获取注册的页面信息
        const pagesResp = await axios.get('/api/plugins/web_pages');
        const pages = pagesResp.data.pages || [];
        const pageInfo = pages.find((p: any) => p.id === pluginId);
        
        if (!pageInfo) {
          setError(t('plugins.msg.page_not_found', '未找到插件网页注册信息'));
          setLoading(false);
          return;
        }

        // 加载 HTML 内容
        const resp = await axios.get(`/api/load_config?path=${encodeURIComponent(pageInfo.path)}&type=auto`);
        if (resp.data && resp.data.type === 'html') {
          setHtmlContent(resp.data.content);
        } else {
          setError(t('plugins.msg.load_page_failed', '加载插件网页失败，返回数据格式不正确'));
        }
      } catch (err: any) {
        console.error('Failed to load plugin page:', err);
        setError(err.response?.data?.message || t('plugins.msg.load_page_failed', '加载插件网页出错'));
      } finally {
        setLoading(false);
      }
    };

    fetchPluginPage();
  }, [pluginId, t]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24">
        <Loader2 className="w-12 h-12 text-blue-500 animate-spin mb-4" />
        <p className="text-slate-500 animate-pulse">{t('common.notice_loading')}</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-rose-500">
        <AlertCircle className="w-16 h-16 mb-4 opacity-20" />
        <p className="font-bold text-xl mb-2">{t('common.failed')}</p>
        <p className="text-sm opacity-80">{error}</p>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-12rem)] min-h-[600px] flex flex-col space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="flex items-center gap-3 px-2">
        <div className="p-2 bg-blue-500/10 text-blue-500 rounded-xl">
          <Puzzle size={20} />
        </div>
        <div>
          <h1 className="text-xl font-bold text-slate-900 dark:text-white uppercase">
            {pluginId}
          </h1>
          <p className="text-xs text-slate-500">{t('plugins.config_modal.web_view')}</p>
        </div>
      </div>
      
      <div className="flex-1 bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm">
        <iframe
          srcDoc={htmlContent}
          className="w-full h-full border-none"
          title={`Plugin Page - ${pluginId}`}
        />
      </div>
    </div>
  );
};

export default PluginPage;
