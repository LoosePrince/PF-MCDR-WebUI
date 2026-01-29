import React from 'react';
import { Loader2, Info, Download, Clock, X } from 'lucide-react';

type VersionItem = {
  version: string;
  installed?: boolean;
  prerelease?: boolean;
  date?: string;
  downloads?: number;
};

export const VersionSelectModal: React.FC<{
  isOpen: boolean;
  onClose: () => void;
  title: string;
  loading: boolean;
  versions: VersionItem[];
  currentVersion?: string;
  t: any;
  onSelectVersion: (version: string) => void;
}> = ({ isOpen, onClose, title, loading, versions, currentVersion, t, onSelectVersion }) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div onClick={onClose} className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div className="relative bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-800 w-full max-w-xl p-6 md:p-8 max-h-[85vh] overflow-y-auto custom-scrollbar">
        <div className="flex items-center justify-between mb-4 sticky top-0 bg-white dark:bg-slate-900 z-10 pb-3 border-b border-slate-100 dark:border-slate-800">
          <h3 className="text-xl font-bold text-slate-900 dark:text-white line-clamp-1">{title}</h3>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1.5 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        <div className="space-y-4">
          {loading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="animate-spin text-purple-500 w-10 h-10" />
            </div>
          ) : versions.length > 0 ? (
            <div className="space-y-3">
              {currentVersion && (
                <p className="text-sm text-slate-500 mb-2 font-medium">
                  {t('plugins.version_modal.current_version')}{' '}
                  <span className="text-purple-600 dark:text-purple-400 font-bold">v{currentVersion}</span>
                </p>
              )}

              <div className="grid gap-2 max-h-[400px] overflow-y-auto pr-2 custom-scrollbar">
                {versions.map((v) => {
                  const isInstalled = !!v.installed || (!!currentVersion && v.version === currentVersion);
                  return (
                    <div
                      key={v.version}
                      className={`flex items-center justify-between p-4 rounded-2xl border transition-all ${
                        isInstalled
                          ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800/50'
                          : 'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-800 hover:border-blue-200 dark:hover:border-blue-800'
                      }`}
                    >
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-slate-900 dark:text-white">v{v.version}</span>
                          {v.prerelease && (
                            <span className="px-2 py-0.5 bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400 text-[10px] font-bold rounded-full uppercase">
                              {t('plugins.version_modal.prerelease')}
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-slate-500 mt-1 flex items-center gap-3">
                          {v.date && (
                            <span className="flex items-center gap-1">
                              <Clock size={12} /> {v.date}
                            </span>
                          )}
                          {typeof v.downloads === 'number' && v.downloads > 0 && (
                            <span className="flex items-center gap-1">
                              <Download size={12} /> {v.downloads}
                            </span>
                          )}
                        </div>
                      </div>

                      <button
                        disabled={isInstalled}
                        onClick={() => onSelectVersion(v.version)}
                        className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${
                          isInstalled
                            ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400 cursor-default'
                            : 'bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-600/20'
                        }`}
                      >
                        {isInstalled ? t('plugins.version_modal.installed') : t('common.install')}
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-12 text-slate-500">
              <div className="p-4 bg-slate-100 dark:bg-slate-800 rounded-full mb-4">
                <Info size={32} className="opacity-20" />
              </div>
              <p className="font-medium">{t('plugins.version_modal.no_versions')}</p>
            </div>
          )}

          <div className="flex justify-end pt-4">
            <button
              onClick={onClose}
              className="px-6 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-xl transition-colors font-semibold"
            >
              {t('common.cancel')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

