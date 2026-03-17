import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Puzzle, Loader2, AlertCircle } from 'lucide-react';
import api from '../utils/api';

function getErrorMessage(err: unknown): string | null {
  if (!err || typeof err !== 'object') return null
  const maybeResponse = (err as { response?: unknown }).response
  if (!maybeResponse || typeof maybeResponse !== 'object') return null
  const data = (maybeResponse as { data?: unknown }).data
  if (!data || typeof data !== 'object') return null
  const message = (data as { message?: unknown }).message
  return typeof message === 'string' ? message : null
}

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
        const pagesResp = await api.get('/plugins/web_pages');
        const pages = pagesResp.data.pages || [];
        const pageInfo = (pages as Array<{ id?: unknown; path?: unknown }>).find((p) => p.id === pluginId);
        
        if (!pageInfo) {
          setError(t('plugins.msg.page_not_found'));
          setLoading(false);
          return;
        }

        // 加载 HTML 内容
        const resp = await api.get(`/load_config?path=${encodeURIComponent(String(pageInfo.path || ''))}&type=auto`);
        if (resp.data && resp.data.type === 'html') {
          setHtmlContent(resp.data.content);
        } else {
          setError(t('plugins.msg.load_page_failed'));
        }
      } catch (err: unknown) {
        console.error('Failed to load plugin page:', err);
        setError(getErrorMessage(err) || t('plugins.msg.load_page_failed'));
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
