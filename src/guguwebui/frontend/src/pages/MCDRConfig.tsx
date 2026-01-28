import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Settings,
  Shield,
  Save,
  Info,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Terminal,
  ExternalLink,
  ChevronRight,
  UserPlus,
  X,
  Zap,
  Globe,
  BookOpen
} from 'lucide-react';
import axios from 'axios';
import { NiceSelect } from '../components/NiceSelect';

interface RconConfig {
  rcon_host: string;
  rcon_port: number;
  rcon_password: string;
}

const MCDRConfig: React.FC = () => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'config' | 'permission'>('config');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [configData, setConfigData] = useState<any>({});
  const [permissionData, setPermissionData] = useState<any>({});
  const [showNotification, setShowNotification] = useState(false);
  const [notificationMsg, setNotificationMsg] = useState('');
  const [notificationType, setNotificationType] = useState<'success' | 'error'>('success');

  // RCON Modal states
  const [showRconSetupModal, setShowRconSetupModal] = useState(false);
  const [showRconRestartModal, setShowRconRestartModal] = useState(false);
  const [settingUpRcon, setSettingUpRcon] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const [rconConfig, setRconConfig] = useState<RconConfig | null>(null);

  // Permission management
  const [newPlayerName, setNewPlayerName] = useState('');
  const [playerAddingToLevel, setPlayerAddingToLevel] = useState<string | null>(null);
  const [showHandlerModal, setShowHandlerModal] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [configResp, permResp] = await Promise.all([
        axios.get('/api/load_config?path=config.yml'),
        axios.get('/api/load_config?path=permission.yml')
      ]);
      setConfigData(configResp.data);
      setPermissionData(permResp.data);
    } catch (error) {
      console.error('Failed to load MCDR config:', error);
      notify(t('common.config_load_failed'), 'error');
    } finally {
      setLoading(false);
    }
  };

  const notify = (msg: string, type: 'success' | 'error') => {
    setNotificationMsg(msg);
    setNotificationType(type);
    setShowNotification(true);
    setTimeout(() => setShowNotification(false), 3000);
  };

  const handleSave = async (file: 'config.yml' | 'permission.yml') => {
    setSaving(true);
    const data = file === 'config.yml' ? configData : permissionData;
    try {
      const resp = await axios.post('/api/save_config', {
        file_path: file,
        config_data: data
      });
      if (resp.data.status === 'success') {
        notify(t('page.mcdr.msg.save_success'), 'success');
      } else {
        notify(t('page.mcdr.msg.save_failed_prefix') + (resp.data.message || ''), 'error');
      }
    } catch (error: any) {
      notify(t('page.mcdr.msg.save_error_prefix') + (error.message || ''), 'error');
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
        const configResp = await axios.get('/api/load_config?path=config.yml');
        setConfigData(configResp.data);
        notify(t('page.mcdr.rcon.setup_success_msg'), 'success');
      } else {
        notify(t('page.mcdr.rcon.setup_failed_prefix') + (resp.data.message || ''), 'error');
      }
    } catch (error) {
      notify(t('page.mcdr.rcon.setup_error'), 'error');
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
        notify(t('page.mcdr.rcon.restart_success'), 'success');
      } else {
        notify(t('page.mcdr.rcon.restart_failed_prefix') + (resp.data.message || ''), 'error');
      }
    } catch (error) {
      notify(t('page.mcdr.rcon.restart_error'), 'error');
    } finally {
      setRestarting(false);
    }
  };

  const updateConfig = (path: string, value: any) => {
    const newData = { ...configData };
    const keys = path.split('.');
    let current = newData;
    for (let i = 0; i < keys.length - 1; i++) {
      if (!current[keys[i]]) current[keys[i]] = {};
      current = current[keys[i]];
    }
    current[keys[keys.length - 1]] = value;
    setConfigData(newData);
  };

  const addPlayer = (level: string) => {
    const trimmed = newPlayerName.trim();
    if (!trimmed) return;

    setPermissionData((prev: any) => {
      const currentLevel: string[] = Array.isArray(prev?.[level]) ? prev[level] : [];
      if (currentLevel.includes(trimmed)) return prev;
      return {
        ...prev,
        [level]: [...currentLevel, trimmed]
      };
    });

    setNewPlayerName('');
    setPlayerAddingToLevel(null);
  };

  const removePlayer = (level: string, index: number) => {
    setPermissionData((prev: any) => {
      const currentLevel: string[] = Array.isArray(prev?.[level]) ? prev[level] : [];
      return {
        ...prev,
        [level]: currentLevel.filter((_, i) => i !== index)
      };
    });
  };

  const TabButton = ({ id, icon: Icon, label }: { id: typeof activeTab, icon: any, label: string }) => (
    <button
      onClick={() => setActiveTab(id)}
      className={`flex items-center space-x-2 px-6 py-3 rounded-xl transition-all duration-200 ${activeTab === id
          ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/30'
          : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
        }`}
    >
      <Icon size={18} />
      <span className="font-medium">{label}</span>
    </button>
  );

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px]">
        <Loader2 className="w-12 h-12 text-blue-500 animate-spin mb-4" />
        <p className="text-slate-600 dark:text-slate-400 animate-pulse">{t('common.notice_loading')}</p>
      </div>
    );
  }

  return (
    <>
      <div className="space-y-8 pb-12 animate-in fade-in slide-in-from-bottom-4 duration-700">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-900 dark:text-white flex items-center gap-3">
            <Settings className="text-blue-500" />
            {t('nav.mcdr_config')}
          </h1>
          <p className="mt-1 text-slate-600 dark:text-slate-400">
            {t('page.mcdr.about.title')}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <a
            href="https://mcdreforged.com"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-slate-600 dark:text-slate-300 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800/80 transition-colors"
          >
            <BookOpen size={16} />
            {t('page.mcdr.about.doc')}
            <ExternalLink size={14} />
          </a>
          <button
            onClick={() => handleSave(activeTab === 'config' ? 'config.yml' : 'permission.yml')}
            disabled={saving}
            className="flex items-center gap-2 px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white rounded-lg shadow-lg shadow-blue-500/25 transition-all"
          >
            {saving ? <Loader2 size={18} className="animate-spin" /> : <Save size={18} />}
            {saving ? t('page.mc.saving') : t('page.mc.save')}
          </button>
        </div>
      </div>

      {/* Tabs Nav */}
      <div className="flex gap-2 p-1 bg-slate-100 dark:bg-slate-800/50 rounded-xl w-fit">
        <TabButton id="config" icon={Settings} label={t('page.mcdr.config.config_yml')} />
        <TabButton id="permission" icon={Shield} label={t('page.mcdr.config.permission_yml')} />
      </div>

      <AnimatePresence mode="wait">
        {activeTab === 'config' ? (
          <motion.div
            key="config"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 20 }}
            className="grid grid-cols-1 lg:grid-cols-3 gap-8"
          >
            {/* Left Column - Main Config */}
            <div className="lg:col-span-2 space-y-8">
              {/* Basic Settings */}
              <ConfigSection title={t('page.mcdr.config.basic')} icon={Globe}>
                <div className="space-y-6">
                  <ConfigItem
                    label={t('page.mcdr.form.language')}
                    sub={t('page.mcdr.form.language_tip')}
                  >
                    <NiceSelect
                      value={configData.language || 'en_us'}
                      onChange={(val) => updateConfig('language', val)}
                      options={[
                        { value: 'en_us', label: t('page.mcdr.form.language_en') },
                        { value: 'zh_cn', label: t('page.mcdr.form.language_zh') }
                      ]}
                    />
                  </ConfigItem>

                  <ConfigItem
                    label={t('page.mcdr.form.working_directory')}
                    sub={t('page.mcdr.form.working_directory_tip')}
                  >
                    <input
                      type="text"
                      value={configData.working_directory || 'server'}
                      onChange={(e) => updateConfig('working_directory', e.target.value)}
                      className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-800 rounded-lg px-4 py-2 outline-none focus:ring-2 focus:ring-blue-500/50"
                    />
                  </ConfigItem>

                  <ConfigItem
                    label={t('page.mcdr.form.start_command')}
                    sub={t('page.mcdr.form.start_command_tip')}
                  >
                    <textarea
                      value={configData.start_command || ''}
                      onChange={(e) => updateConfig('start_command', e.target.value)}
                      rows={3}
                      placeholder={t('page.mcdr.form.start_example')}
                      className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-800 rounded-lg px-4 py-2 outline-none focus:ring-2 focus:ring-blue-500/50 resize-none font-mono text-sm"
                    />
                  </ConfigItem>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <ConfigItem label={t('page.mcdr.form.handler')} sub={t('page.mcdr.form.handler_tip')}>
                    <button
                      type="button"
                      onClick={() => setShowHandlerModal(true)}
                      className="w-full flex items-center justify-between px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:border-blue-400 hover:bg-blue-50/40 dark:hover:bg-slate-800 transition-all"
                    >
                      <div className="flex flex-col">
                        <span className="text-sm font-semibold text-slate-900 dark:text-white">
                          {configData.handler || 'vanilla_handler'}
                        </span>
                        <span className="text-xs text-slate-500 dark:text-slate-400">
                          {t('page.mcdr.form.handler_tip')}
                        </span>
                      </div>
                      <ChevronRight size={18} className="text-slate-400" />
                    </button>
                  </ConfigItem>

                    <ConfigItem label={t('page.mcdr.form.check_update')} sub={t('page.mcdr.form.check_update_tip')}>
                      <div className="flex items-center">
                        <Switch
                          checked={configData.check_update !== false}
                          onChange={(v) => updateConfig('check_update', v)}
                        />
                      </div>
                    </ConfigItem>
                  </div>
                </div>
              </ConfigSection>

              {/* RCON Settings */}
              <ConfigSection title={t('page.mcdr.rcon.title')} icon={Terminal}>
                <div className="space-y-6">
                  <div className="flex items-center justify-between p-4 bg-blue-50 dark:bg-blue-900/10 border border-blue-100 dark:border-blue-900/30 rounded-xl">
                    <div className="flex items-center gap-3">
                      <Zap className="text-blue-500" size={24} />
                      <div>
                        <h4 className="font-semibold text-blue-900 dark:text-blue-200">{t('page.mcdr.rcon.setup_button')}</h4>
                        <p className="text-sm text-blue-700 dark:text-blue-300">{t('page.mcdr.rcon.desc')}</p>
                      </div>
                    </div>
                    <button
                      onClick={() => setShowRconSetupModal(true)}
                      className="px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white text-sm font-medium rounded-lg transition-colors whitespace-nowrap"
                    >
                      {t('page.mcdr.rcon.setup_button')}
                    </button>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <ConfigItem label={t('page.mcdr.rcon.enable')} sub={t('page.mcdr.rcon.enable_tip')}>
                      <Switch
                        checked={configData.rcon?.enable === true}
                        onChange={(v) => updateConfig('rcon.enable', v)}
                      />
                    </ConfigItem>
                    <ConfigItem label={t('page.mcdr.rcon.address')} sub={t('page.mcdr.rcon.address_tip')}>
                    <input
                      type="text"
                      value={configData.rcon?.address || '127.0.0.1'}
                      onChange={(e) => updateConfig('rcon.address', e.target.value)}
                      className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-800 rounded-lg px-4 py-2 outline-none focus:ring-2 focus:ring-blue-500/50"
                    />
                  </ConfigItem>
                    <ConfigItem label={t('page.mcdr.rcon.port')} sub={t('page.mcdr.rcon.port_tip')}>
                    <input
                      type="number"
                      value={configData.rcon?.port || 25575}
                      onChange={(e) => updateConfig('rcon.port', parseInt(e.target.value))}
                      className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-800 rounded-lg px-4 py-2 outline-none focus:ring-2 focus:ring-blue-500/50"
                    />
                  </ConfigItem>
                    <ConfigItem label={t('page.mcdr.rcon.password')} sub={t('page.mcdr.rcon.password_tip')}>
                    <input
                      type="password"
                      value={configData.rcon?.password || ''}
                      autoComplete="new-password"
                      onChange={(e) => updateConfig('rcon.password', e.target.value)}
                      className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-800 rounded-lg px-4 py-2 outline-none focus:ring-2 focus:ring-blue-500/50"
                    />
                  </ConfigItem>
                  </div>
                </div>
              </ConfigSection>
            </div>

            {/* Right Column - Misc Settings */}
            <div className="space-y-8">
              {/* Debug Settings */}
              <ConfigSection title={t('page.mcdr.debug.title')} icon={AlertCircle}>
                <div className="space-y-4">
                  <ConfigItem label={t('page.mcdr.debug.all')}>
                    <Switch
                      checked={configData.debugging?.all === true}
                      onChange={(v) => updateConfig('debugging.all', v)}
                    />
                  </ConfigItem>
                  <div className="pt-2 border-t border-slate-100 dark:border-slate-800 space-y-3">
                    {['mcdr', 'handler', 'reactor', 'plugin', 'permission', 'command', 'task_executor'].map((key) => (
                      <div key={key} className="flex items-center justify-between text-sm">
                        <span className="text-slate-600 dark:text-slate-400">{t(`page.mcdr.debug.${key}`)}</span>
                        <Switch
                          checked={configData.debugging?.[key] === true}
                          onChange={(v) => updateConfig(`debugging.${key}`, v)}
                          size="sm"
                        />
                      </div>
                    ))}
                  </div>
                </div>
              </ConfigSection>

              {/* Advanced UI Settings */}
              <ConfigSection title={t('page.mcdr.form.advanced_console')} icon={Loader2}>
                <div className="space-y-6">
                  <ConfigItem label={t('page.mcdr.form.advanced_console')} sub={t('page.mcdr.form.advanced_console_tip')}>
                    <Switch
                      checked={configData.advanced_console !== false}
                      onChange={(v) => updateConfig('advanced_console', v)}
                    />
                  </ConfigItem>
                  <ConfigItem label={t('page.mcdr.form.disable_console_color')} sub={t('page.mcdr.form.disable_console_color_tip')}>
                    <Switch
                      checked={configData.disable_console_color === true}
                      onChange={(v) => updateConfig('disable_console_color', v)}
                    />
                  </ConfigItem>
                </div>
              </ConfigSection>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="permission"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            className="space-y-6"
          >
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {['owner', 'admin', 'helper', 'user', 'guest'].map((level) => (
                <div
                  key={level}
                  className="bg-white dark:bg-slate-900 rounded-3xl shadow-sm border border-slate-200 dark:border-slate-800 overflow-hidden"
                >
                  <div className={`px-4 py-3 flex items-center justify-between ${level === 'owner' ? 'bg-red-500/10 text-red-600' :
                      level === 'admin' ? 'bg-orange-500/10 text-orange-600' :
                        level === 'helper' ? 'bg-blue-500/10 text-blue-600' :
                          'bg-slate-500/10 text-slate-600 dark:text-slate-400'
                    }`}>
                    <div className="flex items-center gap-2">
                      <Shield size={18} />
                      <h3 className="font-bold uppercase tracking-wider text-sm">
                        {t(`page.mcdr.perm.${level}`)}
                      </h3>
                    </div>
                    <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-white dark:bg-slate-900 border border-current opacity-60">
                      {level === 'owner' ? 'LVL 4' : level === 'admin' ? 'LVL 3' : level === 'helper' ? 'LVL 2' : level === 'user' ? 'LVL 1' : 'LVL 0'}
                    </span>
                  </div>

                  <div className="p-4 space-y-4">
                    <p className="text-xs text-slate-500 line-clamp-2">
                      {t(`page.mcdr.perm.${level}_tip`)}
                    </p>

                    <div className="flex flex-wrap gap-2 min-h-[40px] p-2 bg-slate-50 dark:bg-slate-900/60 rounded-lg border border-dashed border-slate-200 dark:border-slate-800">
                      {(permissionData[level] || []).map((player: string, index: number) => (
                        <div
                          key={`${level}-${index}`}
                          className="group flex items-center gap-1.5 px-2 py-1 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-800 rounded-md shadow-sm animate-in zoom-in-95 duration-200"
                        >
                          <span className="text-xs font-medium text-slate-700 dark:text-slate-300">{player}</span>
                          <button
                            onClick={() => removePlayer(level, index)}
                            className="text-slate-400 hover:text-red-500 transition-colors"
                          >
                            <X size={12} />
                          </button>
                        </div>
                      ))}
                      {playerAddingToLevel === level ? (
                        <div className="flex items-center gap-2 w-full mt-2">
                          <input
                            autoFocus
                            type="text"
                            value={newPlayerName}
                            onChange={(e) => setNewPlayerName(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && addPlayer(level)}
                            onBlur={() => !newPlayerName && setPlayerAddingToLevel(null)}
                            placeholder={t('page.mcdr.perm.add_player_placeholder')}
                            className="flex-1 bg-white dark:bg-slate-800 border border-blue-500 rounded px-2 py-1 text-xs outline-none shadow-sm shadow-blue-500/20"
                          />
                          <button onClick={() => addPlayer(level)} className="text-blue-500"><CheckCircle2 size={16} /></button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setPlayerAddingToLevel(level)}
                          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-md transition-colors"
                        >
                          <UserPlus size={14} />
                          {t('page.mcdr.perm.add_player')}
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      </div>

      {/* RCON Modals */}
      <Modal
        isOpen={showRconSetupModal}
        onClose={() => setShowRconSetupModal(false)}
        title={t('page.mcdr.rcon.setup_modal_title')}
      >
        <div className="space-y-4">
          <p className="text-gray-600 dark:text-gray-400">{t('page.mcdr.rcon.setup_description')}</p>
          <ul className="space-y-2 text-sm bg-gray-50 dark:bg-gray-900/50 p-4 rounded-lg">
            <li className="flex items-center gap-2"><ChevronRight size={14} className="text-blue-500" /> {t('page.mcdr.rcon.setup_ip')}</li>
            <li className="flex items-center gap-2"><ChevronRight size={14} className="text-blue-500" /> {t('page.mcdr.rcon.setup_port')}</li>
            <li className="flex items-center gap-2"><ChevronRight size={14} className="text-blue-500" /> {t('page.mcdr.rcon.setup_password')}</li>
          </ul>
          <div className="p-3 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-900/30 rounded-lg flex gap-3">
            <Info className="text-yellow-600 shrink-0" size={20} />
            <p className="text-xs text-yellow-800 dark:text-yellow-200">{t('page.mcdr.rcon.setup_warning')}</p>
          </div>
          <div className="flex gap-3 pt-4">
            <button
              onClick={() => setShowRconSetupModal(false)}
              className="flex-1 px-4 py-2 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-600 dark:text-gray-400 font-medium hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors"
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
          <div className="p-4 bg-green-50 dark:bg-green-900/20 border border-green-100 dark:border-green-900/30 rounded-xl">
            <div className="flex items-center gap-2 text-green-700 dark:text-green-300 font-bold mb-3">
              <CheckCircle2 size={20} />
              {t('page.mcdr.rcon.setup_success')}
            </div>
            <div className="space-y-1 text-sm font-mono opacity-80">
              <div className="flex justify-between"><span>{t('page.mcdr.rcon.config_host')}:</span> <span>{rconConfig?.rcon_host}</span></div>
              <div className="flex justify-between"><span>{t('page.mcdr.rcon.config_port')}:</span> <span>{rconConfig?.rcon_port}</span></div>
              <div className="flex justify-between"><span>{t('page.mcdr.rcon.config_password')}:</span> <span>{rconConfig?.rcon_password}</span></div>
            </div>
          </div>
          <p className="text-gray-600 dark:text-gray-400">{t('page.mcdr.rcon.restart_question')}</p>
          <div className="flex gap-3 pt-4">
            <button
              onClick={() => setShowRconRestartModal(false)}
              className="flex-1 px-4 py-2 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-600 dark:text-gray-400 font-medium hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors"
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

      {/* Handler Select Modal */}
      <Modal
        isOpen={showHandlerModal}
        onClose={() => setShowHandlerModal(false)}
        title={t('page.mcdr.form.handler')}
      >
        <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
          <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">
            {t('page.mcdr.form.handler_modal_desc')}
          </p>
          {[
            { value: 'vanilla_handler', key: 'vanilla' },
            { value: 'beta18_handler', key: 'beta18' },
            { value: 'bukkit_handler', key: 'bukkit' },
            { value: 'bukkit14_handler', key: 'bukkit14' },
            { value: 'forge_handler', key: 'forge' },
            { value: 'cat_server_handler', key: 'cat_server' },
            { value: 'arclight_handler', key: 'arclight' },
            { value: 'bungeecord_handler', key: 'bungeecord' },
            { value: 'waterfall_handler', key: 'waterfall' },
            { value: 'velocity_handler', key: 'velocity' },
            { value: 'basic_handler', key: 'basic' }
          ].map((opt) => {
            const active = (configData.handler || 'vanilla_handler') === opt.value;
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => {
                  updateConfig('handler', opt.value);
                  setShowHandlerModal(false);
                }}
                className={`w-full text-left px-4 py-3 rounded-2xl border transition-all flex flex-col gap-1 ${
                  active
                    ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20 shadow-sm'
                    : 'border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:border-blue-400 hover:bg-blue-50/60 dark:hover:bg-slate-800'
                }`}
              >
                <span className="text-sm font-semibold text-slate-900 dark:text-white">
                  {t(`page.mcdr.form.handler_option.${opt.key}`)}
                </span>
                <span className="text-xs text-slate-500 dark:text-slate-400">
                  {t(`page.mcdr.form.handler_detail.${opt.key}`)}
                </span>
                <span className="text-[10px] font-mono text-slate-400">
                  handler: {opt.value}
                </span>
              </button>
            );
          })}
        </div>
      </Modal>

      {/* Notifications */}
      <AnimatePresence>
        {showNotification && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            className={`fixed bottom-6 right-6 z-50 flex items-center gap-3 px-6 py-4 rounded-2xl shadow-2xl ${notificationType === 'success'
                ? 'bg-emerald-500 text-white shadow-emerald-500/20'
                : 'bg-rose-500 text-white shadow-rose-500/20'
              }`}
          >
            {notificationType === 'success' ? <CheckCircle2 size={20} /> : <AlertCircle size={20} />}
            <span className="font-medium">{notificationMsg}</span>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
};

// Sub-components
const ConfigSection: React.FC<{ title: string; icon: any; children: React.ReactNode }> = ({ title, icon: Icon, children }) => (
  <div className="bg-white dark:bg-slate-900 rounded-3xl shadow-sm border border-slate-200 dark:border-slate-800 overflow-hidden">
    <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-800 flex items-center gap-3 bg-slate-50/50 dark:bg-slate-900/50">
      <div className="p-2 bg-blue-500/10 text-blue-500 rounded-lg">
        <Icon size={20} />
      </div>
      <h2 className="text-lg font-bold text-slate-900 dark:text-white">{title}</h2>
    </div>
    <div className="p-6">{children}</div>
  </div>
);

const ConfigItem: React.FC<{ label: string; sub?: string; children: React.ReactNode }> = ({ label, sub, children }) => (
  <div className="space-y-1.5">
    <label className="text-sm font-semibold text-slate-700 dark:text-slate-200 flex items-center justify-between">
      {label}
    </label>
    {children}
    {sub && <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">{sub}</p>}
  </div>
);

const Switch: React.FC<{ checked: boolean; onChange: (v: boolean) => void, size?: 'sm' | 'md' }> = ({ checked, onChange, size = 'md' }) => (
  <button
    onClick={() => onChange(!checked)}
    className={`relative transition-colors rounded-full focus:outline-none focus:ring-2 focus:ring-blue-500/20 ${checked ? 'bg-blue-500' : 'bg-slate-300 dark:bg-slate-700'
      } ${size === 'md' ? 'w-12 h-6' : 'w-10 h-5'}`}
  >
    <motion.div
      animate={{ x: checked ? (size === 'md' ? 26 : 22) : 2 }}
      className={`absolute top-1 bg-white rounded-full shadow-sm ${size === 'md' ? 'w-4 h-4' : 'w-3 h-3'}`}
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

export default MCDRConfig;
