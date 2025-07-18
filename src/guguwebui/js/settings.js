function settingsApp() {
    return {
        // 状态
        showNotificationBar: false,
        notificationMessage: '',
        notificationType: 'success',
        notificationTimeout: null,
        
        // 表单数据
        serverStatus: 'loading',
        userName: '',
        webConfig: {
            host: '0.0.0.0',
            port: 8000,
            super_admin_account: '',
            disable_admin_login_web: false,
            enable_temp_login_password: false,
            ssl_enabled: false,
            ssl_certfile: '',
            ssl_keyfile: '',
            ssl_keyfile_password: ''
        },
        
        // AI配置
        aiApiKey: '',
        aiModel: 'deepseek-chat',
        aiApiUrl: 'https://api.deepseek.com/chat/completions',
        isKeyValid: false,
        keyValidated: false,
        
        repositories: [],
        officialRepoUrl: 'https://api.mcdreforged.com/catalogue/everything_slim.json.xz',
        newRepo: {
            name: '',
            url: ''
        },
        mcdrPluginsUrl: '',
        pimStatus: 'checking',
        
        // 初始化
        init() {
            this.checkLoginStatus();
            this.checkServerStatus();
            this.getConfig();
            this.checkPimStatus();
            
            // 每60秒自动刷新服务器状态
            setInterval(() => this.checkServerStatus(), 10001);
            
            // 设置当前年份
            document.getElementById('year').textContent = new Date().getFullYear();
        },
        
        // 检查登录状态
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
        
        // 检查服务器状态
        async checkServerStatus() {
            try {
                this.serverStatus = 'loading';
                const response = await fetch('api/get_server_status');
                const data = await response.json();
                this.serverStatus = data.status || 'offline';
            } catch (error) {
                console.error('Error checking server status:', error);
                this.serverStatus = 'error';
            }
        },
        
        // 获取配置
        async getConfig() {
            try {
                const response = await fetch('api/get_web_config');
                const config = await response.json();
                
                this.webConfig.host = config.host || '0.0.0.0';
                this.webConfig.port = config.port || 8000;
                this.webConfig.super_admin_account = config.super_admin_account || '';
                this.webConfig.disable_admin_login_web = config.disable_admin_login_web || false;
                this.webConfig.enable_temp_login_password = config.enable_temp_login_password || false;
                this.aiModel = config.ai_model || 'deepseek-chat';
                this.aiApiUrl = config.ai_api_url || 'https://api.deepseek.com/chat/completions';
                // 不加载已保存的API密钥，留空等待用户设置新的密钥
                this.aiApiKey = '';
                // 如果已配置过密钥，标记为已验证和有效
                if (config.ai_api_key_configured) {
                    this.isKeyValid = true;
                    this.keyValidated = true;
                }
                
                // HTTPS 配置
                this.webConfig.ssl_enabled = config.ssl_enabled || false;
                this.webConfig.ssl_certfile = config.ssl_certfile || '';
                this.webConfig.ssl_keyfile = config.ssl_keyfile || '';
                this.webConfig.ssl_keyfile_password = config.ssl_keyfile_password || '';
                
                // 检查插件目录URL
                if (config.mcdr_plugins_url) {
                    this.mcdrPluginsUrl = config.mcdr_plugins_url;
                }
                
                // 检查仓库列表
                if (config.repositories && Array.isArray(config.repositories)) {
                    this.repositories = config.repositories;
                }
                
                // 处理仓库配置
                // 兼容旧版单一URL的配置方式
                if (config.mcdr_plugins_url && !config.repositories) {
                    // 如果存在旧版的单一URL配置，但还没有repositories配置
                    // 并且URL不是官方仓库URL，则添加为自定义仓库
                    if (config.mcdr_plugins_url !== this.officialRepoUrl) {
                        this.repositories = [{
                            name: '自定义仓库',
                            url: config.mcdr_plugins_url
                        }];
                    } else {
                        this.repositories = []; // 如果只有官方仓库，则清空自定义仓库列表
                    }
                } else if (config.repositories && Array.isArray(config.repositories)) {
                    // 使用新的多仓库配置
                    this.repositories = config.repositories;
                } else {
                    this.repositories = []; // 初始化为空数组
                }
                
                this.pimStatus = config.pim_status || 'checking';
                
                // 更新后台切换开关状态
                this.$nextTick(() => {
                    const toggleSwitches = document.querySelectorAll('.toggle-switch');
                    toggleSwitches.forEach((switchEl) => {
                        switchEl.checked = this[switchEl.id];
                    });
                });
            } catch (error) {
                console.error('Error fetching config:', error);
                this.showNotification('获取配置失败', 'error');
            }
        },
        
        // 保存网络配置
        async saveNetworkConfig() {
            try {
                // 验证输入
                if (!this.webConfig.host) {
                    this.showNotification('主机地址不能为空', 'error');
                    return;
                }
                
                if (!this.webConfig.port || this.webConfig.port < 1 || this.webConfig.port > 65535) {
                    this.showNotification('端口必须是1-65535之间的有效数字', 'error');
                    return;
                }
                
                // 准备请求数据
                const requestData = {
                    action: 'config',
                    host: this.webConfig.host.toString().trim(),
                    port: parseInt(this.webConfig.port, 10)
                };
                
                const response = await fetch('api/save_web_config', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(requestData)
                });
                
                const result = await response.json();
                if (result.status === 'success') {
                    this.showNotification('网络设置保存成功', 'success');
                } else {
                    this.showNotification('保存失败: ' + result.message, 'error');
                }
            } catch (error) {
                console.error('Error saving network config:', error);
                this.showNotification('保存出错: ' + error.message, 'error');
            }
        },
        
        // 保存账户配置
        async saveAccountConfig() {
            try {
                // 验证输入
                if (!this.webConfig.super_admin_account) {
                    this.showNotification('超级管理员账号不能为空', 'error');
                    return;
                }
                
                // 准备请求数据
                const requestData = {
                    action: 'config',
                    superaccount: this.webConfig.super_admin_account.toString().trim()
                };

                const response = await fetch('api/save_web_config', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(requestData)
                });
                
                const result = await response.json();
                if (result.status === 'success') {
                    this.showNotification('账户设置保存成功', 'success');
                } else {
                    this.showNotification('保存失败: ' + result.message, 'error');
                }
            } catch (error) {
                console.error('Error saving account config:', error);
                this.showNotification('保存出错: ' + error.message, 'error');
            }
        },
        
        // 切换布尔设置
        async toggleSetting(setting) {
            try {
                const apiSetting = setting === 'disable_admin_login_web' ? 'disable_admin_login_web' : 'enable_temp_login_password';
                
                const response = await fetch('api/save_web_config', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        action: apiSetting
                    })
                });
                
                const result = await response.json();
                if (result.status === 'success') {
                    // 切换本地状态
                    this.webConfig[setting] = result.message;
                    this.showNotification(`设置已${this.webConfig[setting] ? '启用' : '禁用'}`, 'success');
                } else {
                    this.showNotification('设置切换失败: ' + result.message, 'error');
                }
            } catch (error) {
                console.error('Error toggling setting:', error);
                this.showNotification('设置出错: ' + error.message, 'error');
            }
        },
        
        // 显示通知
        showNotification(message, type = 'info') {
            // 获取或创建通知容器
            let notificationContainer = document.getElementById('notification-container');
            if (!notificationContainer) {
                notificationContainer = document.createElement('div');
                notificationContainer.id = 'notification-container';
                notificationContainer.className = 'fixed top-16 right-4 z-50 flex flex-col gap-2';
                document.body.appendChild(notificationContainer);
            }
            
            // 创建通知元素
            const notification = document.createElement('div');
            notification.className = `p-3 rounded-lg shadow-lg transition-all duration-300 transform translate-x-full opacity-0`;
            
            // 根据类型设置样式
            switch (type) {
                case 'success':
                    notification.className += ' bg-green-500 text-white';
                    notification.innerHTML = `<i class="fas fa-check-circle mr-2"></i>${message}`;
                    break;
                case 'error':
                    notification.className += ' bg-red-500 text-white';
                    notification.innerHTML = `<i class="fas fa-times-circle mr-2"></i>${message}`;
                    break;
                default:
                    notification.className += ' bg-blue-500 text-white';
                    notification.innerHTML = `<i class="fas fa-info-circle mr-2"></i>${message}`;
            }
            
            // 添加到容器
            notificationContainer.appendChild(notification);
            
            // 触发动画
            setTimeout(() => {
                notification.classList.remove('translate-x-full', 'opacity-0');
                notification.classList.add('translate-x-0', 'opacity-100');
            }, 10);
            
            // 自动移除
            setTimeout(() => {
                notification.classList.remove('translate-x-0', 'opacity-100');
                notification.classList.add('translate-x-full', 'opacity-0');
                setTimeout(() => {
                    notificationContainer.removeChild(notification);
                }, 300);
            }, 3000);
        },
        
        // 保存AI配置
        async saveAiConfig() {
            try {
                // 准备请求数据，只包含非空值
                const requestData = {
                    action: 'config'
                };
                
                // 只有当aiApiKey有值且不为空白字符串时才添加到请求
                if (this.aiApiKey && this.aiApiKey.trim() !== '') {
                    requestData.ai_api_key = this.aiApiKey.trim();
                }
                
                // 只有当aiModel有值且不为空白字符串时才添加到请求
                if (this.aiModel && this.aiModel.trim() !== '') {
                    requestData.ai_model = this.aiModel.trim();
                }
                
                // 只有当aiApiUrl有值且不为空白字符串时才添加到请求
                if (this.aiApiUrl && this.aiApiUrl.trim() !== '') {
                    requestData.ai_api_url = this.aiApiUrl.trim();
                }
                
                const response = await fetch('api/save_web_config', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(requestData)
                });
                
                const result = await response.json();
                if (result.status === 'success') {
                    this.showNotification('AI配置保存成功', 'success');
                    // 保存成功后重置状态
                    if (this.aiApiKey) {
                        this.aiApiKey = '';
                    }
                } else {
                    this.showNotification('保存失败: ' + result.message, 'error');
                }
            } catch (error) {
                console.error('Error saving AI config:', error);
                this.showNotification('保存出错: ' + error.message, 'error');
            }
        },
        
        // 切换密码可见性
        togglePasswordVisibility(id) {
            const input = document.getElementById(id);
            const toggle = document.getElementById(`${id}_toggle`);
            
            if (input.type === 'password') {
                input.type = 'text';
                toggle.classList.remove('fa-eye');
                toggle.classList.add('fa-eye-slash');
            } else {
                input.type = 'password';
                toggle.classList.remove('fa-eye-slash');
                toggle.classList.add('fa-eye');
            }
        },
        
        // 添加API密钥验证方法
        async validateApiKey() {
            if (!this.aiApiKey) {
                this.showNotification('请输入API密钥', 'error');
                return;
            }
            
            try {
                this.showNotification('正在验证API密钥...', 'info');
                
                // 直接使用输入框中的API密钥发送测试请求
                const response = await fetch('api/deepseek', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        query: '测试密钥是否有效，请回复"有效"',
                        system_prompt: '你是一个简单的验证程序，只需回复"有效"',
                        model: this.aiModel,
                        api_url: this.aiApiUrl,
                        // 将输入框中的密钥传递到API，而不是使用后端已保存的密钥
                        api_key: this.aiApiKey
                    })
                });
                
                const result = await response.json();
                
                if (result.status === 'success') {
                    this.isKeyValid = true;
                    this.keyValidated = true;
                    this.showNotification('API密钥验证成功', 'success');
                } else {
                    this.isKeyValid = false;
                    this.keyValidated = true;
                    this.showNotification(`API密钥验证失败: ${result.message}`, 'error');
                }
            } catch (error) {
                console.error('API密钥验证错误:', error);
                this.isKeyValid = false;
                this.keyValidated = true;
                this.showNotification(`验证出错: ${error.message}`, 'error');
            }
        },
        
        // 添加新仓库
        addRepository() {
            if (!this.newRepo.name || !this.newRepo.url) {
                this.showNotification('仓库名称和URL不能为空', 'error');
                return;
            }
            
            // 检查URL格式
            try {
                new URL(this.newRepo.url);
            } catch (e) {
                this.showNotification('请输入有效的URL', 'error');
                return;
            }
            
            // 检查是否与官方仓库URL重复
            if (this.newRepo.url === this.officialRepoUrl) {
                this.showNotification('不能添加与官方仓库相同的URL', 'error');
                return;
            }
            
            // 检查是否与现有仓库重复
            const isDuplicate = this.repositories.some(repo => 
                repo.url === this.newRepo.url || repo.name === this.newRepo.name
            );
            
            if (isDuplicate) {
                this.showNotification('仓库名称或URL已存在', 'error');
                return;
            }
            
            // 添加到仓库列表
            this.repositories.push({
                name: this.newRepo.name,
                url: this.newRepo.url
            });
            
            // 清空输入框
            this.newRepo.name = '';
            this.newRepo.url = '';
            
            this.showNotification('仓库已添加，请点击保存按钮保存配置', 'success');
        },
        
        // 删除仓库
        deleteRepository(index) {
            if (index >= 0 && index < this.repositories.length) {
                this.repositories.splice(index, 1);
                this.showNotification('仓库已删除，请点击保存按钮保存配置', 'success');
            }
        },
        
        // 保存仓库配置
        async saveRepositories() {
            try {
                // 准备请求数据，只包含非空值
                const requestData = {
                    action: 'config'
                };
                
                // 只有当mcdrPluginsUrl有值且不为空白字符串时才添加到请求
                if (this.mcdrPluginsUrl && this.mcdrPluginsUrl.trim() !== '') {
                    requestData.mcdr_plugins_url = this.mcdrPluginsUrl.trim();
                }
                
                // 添加仓库列表，确保它是数组
                if (Array.isArray(this.repositories)) {
                    requestData.repositories = this.repositories;
                }
                
                const response = await fetch('api/save_web_config', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(requestData)
                });
                
                const result = await response.json();
                if (result.status === 'success') {
                    this.showNotification('仓库配置保存成功', 'success');
                } else {
                    this.showNotification('保存失败: ' + result.message, 'error');
                }
            } catch (error) {
                console.error('Error saving repositories:', error);
                this.showNotification('保存出错: ' + error.message, 'error');
            }
        },
        
        // 保存MCDR插件目录配置 - 保留此方法兼容旧版
        async saveMcdrPluginsUrl() {
            try {
                // 准备请求数据，只包含非空值
                const requestData = {
                    action: 'config'
                };
                
                // 优先使用用户输入的URL，如果为空则使用官方仓库URL
                const url = (this.mcdrPluginsUrl && this.mcdrPluginsUrl.trim() !== '') 
                    ? this.mcdrPluginsUrl.trim() 
                    : this.officialRepoUrl;
                    
                requestData.mcdr_plugins_url = url;
                
                const response = await fetch('api/save_web_config', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(requestData)
                });
                
                const result = await response.json();
                if (result.status === 'success') {
                    this.showNotification('MCDR插件目录URL保存成功', 'success');
                } else {
                    this.showNotification('保存失败: ' + result.message, 'error');
                }
            } catch (error) {
                console.error('Error saving MCDR plugins URL:', error);
                this.showNotification('保存出错: ' + error.message, 'error');
            }
        },
        
        // 检查PIM插件状态
        async checkPimStatus() {
            try {
                const response = await fetch('api/check_pim_status');
                const result = await response.json();
                
                if (result.status === 'success') {
                    this.pimStatus = result.pim_status;
                } else {
                    this.pimStatus = 'not_installed';
                    console.error('Error checking PIM status:', result.message);
                }
            } catch (error) {
                this.pimStatus = 'not_installed';
                console.error('Error checking PIM status:', error);
            }
        },
        
        // 安装PIM插件
        async installPimPlugin() {
            try {
                this.pimStatus = 'installing';
                const response = await fetch('api/install_pim_plugin');
                const result = await response.json();
                
                if (result.status === 'success') {
                    this.showNotification('PIM插件安装成功', 'success');
                    this.pimStatus = 'installed';
                } else {
                    this.showNotification('安装失败: ' + result.message, 'error');
                    await this.checkPimStatus(); // 重新检查状态
                }
            } catch (error) {
                console.error('Error installing PIM plugin:', error);
                this.showNotification('安装出错: ' + error.message, 'error');
                await this.checkPimStatus(); // 重新检查状态
            }
        },
        
        // 保存插件仓库配置
        async savePluginRepoConfig() {
            try {
                // 准备请求数据，只包含非空值
                const requestData = {
                    action: 'config'
                };
                
                // 只有当mcdrPluginsUrl有值且不为空白字符串时才添加到请求
                if (this.mcdrPluginsUrl && this.mcdrPluginsUrl.trim() !== '') {
                    requestData.mcdr_plugins_url = this.mcdrPluginsUrl.trim();
                }
                
                // 添加仓库列表，确保它是数组
                if (Array.isArray(this.repositories)) {
                    requestData.repositories = this.repositories;
                }
                
                const response = await fetch('api/save_web_config', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(requestData)
                });
                
                const result = await response.json();
                
                if (result.status === 'success') {
                    this.showNotification('插件目录配置保存成功', 'success');
                } else {
                    this.showNotification('保存失败: ' + result.message, 'error');
                }
            } catch (error) {
                console.error('Error saving plugin repository config:', error);
                this.showNotification('保存出错: ' + error.message, 'error');
            }
        },
        
        // 保存HTTPS配置
        async saveHttpsConfig() {
            try {
                // 如果启用了HTTPS但未提供证书或密钥文件
                if (this.webConfig.ssl_enabled && (!this.webConfig.ssl_certfile || !this.webConfig.ssl_keyfile)) {
                    this.showNotification('启用HTTPS需要同时提供证书文件和密钥文件路径', 'error');
                    return;
                }
                
                // 检查文件路径格式
                if (this.webConfig.ssl_enabled) {
                    // 提示用户确认文件存在
                    if (!confirm('请确认您已经准备好了SSL证书和密钥文件，并且指定的路径是正确的。\n\n如果文件不存在，WebUI将回退到HTTP模式。\n\n是否继续?')) {
                        return;
                    }
                }
                
                // 准备请求数据
                const requestData = {
                    action: 'config',
                    ssl_enabled: this.webConfig.ssl_enabled,
                    ssl_certfile: this.webConfig.ssl_certfile,
                    ssl_keyfile: this.webConfig.ssl_keyfile,
                    ssl_keyfile_password: this.webConfig.ssl_keyfile_password
                };
                
                const response = await fetch('api/save_web_config', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(requestData)
                });
                
                const result = await response.json();
                if (result.status === 'success') {
                    this.showNotification('HTTPS设置保存成功，重启插件后生效。如果SSL文件不存在，系统将自动回退到HTTP模式。', 'success');
                } else {
                    this.showNotification('保存失败: ' + result.message, 'error');
                }
            } catch (error) {
                console.error('Error saving HTTPS config:', error);
                this.showNotification('保存出错: ' + error.message, 'error');
            }
        }
    };
}