// 本地插件页面的JavaScript功能
document.addEventListener('alpine:init', () => {
    Alpine.data('pluginsData', () => ({
        serverStatus: 'loading',
        userName: '',
        serverVersion: '',
        serverPlayers: '0/0',
        plugins: [],
        loading: true,
        searchQuery: '',
        notificationMessage: '',
        notificationType: 'success',
        showNotification: false,
        processingPlugins: {},
        showConfigModal: false,
        currentPlugin: null,
        configFiles: [],
        selectedFile: '',
        configContent: '',
        showEditor: false,
        editorMode: 'code', // 'code' or 'form'
        codeMirrorEditor: null,
        configData: null,
        configTranslations: {}, // 添加翻译数据存储
        // 插件安装相关属性
        installTaskId: null,
        installProgress: 0,
        installMessage: '',
        installStatus: 'pending', // pending, running, completed, failed
        showInstallModal: false,
        installPluginId: '',
        installLogMessages: [],
        installProgressTimer: null,

        // 添加确认模态框相关属性
        showConfirmModal: false,
        confirmTitle: '',
        confirmMessage: '',
        confirmAction: null,
        confirmPluginId: '',
        confirmType: '', // 'uninstall', 'reload', 'update'

        // 添加版本切换相关属性
        showVersionModal: false,
        versionsLoading: false,
        versionError: false,
        versionErrorMessage: '',
        currentVersionPlugin: null, 
        versions: [],
        installedVersion: null,

        // 比较两个版本号的函数 
        // 返回值: 如果v1 > v2，返回1；如果v1 < v2，返回-1；如果相等，返回0
        compareVersions(v1, v2) {
            if (!v1) return -1;
            if (!v2) return 1;
            
            // 移除版本号前的'v'字符
            v1 = v1.toString().replace(/^v/, '');
            v2 = v2.toString().replace(/^v/, '');
            
            // 分割版本号为数字数组
            const parts1 = v1.split('.').map(Number);
            const parts2 = v2.split('.').map(Number);
            
            // 比较每个部分
            for (let i = 0; i < Math.max(parts1.length, parts2.length); i++) {
                const p1 = i < parts1.length ? parts1[i] : 0;
                const p2 = i < parts2.length ? parts2[i] : 0;
                
                if (p1 > p2) return 1;
                if (p1 < p2) return -1;
            }
            
            return 0; // 版本相同
        },

        async checkLoginStatus() {
            try {
                const response = await fetch('api/checkLogin');
                const data = await response.json();
                if (data.status === 'success') {
                    this.userName = data.username;
                }
            } catch (error) {
                console.error('Error checking login status:', error);
            }
        },
        
        async checkServerStatus() {
            try {
                this.serverStatus = 'loading';
                const response = await fetch('api/get_server_status');
                const data = await response.json();
                this.serverStatus = data.status || 'offline';
                this.serverVersion = data.version || '';
                this.serverPlayers = data.players || '0/0';
            } catch (error) {
                console.error('Error checking server status:', error);
                this.serverStatus = 'error';
            }
        },

        async loadPlugins() {
            try {
                this.loading = true;
                const response = await fetch('api/plugins?detail=true');
                const data = await response.json();
                this.plugins = data.plugins || [];
                this.loading = false;
                
                // 确保每个插件的处理状态被正确初始化
                if (this.plugins && this.plugins.length > 0) {
                    this.plugins.forEach(plugin => {
                        if (!this.processingPlugins.hasOwnProperty(plugin.id)) {
                            this.processingPlugins[plugin.id] = false;
                        }
                    });
                }
            } catch (error) {
                console.error('Error loading plugins:', error);
                this.loading = false;
                this.showNotificationMsg('加载插件列表失败', 'error');
            }
        },

        async togglePlugin(pluginId, targetStatus) {
            if (pluginId === 'guguwebui') {
                this.showNotificationMsg('不能切换 WebUI 插件的状态', 'error');
                return;
            }

            this.processingPlugins[pluginId] = true;
            
            try {
                const response = await fetch('api/toggle_plugin', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        plugin_id: pluginId,
                        status: targetStatus
                    })
                });
                
                const result = await response.json();
                
                if (result.status === 'success') {
                    // 更新插件状态
                    await this.loadPlugins();
                    this.showNotificationMsg(`${targetStatus ? '启用' : '禁用'}插件成功`, 'success');
                } else {
                    this.showNotificationMsg(`${targetStatus ? '启用' : '禁用'}插件失败: ${result.message || ''}`, 'error');
                }
            } catch (error) {
                console.error(`Error toggling plugin ${pluginId}:`, error);
                this.showNotificationMsg(`${targetStatus ? '启用' : '禁用'}插件失败`, 'error');
            } finally {
                this.processingPlugins[pluginId] = false;
            }
        },

        async reloadPlugin(pluginId) {
            if (pluginId === 'guguwebui') {
                this.showNotificationMsg('不能重载 WebUI 插件', 'error');
                return;
            }

            // 使用确认模态框
            this.openConfirmModal(
                'reload', 
                pluginId,
                '重载插件',
                `确定要重载插件 ${pluginId} 吗？`,
                async (id) => {
                    this.processingPlugins[id] = true;
                    
                    try {
                        const response = await fetch('api/reload_plugin', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({
                                plugin_id: id
                            })
                        });
                        
                        const result = await response.json();
                        
                        if (result.status === 'success') {
                            await this.loadPlugins();
                            this.showNotificationMsg('重载插件成功', 'success');
                        } else {
                            this.showNotificationMsg(`重载插件失败: ${result.message || ''}`, 'error');
                        }
                    } catch (error) {
                        console.error(`Error reloading plugin ${id}:`, error);
                        this.showNotificationMsg('重载插件失败', 'error');
                    } finally {
                        this.processingPlugins[id] = false;
                    }
                }
            );
        },

        async updatePlugin(pluginId) {
            if (pluginId === 'guguwebui') {
                this.showNotificationMsg('不能更新 WebUI 插件', 'error');
                return;
            }

            // 使用确认模态框
            this.openConfirmModal(
                'update', 
                pluginId,
                '更新插件',
                `确定要更新插件 ${pluginId} 吗？`,
                async (id) => {
                    this.processingPlugins[id] = true;
                    
                    try {
                        // 准备安装模态框
                        this.installPluginId = id;
                        this.installProgress = 0;
                        this.installMessage = '正在准备更新...';
                        this.installStatus = 'running';
                        this.installLogMessages = [];
                        this.showInstallModal = true;
                        
                        // 尝试使用新版PIM安装器API更新插件
                        let response = await fetch('api/pim/update_plugin', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({
                                plugin_id: id
                            })
                        });
                        
                        let result = await response.json();
                        
                        // 判断是否成功使用PIM API
                        if (result.success) {
                            // 使用PIM API成功
                            this.installTaskId = result.task_id;
                            console.log(`使用PIM API更新插件 ${id}, 任务ID: ${result.task_id}`);
                            
                            // 开始轮询安装进度，2秒查询一次
                            this.installProgressTimer = setInterval(() => {
                                this.checkInstallProgress();
                            }, 2000);
                            
                            // 立即执行一次查询，避免等待第一个间隔
                            this.checkInstallProgress();
                        } else if (response.status !== 404 && !result.error?.includes('未知API')) {
                            // PIM API请求失败，但服务端存在此API（非404错误）
                            this.installStatus = 'failed';
                            this.installMessage = `更新失败: ${result.error || ''}`;
                            this.showNotificationMsg(`更新插件失败: ${result.error || ''}`, 'error');
                            this.processingPlugins[id] = false;
                        }
                    } catch (error) {
                        console.error(`Error updating plugin ${id}:`, error);
                        this.installStatus = 'failed';
                        this.installMessage = '更新插件失败';
                        this.showNotificationMsg('更新插件失败', 'error');
                        this.processingPlugins[id] = false;
                    }
                }
            );
        },

        // 安装插件函数
        async installPlugin(pluginId) {
            if (this.processingPlugins[pluginId]) return;
            
            // 前端拦截guguwebui安装请求
            if (pluginId === "guguwebui") {
                this.showNotificationMsg('不允许安装WebUI自身，这可能会导致WebUI无法正常工作', 'error');
                return;
            }
            
            // 使用确认模态框
            this.openConfirmModal(
                'install', 
                pluginId,
                '安装插件',
                `确定要安装插件 ${pluginId} 吗？`,
                async (id) => {
                    this.processingPlugins[id] = true;
                    
                    try {
                        // 准备安装模态框
                        this.installPluginId = id;
                        this.installProgress = 0;
                        this.installMessage = '正在准备安装...';
                        this.installStatus = 'running';
                        this.installLogMessages = [];
                        this.showInstallModal = true;
                        
                        // 尝试使用新版PIM安装器API
                        let response = await fetch('api/pim/install_plugin', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({
                                plugin_id: id
                            })
                        });
                        
                        let result = await response.json();
                        
                        // 判断是否成功使用PIM API
                        if (result.success) {
                            // 使用PIM API成功
                            this.installTaskId = result.task_id;
                            console.log(`使用PIM API安装插件 ${id}, 任务ID: ${result.task_id}`);
                            
                            // 开始轮询安装进度，2秒查询一次
                            this.installProgressTimer = setInterval(() => {
                                this.checkInstallProgress();
                            }, 2000);
                            
                            // 立即执行一次查询，避免等待第一个间隔
                            this.checkInstallProgress();
                        } else if (response.status !== 404 && !result.error?.includes('未知API')) {
                            // PIM API请求失败，但服务端存在此API（非404错误）
                            this.installStatus = 'failed';
                            this.installMessage = `安装失败: ${result.error || ''}`;
                            this.showNotificationMsg(`安装插件失败: ${result.error || ''}`, 'error');
                            this.processingPlugins[id] = false;
                        }
                    } catch (error) {
                        console.error(`Error installing plugin ${id}:`, error);
                        this.installStatus = 'failed';
                        this.installMessage = '安装插件失败';
                        this.showNotificationMsg('安装插件失败', 'error');
                        this.processingPlugins[id] = false;
                    }
                }
            );
        },
        
        // 检查安装进度
        async checkInstallProgress() {
            if (!this.installTaskId) return;
            
            try {
                console.log(`检查任务 ${this.installTaskId} 进度，插件ID: ${this.installPluginId}`);
                const response = await fetch(`api/pim/task_status?task_id=${this.installTaskId}&plugin_id=${this.installPluginId}`);
                const data = await response.json();
                
                if (data.success && data.task_info) {
                    const taskInfo = data.task_info;
                    console.log('收到任务信息:', taskInfo);
                    
                    // 更新进度和消息
                    this.installProgress = taskInfo.progress * 100;
                    this.installMessage = taskInfo.message || '处理中...';
                    this.installStatus = taskInfo.status;
                    
                    // 更新日志消息
                    if (taskInfo.all_messages && Array.isArray(taskInfo.all_messages)) {
                        // 确保日志消息是新的
                        if (JSON.stringify(this.installLogMessages) !== JSON.stringify(taskInfo.all_messages)) {
                            this.installLogMessages = taskInfo.all_messages;
                        }
                    } else if (taskInfo.error_messages && Array.isArray(taskInfo.error_messages)) {
                        // 确保错误消息是新的
                        if (JSON.stringify(this.installLogMessages) !== JSON.stringify(taskInfo.error_messages)) {
                            this.installLogMessages = taskInfo.error_messages;
                        }
                    }
                    
                    // 强制立即更新DOM
                    this.$nextTick(() => {
                        document.getElementById('install-progress-bar').style.width = `${this.installProgress}%`;
                        document.getElementById('install-progress-text').textContent = `${Math.round(this.installProgress)}%`;
                    });
                    
                    // 检查任务是否完成
                    if (taskInfo.status === 'completed' || taskInfo.status === 'failed') {
                        // 停止轮询
                        if (this.installProgressTimer) {
                            clearInterval(this.installProgressTimer);
                            this.installProgressTimer = null;
                        }
                        
                        // 加载最新的插件列表
                        await this.loadPlugins();
                        
                        // 设置处理状态
                        this.processingPlugins[this.installPluginId] = false;
                        
                        // 显示完成通知
                        if (taskInfo.status === 'completed') {
                            this.showNotificationMsg(`插件 ${this.installPluginId} 操作成功！`, 'success');
                        } else {
                            this.showNotificationMsg(`插件 ${this.installPluginId} 操作失败: ${taskInfo.message}`, 'error');
                        }
                    }
                } else if (response.status === 404 || (data.error && data.error.includes('不存在'))) {
                    console.log(`任务 ${this.installTaskId} 不存在，尝试刷新插件列表检查状态`);
                    
                    // 重新尝试直接使用插件ID查询
                    try {
                        const retryResponse = await fetch(`api/pim/task_status?plugin_id=${this.installPluginId}`);
                        const retryData = await retryResponse.json();
                        
                        if (retryData.success && retryData.task_info) {
                            console.log(`找到插件 ${this.installPluginId} 的任务`, retryData.task_info);
                            // 更新任务ID和任务信息
                            this.installTaskId = retryData.task_info.id || this.installTaskId;
                            
                            // 更新进度和消息
                            this.installProgress = retryData.task_info.progress * 100;
                            this.installMessage = retryData.task_info.message || '处理中...';
                            this.installStatus = retryData.task_info.status;
                            
                            // 更新日志消息
                            if (retryData.task_info.all_messages && Array.isArray(retryData.task_info.all_messages)) {
                                this.installLogMessages = retryData.task_info.all_messages;
                            } else if (retryData.task_info.error_messages && Array.isArray(retryData.task_info.error_messages)) {
                                this.installLogMessages = retryData.task_info.error_messages;
                            }
                            
                            // 如果任务已经完成或失败
                            if (retryData.task_info.status === 'completed' || retryData.task_info.status === 'failed') {
                                // 停止轮询
                                if (this.installProgressTimer) {
                                    clearInterval(this.installProgressTimer);
                                    this.installProgressTimer = null;
                                }
                                
                                // 刷新插件列表
                                await this.loadPlugins();
                                
                                // 设置处理状态
                                this.processingPlugins[this.installPluginId] = false;
                                
                                // 显示通知
                                if (retryData.task_info.status === 'completed') {
                                    this.showNotificationMsg(`插件 ${this.installPluginId} 操作成功！`, 'success');
                                } else {
                                    this.showNotificationMsg(`插件 ${this.installPluginId} 操作失败: ${retryData.task_info.message}`, 'error');
                                }
                                return;
                            }
                            
                            // 如果找到了正在进行的任务，继续轮询
                            return;
                        }
                    } catch (retryError) {
                        console.warn('重试查询任务状态失败:', retryError);
                    }
                    
                    // 检查插件是否已经安装成功（通过加载插件列表来检查）
                    await this.loadPlugins();
                    
                    // 标记为完成
                    this.installStatus = 'completed';
                    this.installProgress = 100;
                    this.installMessage = `插件 ${this.installPluginId} 操作可能已完成，请检查插件列表`;
                    
                    // 停止轮询
                    if (this.installProgressTimer) {
                        clearInterval(this.installProgressTimer);
                        this.installProgressTimer = null;
                    }
                    
                    // 设置处理状态
                    this.processingPlugins[this.installPluginId] = false;
                    
                    // 显示通知
                    this.showNotificationMsg(`任务状态未知，请检查插件列表确认是否成功`, 'info');
                } else if (data.error) {
                    console.warn('获取任务状态出错，但将继续尝试:', data.error);
                    this.installMessage = "获取任务状态出错，但操作可能正在进行中...";
                    this.installLogMessages.push(`获取任务状态出错: ${data.error}`);
                }
            } catch (error) {
                console.error('Error checking install progress:', error);
                // 错误可能是暂时的，继续轮询
                this.installMessage = "获取任务状态出错，但操作可能正在进行中...";
                this.installLogMessages.push(`获取任务状态出错: ${error.message}`);
            }
        },
        
        // 关闭安装模态框
        closeInstallModal() {
            if (this.installStatus === 'running') {
                // 如果任务仍在运行，只关闭模态框但继续轮询进度
                this.showInstallModal = false;
            } else {
                // 完全清理状态
                this.showInstallModal = false;
                this.installTaskId = null;
                this.installProgress = 0;
                this.installMessage = '';
                this.installStatus = 'pending';
                this.installPluginId = '';
                this.installLogMessages = [];
                
                if (this.installProgressTimer) {
                    clearInterval(this.installProgressTimer);
                    this.installProgressTimer = null;
                }
            }
        },

        getPluginStatus(plugin) {
            if (plugin.status === true || plugin.status === 'loaded') return 'active';
            if (plugin.status === false || plugin.status === 'disabled') return 'inactive';
            if (plugin.status === 'unloaded') return 'unloaded';
            return 'error';
        },

        filterPlugins() {
            if (!this.searchQuery) return this.plugins;
            
            const query = this.searchQuery.toLowerCase();
            return this.plugins.filter(plugin => 
                plugin.id.toLowerCase().includes(query) ||
                plugin.name.toLowerCase().includes(query) ||
                (plugin.description && plugin.description.toLowerCase().includes(query)) ||
                (plugin.author && plugin.author.toLowerCase().includes(query))
            );
        },

        showNotificationMsg(message, type = 'success') {
            this.notificationMessage = message;
            this.notificationType = type;
            this.showNotification = true;
            
            setTimeout(() => {
                this.showNotification = false;
            }, 5000);
        },

        async openConfigModal(plugin) {
            this.currentPlugin = plugin;
            this.configFiles = [];
            this.selectedFile = '';
            this.configContent = '';
            this.showEditor = false;
            this.showConfigModal = true;
            
            try {
                const response = await fetch(`api/list_config_files?plugin_id=${plugin.id}`);
                const data = await response.json();
                this.configFiles = data.files || [];
            } catch (error) {
                console.error('Error fetching config files:', error);
                this.showNotificationMsg('获取配置文件列表失败', 'error');
            }
        },
        
        async openConfigFile(file, mode = 'code') {
            this.selectedFile = file;
            this.editorMode = mode;
            this.showEditor = true;
            this.configTranslations = {}; // 重置翻译数据
            
            // 清除已有的编辑器实例
            if (this.codeMirrorEditor) {
                this.codeMirrorEditor.toTextArea();
                this.codeMirrorEditor = null;
            }
            
            try {
                if (mode === 'code') {
                    // 以代码编辑器模式打开
                    const response = await fetch(`api/load_config_file?path=${file}`);
                    this.configContent = await response.text();
                    
                    // 使用setTimeout确保DOM已更新
                    setTimeout(() => {
                        const fileExt = file.split('.').pop().toLowerCase();
                        let editorMode = 'text/plain';
                        
                        if (fileExt === 'json') editorMode = 'application/json';
                        else if (fileExt === 'yml' || fileExt === 'yaml') editorMode = 'text/x-yaml';
                        else if (fileExt === 'properties') editorMode = 'text/x-properties';
                        
                        const editorElement = document.getElementById('config-editor');
                        if (editorElement) {
                            this.codeMirrorEditor = CodeMirror.fromTextArea(editorElement, {
                                mode: editorMode,
                                lineNumbers: true,
                                theme: this.darkMode ? 'darcula' : 'default',
                                lineWrapping: true,
                                autoCloseBrackets: true,
                                matchBrackets: true,
                                indentUnit: 2,
                                tabSize: 2
                            });
                        }
                    }, 100);
                } else {
                    // 以表单模式打开
                    const response = await fetch(`api/load_config?path=${file}`);
                    const data = await response.json();
                    
                    // 重置状态，完全替换数据以触发Alpine.js响应式更新
                    this.configData = {};
                    
                    // 使用setTimeout确保DOM和Alpine.js的响应式系统有时间处理第一步的清空操作
                    setTimeout(() => {
                        try {
                            // 检查是否是HTML类型响应
                            if (data && data.type === 'html') {
                                this.configData = data; // 直接使用返回数据，包含type和content字段
                                
                                // 使用另一个setTimeout确保DOM已更新并且存在iframe元素
                                setTimeout(() => {
                                    const iframe = document.getElementById('html-config-iframe');
                                    if (iframe) {
                                        // 写入HTML内容到iframe
                                        const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                                        iframeDoc.open();
                                        iframeDoc.write(data.content);
                                        iframeDoc.close();
                                        
                                        // 调整iframe高度以适应内容
                                        iframe.onload = function() {
                                            try {
                                                const height = iframeDoc.body.scrollHeight;
                                                if (height > 400) {
                                                    iframe.style.height = height + 'px';
                                                }
                                            } catch (err) {
                                                console.warn('Unable to adjust iframe height:', err);
                                            }
                                        };
                                    }
                                }, 100);
                            } 
                            // 确保不是空数据
                            else if (data && typeof data === 'object') {
                                // 确保configData是一个空对象
                                this.configData = {};
                                
                                // 创建一个深复制，然后确保每个层级都已初始化
                                const processedData = JSON.parse(JSON.stringify(data));
                                
                                // 预处理嵌套对象，确保每个层级都是安全的
                                Object.keys(processedData).forEach(key => {
                                    if (typeof processedData[key] === 'object' && processedData[key] !== null && !Array.isArray(processedData[key])) {
                                        Object.keys(processedData[key]).forEach(nestedKey => {
                                            if (typeof processedData[key][nestedKey] === 'object' && processedData[key][nestedKey] !== null && !Array.isArray(processedData[key][nestedKey])) {
                                                Object.keys(processedData[key][nestedKey]).forEach(thirdKey => {
                                                    if (typeof processedData[key][nestedKey][thirdKey] === 'object' && processedData[key][nestedKey][thirdKey] !== null && !Array.isArray(processedData[key][nestedKey][thirdKey])) {
                                                        // 确保第四层对象存在
                                                        processedData[key][nestedKey][thirdKey] = processedData[key][nestedKey][thirdKey] || {};
                                                    }
                                                });
                                                // 确保第三层对象存在
                                                processedData[key][nestedKey] = processedData[key][nestedKey] || {};
                                            }
                                        });
                                        // 确保第二层对象存在
                                        processedData[key] = processedData[key] || {};
                                    }
                                });
                                
                                // 设置处理后的数据
                                this.configData = processedData;
                                
                                // 在加载配置数据后，请求翻译数据
                                setTimeout(async () => {
                                    try {
                                        // console.log(`正在请求翻译数据: /api/load_config?path=${file}&translation=true`);
                                        const translationResponse = await fetch(`api/load_config?path=${file}&translation=true`);
                                        const translationData = await translationResponse.json();
                                        if (translationData && typeof translationData === 'object') {
                                            // console.log('收到翻译数据:', translationData);
                                            this.configTranslations = translationData;
                                            
                                            // 检查配置数据中的嵌套结构，记录所有键
                                            const nestedKeys = [];
                                            if (this.configData) {
                                                Object.keys(this.configData).forEach(key => {
                                                    if (typeof this.configData[key] === 'object' && this.configData[key] !== null && !Array.isArray(this.configData[key])) {
                                                        Object.keys(this.configData[key]).forEach(nestedKey => {
                                                            nestedKeys.push(nestedKey);
                                                        });
                                                    }
                                                });
                                            }
                                            if (nestedKeys.length > 0) {
                                                // console.log('嵌套键列表:', nestedKeys);
                                                // console.log('匹配到的直接翻译:', nestedKeys.filter(key => this.configTranslations[key]).map(key => ({[key]: this.configTranslations[key]})));
                                            }
                                            
                                            // 添加一个小延迟，确保翻译应用后UI已更新
                                            setTimeout(() => {
                                                // console.log('翻译数据已应用到表单');
                                                // 这里可以执行表单初始化完成后的回调
                                            }, 200);
                                        } else {
                                            console.warn('未收到有效的翻译数据');
                                        }
                                    } catch (err) {
                                        console.warn('Error loading translations:', err);
                                    }
                                }, 100);
                            } else {
                                this.configData = {};
                                console.warn('Empty or invalid config data received');
                            }
                        } catch (err) {
                            console.error('Error processing config data:', err);
                            this.configData = {};
                        }
                    }, 100);
                }
            } catch (error) {
                console.error('Error loading config file:', error);
                this.showNotificationMsg('加载配置文件失败', 'error');
                // 确保在发生错误时也重置数据
                this.configData = {};
            }
        },
        
        async saveConfigFile() {
            try {
                if (this.editorMode === 'code') {
                    // 获取CodeMirror的内容
                    const content = this.codeMirrorEditor.getValue();
                    
                    const response = await fetch('api/save_config_file', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            action: this.selectedFile,
                            content: content
                        })
                    });
                    
                    const result = await response.json();
                    
                    if (result.status === 'success') {
                        this.showNotificationMsg('配置文件保存成功', 'success');
                        // 关闭编辑器
                        this.showEditor = false;
                        this.selectedFile = '';
                    } else {
                        this.showNotificationMsg(`保存失败: ${result.message || ''}`, 'error');
                    }
                } else {
                    // 如果是HTML类型，则不需要保存
                    if (this.configData && this.configData.type === 'html') {
                        this.showNotificationMsg('HTML界面不需要保存', 'success');
                        return;
                    }
                    
                    // 表单模式保存
                    const response = await fetch('api/save_config', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            file_path: this.selectedFile,
                            config_data: this.configData
                        })
                    });
                    
                    const result = await response.json();
                    
                    if (result.status === 'success') {
                        this.showNotificationMsg('配置文件保存成功', 'success');
                        // 关闭编辑器
                        this.showEditor = false;
                        this.selectedFile = '';
                    } else {
                        this.showNotificationMsg(`保存失败: ${result.message || ''}`, 'error');
                    }
                }
            } catch (error) {
                console.error('Error saving config file:', error);
                this.showNotificationMsg('保存配置文件失败', 'error');
            }
        },
        
        closeConfigModal() {
            this.showConfigModal = false;
            if (this.codeMirrorEditor) {
                // 确保在关闭模态窗口时释放CodeMirror实例
                this.codeMirrorEditor.toTextArea();
                this.codeMirrorEditor = null;
            }
        },
        
        closeEditor() {
            this.showEditor = false;
            this.selectedFile = '';
            if (this.codeMirrorEditor) {
                // 确保在关闭编辑器时释放CodeMirror实例
                this.codeMirrorEditor.toTextArea();
                this.codeMirrorEditor = null;
            }
        },

        // 添加重新加载当前文件的方法
        async reloadCurrentFile(mode) {
            if (this.selectedFile) {
                await this.openConfigFile(this.selectedFile, mode);
            }
        },
        
        // 卸载插件函数
        async uninstallPlugin(pluginId) {
            if (pluginId === 'guguwebui') {
                this.showNotificationMsg('不能卸载 WebUI 插件', 'error');
                return;
            }

            // 使用确认模态框
            this.openConfirmModal(
                'uninstall', 
                pluginId,
                '卸载插件',
                `确定要卸载插件 ${pluginId} 吗？此操作不可恢复，将彻底删除插件文件。\n支持卸载已加载和未加载的插件。`,
                async (id) => {
                    this.processingPlugins[id] = true;
                    
                    try {
                        // 准备安装模态框
                        this.installPluginId = id;
                        this.installProgress = 0;
                        this.installMessage = '正在准备卸载...';
                        this.installStatus = 'running';
                        this.installLogMessages = [];
                        this.showInstallModal = true;
                        
                        // 使用PIM API卸载插件
                        let response = await fetch('api/pim/uninstall_plugin', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({
                                plugin_id: id
                            })
                        });
                        
                        let result = await response.json();
                        
                        // 判断是否成功使用PIM API
                        if (result.success) {
                            // 使用PIM API成功
                            this.installTaskId = result.task_id;
                            console.log(`使用PIM API卸载插件 ${id}, 任务ID: ${result.task_id}`);
                            
                            // 开始轮询安装进度，2秒查询一次
                            this.installProgressTimer = setInterval(() => {
                                this.checkInstallProgress();
                            }, 2000);
                            
                            // 立即执行一次查询，避免等待第一个间隔
                            this.checkInstallProgress();
                        } else if (response.status !== 404 && !result.error?.includes('未知API')) {
                            // PIM API请求失败，但服务端存在此API（非404错误）
                            this.installStatus = 'failed';
                            this.installMessage = `卸载失败: ${result.error || ''}`;
                            this.showNotificationMsg(`卸载插件失败: ${result.error || ''}`, 'error');
                            this.processingPlugins[id] = false;
                        } else {
                            // 回退到简单的卸载方式（仅卸载不删除文件）
                            console.log('PIM API不可用，回退到基本卸载');
                            this.installMessage = '正在使用基本方式卸载...';
                            this.installLogMessages.push('PIM卸载器不可用，使用简单卸载方式');
                            
                            // 使用toggle_plugin接口将插件卸载
                            response = await fetch('api/toggle_plugin', {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json'
                                },
                                body: JSON.stringify({
                                    plugin_id: id,
                                    status: false
                                })
                            });
                            
                            result = await response.json();
                            
                            if (result.status === 'success') {
                                // 旧版API成功
                                this.installProgress = 100;
                                this.installStatus = 'completed';
                                this.installMessage = '插件已卸载（文件未删除）';
                                this.showNotificationMsg(`插件 ${id} 已卸载，但文件仍保留在服务器上`, 'warning');
                                
                                // 刷新插件列表
                                await this.loadPlugins();
                            } else {
                                // 旧版API失败
                                this.installStatus = 'failed';
                                this.installMessage = `卸载失败: ${result.message || ''}`;
                                this.showNotificationMsg(`卸载插件失败: ${result.message || ''}`, 'error');
                            }
                            
                            this.processingPlugins[id] = false;
                        }
                    } catch (error) {
                        console.error(`Error uninstalling plugin ${id}:`, error);
                        this.installStatus = 'failed';
                        this.installMessage = '卸载插件失败';
                        this.showNotificationMsg('卸载插件失败', 'error');
                        this.processingPlugins[id] = false;
                    }
                }
            );
        },
        
        // 打开确认模态框
        openConfirmModal(type, pluginId, title, message, action) {
            this.confirmType = type;
            this.confirmPluginId = pluginId;
            this.confirmTitle = title;
            this.confirmMessage = message;
            this.confirmAction = action;
            this.showConfirmModal = true;
        },
        
        // 关闭确认模态框
        closeConfirmModal() {
            this.showConfirmModal = false;
            this.confirmAction = null;
        },
        
        // 执行确认的操作
        async executeConfirmedAction() {
            if (this.confirmAction) {
                await this.confirmAction(this.confirmPluginId);
            }
            this.closeConfirmModal();
        },

        async showPluginVersions(plugin) {
            if (!plugin || plugin.id === 'guguwebui') {
                this.showNotificationMsg('不能为 WebUI 选择版本', 'error');
                return;
            }
            
            this.versionsLoading = true;
            this.versionError = false;
            this.currentVersionPlugin = plugin;
            this.installedVersion = plugin.version;
            this.versions = [];
            this.showVersionModal = true;
            
            try {
                const response = await fetch(`api/pim/plugin_versions_v2?plugin_id=${plugin.id}`);
                const result = await response.json();
                
                if (result.success) {
                    // 标记哪些版本正在处理中
                    this.versions = result.versions.map(version => ({
                        ...version,
                        processing: false
                    }));
                    this.installedVersion = result.installed_version;
                } else {
                    this.versionError = true;
                    this.versionErrorMessage = result.error || '获取版本列表失败';
                }
            } catch (error) {
                console.error(`Error loading versions for plugin ${plugin.id}:`, error);
                this.versionError = true;
                this.versionErrorMessage = '获取版本列表失败: ' + error.message;
            } finally {
                this.versionsLoading = false;
            }
        },
        
        async switchPluginVersion(version) {
            if (!this.currentVersionPlugin || !version) return;
            
            const pluginId = this.currentVersionPlugin.id;
            const versionObj = this.versions.find(v => v.version === version);
            
            if (!versionObj || versionObj.processing) return;
            
            // 检查是否与当前安装的版本相同
            if (this.installedVersion && version === this.installedVersion) {
                this.showNotificationMsg(`当前已安装 ${pluginId} 的 ${version} 版本`, 'info');
                return;
            }
            
            // 标记此版本为处理中
            versionObj.processing = true;
            
            try {
                // 先卸载，再安装指定版本
                if (this.installedVersion) {
                    const response = await fetch('api/pim/uninstall_plugin', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            plugin_id: pluginId
                        })
                    });
                    
                    const uninstallResult = await response.json();
                    if (!uninstallResult.success) {
                        throw new Error('卸载失败: ' + (uninstallResult.error || '未知错误'));
                    }
                    
                    // 获取卸载任务ID并开始轮询
                    if (uninstallResult.task_id) {
                        this.installTaskId = uninstallResult.task_id;
                        this.installPluginId = pluginId;
                        this.installStatus = 'running';
                        this.installProgress = 0;
                        this.installMessage = `正在卸载 ${pluginId}...`;
                        this.installLogMessages = [];
                        this.showInstallModal = true;
                        
                        // 开始轮询卸载进度
                        if (this.installProgressTimer) {
                            clearInterval(this.installProgressTimer);
                        }
                        this.installProgressTimer = setInterval(() => {
                            this.checkInstallProgress();
                        }, 2000);
                        
                        // 等待卸载完成
                        while (this.installStatus === 'running') {
                            await new Promise(resolve => setTimeout(resolve, 1000));
                        }
                        
                        if (this.installStatus === 'failed') {
                            throw new Error('卸载失败: ' + this.installMessage);
                        }
                    }
                }
                
                // 安装指定版本
                const response = await fetch('api/pim/install_plugin', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        plugin_id: pluginId,
                        version: version
                    })
                });
                
                const result = await response.json();
                
                if (result.success) {
                    this.installTaskId = result.task_id;
                    this.installPluginId = pluginId;
                    this.installStatus = 'running';
                    this.installProgress = 0;
                    this.installMessage = `正在安装 ${pluginId} v${version}...`;
                    this.installLogMessages = [];
                    this.showInstallModal = true;
                    
                    // 开始轮询安装进度
                    if (this.installProgressTimer) {
                        clearInterval(this.installProgressTimer);
                    }
                    this.installProgressTimer = setInterval(() => {
                        this.checkInstallProgress();
                    }, 2000);
                    
                    // 关闭版本选择模态框
                    this.closeVersionModal();
                    
                    // 刷新插件列表
                    await this.loadPlugins();
                } else {
                    throw new Error(result.error || '安装失败');
                }
            } catch (error) {
                console.error(`Error switching plugin ${pluginId} to version ${version}:`, error);
                this.showNotificationMsg(`切换版本失败: ${error.message}`, 'error');
                
                // 清理定时器
                if (this.installProgressTimer) {
                    clearInterval(this.installProgressTimer);
                    this.installProgressTimer = null;
                }
            } finally {
                // 取消标记处理中状态
                versionObj.processing = false;
            }
        },
        
        closeVersionModal() {
            this.showVersionModal = false;
            this.currentVersionPlugin = null;
            this.versions = [];
            this.versionError = false;
        },
        
        // 格式化日期显示
        formatDate(dateString) {
            if (!dateString) return '未知日期';
            
            try {
                const date = new Date(dateString);
                return date.toLocaleDateString('zh-CN', { 
                    year: 'numeric', 
                    month: 'short', 
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                });
            } catch (e) {
                return dateString;
            }
        },
        
        // 格式化数字，如：1000 -> 1k
        formatNumber(num) {
            if (num === undefined || num === null) return '0';
            
            if (num >= 1000000) {
                return (num / 1000000).toFixed(1) + 'M';
            } else if (num >= 1000) {
                return (num / 1000).toFixed(1) + 'k';
            } else {
                return num.toString();
            }
        },

        init() {
            this.checkLoginStatus();
            this.checkServerStatus();
            this.loadPlugins();
            
            // 初始化处理中插件状态
            this.processingPlugins = {};
            
            // 初始化版本切换相关变量
            this.showVersionModal = false;
            this.versionsLoading = false;
            this.versionError = false;
            this.versionErrorMessage = '';
            this.currentVersionPlugin = null;
            this.versions = [];
            this.installedVersion = null;
            
            // 每60秒自动刷新服务器状态
            setInterval(() => this.checkServerStatus(), 10001);
            
            // 保存主题设置到本地存储
            this.$watch('darkMode', value => {
                localStorage.setItem('darkMode', value);
            });
            
            // 设置当前年份
            const yearElement = document.getElementById('year');
            if (yearElement) {
                yearElement.textContent = new Date().getFullYear();
            }
        }
    }));
});