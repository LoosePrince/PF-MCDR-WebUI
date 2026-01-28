import React, { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Server,
  Search,
  Save,
  Loader2,
  AlertCircle,
  CheckCircle2,
  X,
  Info,
  ChevronRight,
  Zap,
  Filter,
  SlidersHorizontal,
  Gamepad2,
  Network,
  Gauge,
  Globe2,
  ShieldCheck
} from 'lucide-react';
import axios from 'axios';
import { NiceSelect } from '../components/NiceSelect';
import serverLang from '../i18n/server_lang.json';

interface Category {
  id: string;
  name: string;
  icon: any;
  keys: string[];
}

interface RconConfig {
  rcon_host: string;
  rcon_port: number;
  rcon_password: string;
}

const MCConfig: React.FC = () => {
  const { t, i18n } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [configData, setConfigData] = useState<Record<string, any>>({});
  const [translations, setTranslations] = useState<Record<string, [string, string]>>({});
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState('all');
  const [serverPath, setServerPath] = useState('server/');

  // RCON Modal states
  const [showRconSetupModal, setShowRconSetupModal] = useState(false);
  const [showRconRestartModal, setShowRconRestartModal] = useState(false);
  const [settingUpRcon, setSettingUpRcon] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const [rconConfig, setRconConfig] = useState<RconConfig | null>(null);

  const [notification, setNotification] = useState<{ msg: string; type: 'success' | 'error' } | null>(null);

  const categories: Category[] = useMemo(() => [
    { id: 'all', name: t('page.mc.categories.all'), icon: SlidersHorizontal, keys: [] },
    { id: 'basic', name: t('page.mc.categories.basic'), icon: Server, keys: ['motd', 'server-port', 'server-ip', 'level-name', 'max-players', 'gamemode', 'difficulty'] },
    { id: 'game', name: t('page.mc.categories.game'), icon: Gamepad2, keys: ['pvp', 'hardcore', 'force-gamemode', 'allow-nether', 'spawn-animals', 'spawn-monsters', 'spawn-npcs', 'allow-flight', 'function-permission-level', 'op-permission-level'] },
    { id: 'network', name: t('page.mc.categories.network'), icon: Network, keys: ['network-compression-threshold', 'rate-limit', 'enable-status', 'enable-query', 'query.port', 'enable-rcon', 'rcon.port', 'rcon.password', 'broadcast-rcon-to-ops'] },
    { id: 'performance', name: t('page.mc.categories.performance'), icon: Gauge, keys: ['view-distance', 'simulation-distance', 'max-tick-time', 'entity-broadcast-range-percentage', 'max-chained-neighbor-updates'] },
    { id: 'world', name: t('page.mc.categories.world'), icon: Globe2, keys: ['level-seed', 'level-type', 'generate-structures', 'generator-settings', 'max-world-size', 'max-build-height'] },
    { id: 'security', name: t('page.mc.categories.security'), icon: ShieldCheck, keys: ['white-list', 'enforce-whitelist', 'online-mode', 'prevent-proxy-connections', 'player-idle-timeout', 'spawn-protection'] },
  ], [t]);

  const booleanKeys = [
    'accepts-transfers', 'pvp', 'hardcore', 'online-mode', 'enable-status', 'enable-query', 'enable-rcon',
    'enable-command-block', 'force-gamemode', 'allow-nether', 'spawn-animals',
    'spawn-monsters', 'spawn-npcs', 'white-list', 'enforce-whitelist',
    'generate-structures', 'allow-flight', 'sync-chunk-writes', 'use-native-transport',
    'prevent-proxy-connections', 'enable-jmx-monitoring', 'broadcast-rcon-to-ops',
    'broadcast-console-to-ops', 'enforce-secure-profile', 'hide-online-players'
  ];

  const selectOptions: Record<string, string[]> = {
    'difficulty': ['peaceful', 'easy', 'normal', 'hard', '0', '1', '2', '3'],
    'gamemode': ['survival', 'creative', 'adventure', 'spectator'],
    'level-type': ['DEFAULT', 'FLAT', 'LARGEBIOMES', 'AMPLIFIED', 'BUFFET', 'normal', 'flat'],
    'function-permission-level': ['1', '2', '3', '4'],
    'op-permission-level': ['1', '2', '3', '4']
  };

  useEffect(() => {
    init();
  }, []);

  const init = async () => {
    setLoading(true);
    try {
      // 1. Get server path from MCDR config
      const mcdrResp = await axios.get('/api/load_config?path=config.yml');
      const workingDir = mcdrResp.data.working_directory || 'server';
      const path = workingDir.endsWith('/') ? workingDir : workingDir + '/';
      setServerPath(path);

      // 2. Load minecraft config
      const configResp = await axios.get(`/api/load_config?path=${path}server.properties`);
      const rawData = configResp.data;

      // Convert string boolean to real boolean
      const processedData: Record<string, any> = {};
      for (const key in rawData) {
        if (booleanKeys.includes(key)) {
          processedData[key] = (rawData[key] === true || rawData[key] === 'true');
        } else {
          processedData[key] = rawData[key];
        }
      }
      setConfigData(processedData);

      // 3. Load translations from bundled server_lang.json
      const langData = serverLang as any;
      const currentLang = i18n.language.startsWith('zh') ? 'zh_CN' : 'en_US';
      const candidates = [currentLang, currentLang.replace('-', '_'), currentLang.replace('_', '-').toLowerCase()];
      let picked: Record<string, [string, string]> | null = null;
      for (const c of candidates) {
        if ((langData as any)[c]) { picked = (langData as any)[c]; break; }
      }
      if (!picked) {
        const want = (i18n.language.startsWith('zh') ? 'zh_cn' : 'en_us').replace(/[\-_]/g, '').toLowerCase();
        for (const k of Object.keys(langData as any)) {
          if (String(k).replace(/[\-_]/g, '').toLowerCase() === want) {
            picked = (langData as any)[k];
            break;
          }
        }
      }
      setTranslations(picked || (langData as any).zh_CN || (langData as any).zh_cn || {});

    } catch (error) {
      console.error('Failed to init MC config:', error);
      notify(t('page.mc.msg.load_config_failed'), 'error');
    } finally {
      setLoading(false);
    }
  };

  const notify = (msg: string, type: 'success' | 'error') => {
    setNotification({ msg, type });
    setTimeout(() => setNotification(null), 3000);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      // Convert boolean back to string 'true'/'false' for server.properties
      const formattedConfig: Record<string, string> = {};
      for (const key in configData) {
        if (booleanKeys.includes(key)) {
          formattedConfig[key] = configData[key] ? 'true' : 'false';
        } else {
          formattedConfig[key] = String(configData[key]);
        }
      }

      const resp = await axios.post('/api/save_config', {
        file_path: `${serverPath}server.properties`,
        config_data: formattedConfig
      });

      if (resp.data.status === 'success') {
        notify(t('page.mc.msg.save_success'), 'success');
      } else {
        notify(t('page.mc.msg.save_failed_prefix') + (resp.data.message || ''), 'error');
      }
    } catch (error: any) {
      notify(t('page.mc.msg.save_error'), 'error');
    } finally {
      setSaving(false);
    }
  };

  const setupRcon = async () => {
    setSettingUpRcon(true);
    try {
      const resp = await axios.post('/api/setup_rcon');
      if (resp.data.status === 'success') {
        setRconConfig(resp.data.config);
        setShowRconSetupModal(false);
        setShowRconRestartModal(true);
        // Reload config to show new values
        const configResp = await axios.get(`/api/load_config?path=${serverPath}server.properties`);
        setConfigData(configResp.data);
        notify(t('page.mc.rcon.setup_success_msg'), 'success');
      } else {
        notify(t('page.mc.rcon.setup_failed_prefix') + (resp.data.message || ''), 'error');
      }
    } catch (error) {
      notify(t('page.mc.rcon.setup_error'), 'error');
    } finally {
      setSettingUpRcon(false);
    }
  };

  const restartServer = async () => {
    setRestarting(true);
    try {
      const resp = await axios.post('/api/control_server', { action: 'restart' });
      if (resp.data.status === 'success') {
        setShowRconRestartModal(false);
        notify(t('page.mc.rcon.restart_success'), 'success');
      } else {
        notify(t('page.mc.rcon.restart_failed_prefix') + (resp.data.message || ''), 'error');
      }
    } catch (error) {
      notify(t('page.mc.rcon.restart_error'), 'error');
    } finally {
      setRestarting(false);
    }
  };

  const filteredKeys = useMemo(() => {
    let keys = Object.keys(configData);

    // Category filter
    if (activeCategory !== 'all') {
      const cat = categories.find(c => c.id === activeCategory);
      if (cat) {
        keys = keys.filter(k => cat.keys.includes(k) || (activeCategory === 'basic' && !categories.some(c => c.id !== 'all' && c.id !== 'basic' && c.keys.includes(k))));
      }
    }

    // Search filter
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      keys = keys.filter(k => {
        const name = (translations[k]?.[0] || k).toLowerCase();
        const desc = (translations[k]?.[1] || '').toLowerCase();
        return name.includes(q) || desc.includes(q) || k.toLowerCase().includes(q);
      });
    }

    return keys.sort();
  }, [configData, activeCategory, searchQuery, categories, translations]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px]">
        <Loader2 className="w-12 h-12 text-blue-500 animate-spin mb-4" />
        <p className="text-slate-600 dark:text-slate-400 animate-pulse">{t('common.notice_loading')}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-12 min-h-[calc(100vh-8rem)]">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white dark:bg-slate-900 p-6 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm">
        <div>
          <h1 className="text-2xl font-bold font-display text-slate-900 dark:text-white flex items-center gap-3">
            <Server className="text-blue-500" />
            {t('page.mc.header')}
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
            server.properties @ {serverPath}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('page.mc.search')}
              className="pl-10 pr-4 py-2 bg-slate-100 dark:bg-slate-800 border-none rounded-xl text-sm focus:ring-2 focus:ring-blue-500/50 outline-none w-full md:w-64 transition-all"
            />
          </div>
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white font-medium rounded-xl shadow-lg shadow-blue-500/25 transition-all"
          >
            {saving ? <Loader2 size={18} className="animate-spin" /> : <Save size={18} />}
            {saving ? t('page.mc.saving') : t('page.mc.save')}
          </button>
        </div>
      </div>

      <div className="flex flex-col lg:flex-row gap-6">
        {/* Sidebar Categories */}
        <div className="w-full lg:w-64 space-y-2">
          {categories.map((cat) => {
            const Icon = cat.icon;
            return (
              <button
                key={cat.id}
                onClick={() => setActiveCategory(cat.id)}
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all ${activeCategory === cat.id
                    ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/30 font-bold'
                    : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-800 hover:border-blue-400'
                  }`}
              >
                <Icon size={20} />
                <span className="text-sm">{cat.name}</span>
              </button>
            );
          })}
        </div>

        {/* Config Items Grid */}
        <div className="flex-1">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <AnimatePresence mode="popLayout">
              {filteredKeys.map((key) => (
                <motion.div
                  layout
                  key={key}
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  transition={{ duration: 0.2 }}
                  className="bg-white dark:bg-slate-900 p-5 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm hover:shadow-md transition-shadow group relative"
                >
                  <div className="flex flex-col h-full space-y-3">
                    <div className="flex items-start justify-between">
                      <div className="space-y-0.5">
                        <div className="text-xs font-mono text-blue-500 opacity-60 uppercase tracking-tighter">{key}</div>
                        <h3 className="font-bold text-slate-900 dark:text-white leading-tight">
                          {translations[key]?.[0] || key}
                        </h3>
                      </div>
                      {key === 'enable-rcon' && !configData[key] && (
                        <button
                          onClick={() => setShowRconSetupModal(true)}
                          className="p-1.5 bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 rounded-lg hover:bg-blue-100 transition-colors"
                          title={t('page.mc.rcon.setup_button')}
                        >
                          <Zap size={16} />
                        </button>
                      )}
                    </div>

                    <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-2 min-h-[32px]">
                      {translations[key]?.[1] || ''}
                    </p>

                    <div className="mt-auto pt-4 border-t border-slate-100 dark:border-slate-800">
                      {booleanKeys.includes(key) ? (
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-medium text-slate-400">
                            {configData[key] ? t('page.index.rcon_enabled') : t('page.index.rcon_disabled')}
                          </span>
                          <Switch
                            checked={configData[key] === true}
                            onChange={(v) => setConfigData({ ...configData, [key]: v })}
                          />
                        </div>
                      ) : selectOptions[key] ? (
                        <NiceSelect
                          value={String(configData[key] ?? '')}
                          onChange={(val) => setConfigData({ ...configData, [key]: val })}
                          options={selectOptions[key].map(opt => ({ value: opt, label: opt }))}
                        />
                      ) : (
                        <input
                          type="text"
                          value={configData[key] || ''}
                          onChange={(e) => setConfigData({ ...configData, [key]: e.target.value })}
                          className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-800 rounded-lg px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-blue-500/50"
                        />
                      )}
                    </div>
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>

          {filteredKeys.length === 0 && (
            <div className="flex flex-col items-center justify-center py-20 bg-white dark:bg-slate-900 rounded-3xl border-2 border-dashed border-slate-200 dark:border-slate-800">
              <Filter className="w-12 h-12 text-slate-300 mb-4" />
              <p className="text-slate-500 dark:text-slate-400">No configuration items match your search.</p>
            </div>
          )}
        </div>
      </div>

      {/* RCON Modals - Same as MCDRConfig better to share logic but for simplicity we keep it here too */}
      <Modal
        isOpen={showRconSetupModal}
        onClose={() => setShowRconSetupModal(false)}
        title={t('page.mcdr.rcon.setup_modal_title')}
      >
        <div className="space-y-4">
          <p className="text-slate-600 dark:text-slate-400">{t('page.mcdr.rcon.setup_description')}</p>
          <ul className="space-y-2 text-sm bg-slate-50 dark:bg-slate-900/50 p-4 rounded-lg">
            <li className="flex items-center gap-2"><ChevronRight size={14} className="text-blue-500" /> {t('page.mcdr.rcon.setup_ip')}</li>
            <li className="flex items-center gap-2"><ChevronRight size={14} className="text-blue-500" /> {t('page.mcdr.rcon.setup_port')}</li>
            <li className="flex items-center gap-2"><ChevronRight size={14} className="text-blue-500" /> {t('page.mcdr.rcon.setup_password')}</li>
          </ul>
          <div className="p-3 bg-yellow-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-900/30 rounded-lg flex gap-3">
            <Info className="text-yellow-600 shrink-0" size={20} />
            <p className="text-xs text-slate-800 dark:text-slate-200">{t('page.mcdr.rcon.setup_warning')}</p>
          </div>
          <div className="flex gap-3 pt-4">
            <button
              onClick={() => setShowRconSetupModal(false)}
              className="flex-1 px-4 py-2 border border-slate-200 dark:border-slate-800 rounded-lg text-slate-600 dark:text-slate-400 font-medium hover:bg-slate-50 dark:hover:bg-slate-800/80 transition-colors"
            >
              {t('common.cancel')}
            </button>
            <button
              onClick={setupRcon}
              disabled={settingUpRcon}
              className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg shadow-lg shadow-blue-600/20 transition-all flex justify-center items-center gap-2"
            >
              {settingUpRcon && <Loader2 size={18} className="animate-spin" />}
              {settingUpRcon ? t('page.mcdr.rcon.setting_up') : t('page.mcdr.rcon.setup_confirm')}
            </button>
          </div>
        </div>
      </Modal>

      <Modal
        isOpen={showRconRestartModal}
        onClose={() => setShowRconRestartModal(false)}
        title={t('page.mcdr.rcon.restart_modal_title')}
      >
        <div className="space-y-4">
          <div className="p-4 bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-100 dark:border-emerald-900/30 rounded-xl">
            <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-300 font-bold mb-3">
              <CheckCircle2 size={20} />
              {t('page.mcdr.rcon.setup_success')}
            </div>
            <div className="space-y-1 text-sm font-mono opacity-80">
              <div className="flex justify-between"><span>{t('page.mcdr.rcon.config_host')}:</span> <span>{rconConfig?.rcon_host}</span></div>
              <div className="flex justify-between"><span>{t('page.mcdr.rcon.config_port')}:</span> <span>{rconConfig?.rcon_port}</span></div>
              <div className="flex justify-between"><span>{t('page.mcdr.rcon.config_password')}:</span> <span>{rconConfig?.rcon_password}</span></div>
            </div>
          </div>
          <p className="text-slate-600 dark:text-slate-400">{t('page.mcdr.rcon.restart_question')}</p>
          <div className="flex gap-3 pt-4">
            <button
              onClick={() => setShowRconRestartModal(false)}
              className="flex-1 px-4 py-2 border border-slate-200 dark:border-slate-800 rounded-lg text-slate-600 dark:text-slate-400 font-medium hover:bg-slate-50 dark:hover:bg-slate-800/80 transition-colors"
            >
              {t('page.mcdr.rcon.restart_later')}
            </button>
            <button
              onClick={restartServer}
              disabled={restarting}
              className="flex-1 px-4 py-2 bg-red-600 hover:bg-red-700 text-white font-medium rounded-lg shadow-lg shadow-red-600/20 transition-all flex justify-center items-center gap-2"
            >
              {restarting && <Loader2 size={18} className="animate-spin" />}
              {restarting ? t('page.mcdr.rcon.restarting') : t('page.mcdr.rcon.restart_now')}
            </button>
          </div>
        </div>
      </Modal>

      {/* Notifications */}
      <AnimatePresence>
        {notification && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            className={`fixed bottom-6 right-6 z-50 flex items-center gap-3 px-6 py-4 rounded-2xl shadow-2xl ${notification.type === 'success'
                ? 'bg-emerald-500 text-white shadow-emerald-500/20'
                : 'bg-rose-500 text-white shadow-rose-500/20'
              }`}
          >
            {notification.type === 'success' ? <CheckCircle2 size={20} /> : <AlertCircle size={20} />}
            <span className="font-medium">{notification.msg}</span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

// UI Components
const Switch: React.FC<{ checked: boolean; onChange: (v: boolean) => void }> = ({ checked, onChange }) => (
  <button
    onClick={() => onChange(!checked)}
    className={`relative w-11 h-6 transition-colors rounded-full focus:outline-none focus:ring-2 focus:ring-blue-500/20 ${checked ? 'bg-blue-500' : 'bg-slate-300 dark:bg-slate-700'
      }`}
  >
    <motion.div
      animate={{ x: checked ? 22 : 2 }}
      className="absolute top-1 w-4 h-4 bg-white rounded-full shadow-sm"
      transition={{ type: 'spring', stiffness: 500, damping: 30 }}
    />
  </button>
);

const Modal: React.FC<{ isOpen: boolean; onClose: () => void; title: string; children: React.ReactNode }> = ({ isOpen, onClose, title, children }) => {
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
      />
      <motion.div
        initial={{ scale: 0.95, opacity: 0, y: 20 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={{ scale: 0.95, opacity: 0, y: 20 }}
        className="relative bg-white dark:bg-slate-900 rounded-3xl shadow-2xl border border-slate-200 dark:border-slate-800 w-full max-w-md p-8"
      >
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-xl font-bold text-slate-900 dark:text-white">{title}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1">
            <X size={24} />
          </button>
        </div>
        {children}
      </motion.div>
    </div>
  );
};

export default MCConfig;
