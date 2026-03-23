import { AlertCircle, Loader2, Puzzle } from 'lucide-react';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
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
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const iframeResizeObserverRef = useRef<ResizeObserver | null>(null);
  const [iframeHeightPx, setIframeHeightPx] = useState(320);

  const measureIframeContentHeight = useCallback(() => {
    const iframe = iframeRef.current;
    const doc = iframe?.contentDocument;
    const body = doc?.body;
    if (!body) return;
    const h = Math.max(
      body.scrollHeight,
      body.offsetHeight,
      Math.ceil(body.getBoundingClientRect().height),
    );
    if (h > 0) {
      setIframeHeightPx(Math.max(Math.ceil(h), 120));
    }
  }, []);

  const teardownIframeObservers = useCallback(() => {
    iframeResizeObserverRef.current?.disconnect();
    iframeResizeObserverRef.current = null;
  }, []);

  const setupIframeObservers = useCallback(() => {
    const iframe = iframeRef.current;
    const doc = iframe?.contentDocument;
    if (!doc?.documentElement) return;
    teardownIframeObservers();
    measureIframeContentHeight();
    const ro = new ResizeObserver(() => measureIframeContentHeight());
    iframeResizeObserverRef.current = ro;
    ro.observe(doc.documentElement);
    if (doc.body) ro.observe(doc.body);
  }, [measureIframeContentHeight, teardownIframeObservers]);

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

  useEffect(() => {
    return () => teardownIframeObservers();
  }, [teardownIframeObservers]);

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
    <div className="flex flex-col space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-700 pb-8">
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

      <div
        className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden"
      >
        <iframe
          ref={iframeRef}
          srcDoc={htmlContent}
          className="w-full border-none block"
          style={{
            height: iframeHeightPx,
            overflow: 'auto',
          }}
          title={`Plugin Page - ${pluginId}`}
          onLoad={setupIframeObservers}
        />
      </div>
    </div>
  );
};

export default PluginPage;
