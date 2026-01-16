/**
 * MCDR WebUI 主脚本
 * 实现前端交互和页面动态效果
 */

// 防止重复加载
if (window.__MCDR_WEBUI_MAIN_LOADED__) {
    console.warn('[main.js] 脚本已加载，跳过重复加载');
} else {
    window.__MCDR_WEBUI_MAIN_LOADED__ = true;

// i18n 支持
let mainLang = 'zh-CN';
let mainDict = {};

// 翻译函数
function t(key, fallback = '') {
    // 在已加载的语言包中查找 key（支持 a.b.c 链式）
    const val = key.split('.').reduce((o, k) => (o && o[k] != null ? o[k] : undefined), mainDict);
    if (val != null) return String(val);
    // 回退到全局 I18n.t（若可用）
    if (window.I18n && typeof window.I18n.t === 'function') {
        const v = window.I18n.t(key);
        if (v && v !== key) return v;
    }
    return fallback || key;
}

// 加载语言字典
async function loadMainLangDict() {
    // 读取本地存储语言（由 i18n.js 维护）
    const stored = localStorage.getItem('lang') || (navigator.language || 'zh-CN');
    mainLang = stored.toLowerCase().startsWith('zh') ? 'zh-CN' : 'en-US';
    try {
        if (window.I18n && typeof window.I18n.fetchLangDict === 'function') {
            mainDict = await window.I18n.fetchLangDict(mainLang);
        } else {
            const resp = await fetch(`lang/${mainLang}.json`, { cache: 'no-cache' });
            if (resp.ok) {
                mainDict = await resp.json();
            }
        }
    } catch (e) {
        // 忽略，保持空字典，使用 fallback
        console.warn('loadMainLangDict failed:', e);
    }
}

// 初始化主题
function initTheme() {
    // 检查localStorage中是否有主题设置
    const savedTheme = localStorage.getItem('darkMode');
    
    // 如果有设置，使用保存的设置
    if (savedTheme !== null) {
        const isDark = savedTheme === 'true';
        if (isDark) {
            document.documentElement.classList.add('dark');
        } else {
            document.documentElement.classList.remove('dark');
        }
    } else {
        // 如果没有设置，根据系统主题设置
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        if (prefersDark) {
            document.documentElement.classList.add('dark');
        } else {
            document.documentElement.classList.remove('dark');
        }
        // 保存初始主题设置
        localStorage.setItem('darkMode', prefersDark);
    }
    
    // 添加系统主题变化监听
    const darkModeMediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    darkModeMediaQuery.addEventListener('change', (e) => {
        // 如果用户没有明确设置主题偏好，则跟随系统
        if (localStorage.getItem('darkMode') === null) {
            const darkMode = e.matches;
            document.documentElement.classList.toggle('dark', darkMode);
            localStorage.setItem('darkMode', darkMode);
        }
    });
}

// 切换主题
function toggleTheme() {
    const isDark = document.documentElement.classList.contains('dark');
    const newMode = !isDark;
    
    if (newMode) {
        document.documentElement.classList.add('dark');
    } else {
        document.documentElement.classList.remove('dark');
    }
    
    // 保存到localStorage，确保使用字符串值
    localStorage.setItem('darkMode', String(newMode));
    
    // 如果页面使用Alpine.js管理深色模式，需要同步Alpine状态
    const alpineRoot = document.querySelector('[x-data]');
    if (alpineRoot && alpineRoot.__x) {
        alpineRoot.__x.$data.darkMode = newMode;
    }
}

// 检查外部资源（CSS和JS）加载状态
function checkExternalResources() {
    // 获取所有外部CSS和JS资源
    const cssLinks = Array.from(document.querySelectorAll('link[rel="stylesheet"]'));
    const scriptTags = Array.from(document.querySelectorAll('script[src]'));
    
    const failedResources = [];
    let checksRemaining = cssLinks.length + scriptTags.length;
    
    // 如果没有外部资源需要检查
    if (checksRemaining === 0) {
        return;
    }
    
    // 检查是否所有检查都已完成
    function checkComplete() {
        checksRemaining--;
        if (checksRemaining === 0 && failedResources.length > 0) {
            showResourceErrorModal(failedResources);
        }
    }
    
    // 检查CSS文件
    cssLinks.forEach(link => {
        // 创建一个新的link元素进行测试
        const testLink = document.createElement('link');
        testLink.href = link.href;
        testLink.rel = 'stylesheet';
        testLink.onload = () => {
            testLink.remove();
            checkComplete();
        };
        testLink.onerror = () => {
            testLink.remove();
            failedResources.push(link.href);
            checkComplete();
        };
        document.head.appendChild(testLink);
    });
    
    // 检查JS文件
    scriptTags.forEach(script => {
        // 跳过内联脚本或已经失败的脚本
        if (!script.src) {
            checkComplete();
            return;
        }
        
        // 创建一个新的script元素进行测试
        const testScript = document.createElement('script');
        testScript.src = script.src;
        testScript.async = true;
        testScript.onload = () => {
            testScript.remove();
            checkComplete();
        };
        testScript.onerror = () => {
            testScript.remove();
            failedResources.push(script.src);
            checkComplete();
        };
        document.head.appendChild(testScript);
    });
}

// 显示资源加载错误的模态窗口
function showResourceErrorModal(failedResources) {
    // 创建模态窗口容器
    const modal = document.createElement('div');
    modal.classList.add('resource-error-modal');
    modal.style.position = 'fixed';
    modal.style.top = '0';
    modal.style.left = '0';
    modal.style.width = '100%';
    modal.style.height = '100%';
    modal.style.backgroundColor = 'rgba(0, 0, 0, 0.5)';
    modal.style.display = 'flex';
    modal.style.justifyContent = 'center';
    modal.style.alignItems = 'center';
    modal.style.zIndex = '9999';
    
    // 创建模态窗口内容
    const modalContent = document.createElement('div');
    modalContent.style.backgroundColor = document.documentElement.classList.contains('dark') ? '#374151' : '#ffffff';
    modalContent.style.color = document.documentElement.classList.contains('dark') ? '#e5e7eb' : '#1f2937';
    modalContent.style.padding = '20px';
    modalContent.style.borderRadius = '8px';
    modalContent.style.boxShadow = '0 4px 6px rgba(0, 0, 0, 0.1)';
    modalContent.style.maxWidth = '500px';
    modalContent.style.width = '90%';
    
    // 添加标题
    const title = document.createElement('h3');
    title.textContent = t('main.resource_error.title', '资源加载错误');
    title.style.fontSize = '1.25rem';
    title.style.fontWeight = 'bold';
    title.style.marginBottom = '10px';
    
    // 添加描述
    const description = document.createElement('p');
    description.textContent = t('main.resource_error.description', '以下资源加载失败，这可能会导致页面功能异常。请检查您的网络连接或联系管理员。');
    description.style.marginBottom = '15px';
    
    // 添加资源列表
    const resourceList = document.createElement('ul');
    resourceList.style.marginBottom = '20px';
    resourceList.style.backgroundColor = document.documentElement.classList.contains('dark') ? '#4b5563' : '#f3f4f6';
    resourceList.style.padding = '10px';
    resourceList.style.borderRadius = '4px';
    resourceList.style.maxHeight = '150px';
    resourceList.style.overflowY = 'auto';
    
    failedResources.forEach(resource => {
        const item = document.createElement('li');
        item.textContent = resource;
        item.style.marginBottom = '5px';
        item.style.wordBreak = 'break-all';
        resourceList.appendChild(item);
    });
    
    // 添加关闭按钮
    const closeButton = document.createElement('button');
    closeButton.textContent = t('main.resource_error.close', '关闭');
    closeButton.style.backgroundColor = '#3b82f6';
    closeButton.style.color = 'white';
    closeButton.style.border = 'none';
    closeButton.style.borderRadius = '4px';
    closeButton.style.padding = '8px 16px';
    closeButton.style.cursor = 'pointer';
    closeButton.style.float = 'right';
    
    // 关闭按钮点击事件
    closeButton.addEventListener('click', () => {
        document.body.removeChild(modal);
    });
    
    // 组装模态窗口
    modalContent.appendChild(title);
    modalContent.appendChild(description);
    modalContent.appendChild(resourceList);
    modalContent.appendChild(closeButton);
    modal.appendChild(modalContent);
    
    // 添加到页面
    document.body.appendChild(modal);
}

// 检查登录状态
async function checkLoginStatus() {
    try {
        const response = await fetch('api/checkLogin');
        const data = await response.json();
        
        if (data.status !== 'success') {
            // 用户未登录，重定向到登录页面
            window.location.href = '/login';
            return false;
        }
        
        // 更新UI显示用户名
        if (data.username) {
            const userNameElements = document.querySelectorAll('.js-username');
            userNameElements.forEach(el => {
                el.textContent = data.username;
            });
            
            // 检查是否是QQ号，如果是则获取QQ信息
            if (/^\d{5,11}$/.test(data.username)) {
                fetchQQInfo(data.username);
            } else {
                // 不是QQ号，直接使用用户名更新UI
                updateUIWithQQInfo(data.username, data.username);
            }
        }
        
        return true;
    } catch (error) {
        console.error('Error checking login status:', error);
        return false;
    }
}

// 获取QQ昵称和头像
async function fetchQQInfo(qqNumber) {
    try {
        // 检查缓存
        const cachedInfo = getQQInfoFromCache(qqNumber);
        if (cachedInfo) {
            console.log('Using cached QQ info for', qqNumber);
            updateUIWithQQInfo(qqNumber, cachedInfo);
            return;
        }

        // 先用QQ号更新UI，确保头像显示
        console.log('Updating UI initially with QQ number for', qqNumber);
        updateUIWithQQInfo(qqNumber, qqNumber);

        const apiEndpoints = [
            `https://api.leafone.cn/api/qqnick?qq=${qqNumber}`,
            `https://api.mmp.cc/api/qqname?qq=${qqNumber}`
        ];

        let nickname = null;
        let success = false;

        for (const endpoint of apiEndpoints) {
            try {
                console.log(`Attempting to fetch QQ info from: ${endpoint}`);
                const response = await fetch(endpoint);
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                const data = await response.json();

                // 根据不同API的响应结构提取昵称
                if (endpoint.includes('leafone.cn')) {
                    if (data.code === 200 && data.data && data.data.nickname) {
                        nickname = data.data.nickname;
                        success = true;
                    } else {
                        console.warn(`Failed to get nickname from leafone.cn:`, data);
                    }
                } else if (endpoint.includes('mmp.cc')) {
                    if (data.code === 200 && data.data && data.data.name) {
                        nickname = data.data.name;
                        success = true;
                    } else {
                        console.warn(`Failed to get nickname from mmp.cc:`, data);
                    }
                }

                if (success) {
                    console.log(`Successfully fetched nickname from ${endpoint}`);
                    break; // 成功获取到昵称，跳出循环
                }

            } catch (error) {
                console.error(`Error fetching from ${endpoint}:`, error);
                // 继续尝试下一个API
            }
        }

        // 如果成功获取到昵称，则更新UI
        if (success && nickname) {
            console.log('Updating UI with fetched nickname for', qqNumber);
            // 缓存昵称信息
            saveQQInfoToCache(qqNumber, nickname);
            // 更新UI
            updateUIWithQQInfo(qqNumber, nickname);
        } else {
             console.error('Failed to fetch QQ info from all available APIs for QQ:', qqNumber);
             // 不需要再次调用 updateUIWithQQInfo，因为初始调用已经显示了QQ号
        }

    } catch (error) {
        console.error('Error in fetchQQInfo function:', error);
        // 确保即使发生意外错误，头像和QQ号也已初步显示
        // 如果错误发生在初始 updateUIWithQQInfo 之前，这里可以加一个后备调用
        // 但通常，初始调用应该已经执行
    }
}

// 从缓存获取QQ信息
function getQQInfoFromCache(qqNumber) {
    const cacheKey = 'qqInfo';
    const cacheExpiryTime = 2 * 60 * 60 * 1000; // 2小时（毫秒）
    
    try {
        const cachedData = localStorage.getItem(cacheKey);
        if (!cachedData) return null;
        
        const qqInfoCache = JSON.parse(cachedData);
        const qqData = qqInfoCache[qqNumber];
        
        // 如果缓存存在且未过期
        if (qqData && (Date.now() - qqData.timestamp < cacheExpiryTime)) {
            return qqData.nickname;
        }
        
        return null;
    } catch (error) {
        console.error('Error reading QQ info from cache:', error);
        return null;
    }
}

// 保存QQ信息到缓存
function saveQQInfoToCache(qqNumber, nickname) {
    const cacheKey = 'qqInfo';
    
    try {
        // 获取现有缓存或创建新的缓存对象
        let qqInfoCache = {};
        const cachedData = localStorage.getItem(cacheKey);
        
        if (cachedData) {
            qqInfoCache = JSON.parse(cachedData);
        }
        
        // 更新缓存
        qqInfoCache[qqNumber] = {
            nickname: nickname,
            timestamp: Date.now()
        };
        
        // 保存回缓存
        localStorage.setItem(cacheKey, JSON.stringify(qqInfoCache));
        console.log('QQ info cached for', qqNumber);
    } catch (error) {
        console.error('Error saving QQ info to cache:', error);
    }
}

// 使用QQ信息更新UI
function updateUIWithQQInfo(qqNumber, nickname) {
    // 更新昵称
    const userNameElements = document.querySelectorAll('.js-username');
    userNameElements.forEach(el => {
        el.textContent = nickname || qqNumber;
    });
    
    // 更新头像
    const avatarElements = document.querySelectorAll('.user-avatar');
    // 判断是否为QQ号
    const isQQNumber = /^\d{5,11}$/.test(qqNumber);
    // 设置头像URL - 如果是QQ号使用QQ头像，否则使用随机模糊图片
    const avatarUrl = isQQNumber 
        ? `https://q1.qlogo.cn/g?b=qq&nk=${qqNumber}&s=640`
        : 'https://picsum.photos/100/?blur=5';
    
    avatarElements.forEach(el => {
        // 如果是img标签
        if (el.tagName === 'IMG') {
            el.src = avatarUrl;
            el.alt = nickname || qqNumber;
        } 
        // 如果是div等容器，设置背景图
        else {
            el.style.backgroundImage = `url('${avatarUrl}')`;
            el.style.backgroundSize = 'cover';
            el.style.backgroundPosition = 'center';
            
            // 移除内部图标
            const iconElement = el.querySelector('i.fa-user');
            if (iconElement) {
                iconElement.remove();
            }
        }
        
        // 添加头像加载失败回退处理
        if (el.tagName === 'IMG') {
            el.onerror = function() {
                this.onerror = null;
                // 使用随机模糊图片作为备用
                this.src = 'https://picsum.photos/100/?blur=5';
                
                // 如果第二次加载也失败，则使用图标
                this.addEventListener('error', function() {
                    this.style.display = 'none';
                    // 创建并添加图标作为后备
                    const iconElement = document.createElement('i');
                    iconElement.className = 'fas fa-user';
                    this.parentNode.appendChild(iconElement);
                }, { once: true });
            };
        }
    });
}

// 检查服务器状态
async function checkServerStatus() {
    try {
        const statusIndicator = document.getElementById('server-status-indicator');
        const statusText = document.getElementById('server-status-text');
        const versionText = document.getElementById('server-version');
        const playersText = document.getElementById('server-players');
        
        if (!statusIndicator || !statusText) return;
        
        // 设置加载状态
        statusIndicator.className = 'animate-pulse text-gray-500';
        statusIndicator.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i>';
        statusText.textContent = t('main.server_status.checking', '正在检查...');
        
        const response = await fetch('api/get_server_status');
        const data = await response.json();
        
        // 更新状态显示
        if (data.status === 'online') {
            statusIndicator.className = 'text-green-500';
            statusIndicator.innerHTML = '<i class="fas fa-circle"></i>';
            statusText.textContent = t('main.server_status.online', '在线');
        } else if (data.status === 'offline') {
            statusIndicator.className = 'text-red-500';
            statusIndicator.innerHTML = '<i class="fas fa-circle"></i>';
            statusText.textContent = t('main.server_status.offline', '离线');
        } else {
            statusIndicator.className = 'text-yellow-500';
            statusIndicator.innerHTML = '<i class="fas fa-exclamation-triangle"></i>';
            statusText.textContent = t('main.server_status.unknown', '未知');
        }
        
        // 更新版本和玩家信息
        if (versionText) versionText.textContent = data.version || t('main.server_status.unknown_version', '未知版本');
        if (playersText) playersText.textContent = data.players || '0/0';
        
    } catch (error) {
        console.error('Error checking server status:', error);
        
        // 错误状态
        if (statusIndicator && statusText) {
            statusIndicator.className = 'text-yellow-500';
            statusIndicator.innerHTML = '<i class="fas fa-exclamation-triangle"></i>';
            statusText.textContent = t('main.server_status.connection_error', '连接错误');
        }
    }
}

// 初始化侧边栏状态
function initSidebar() {
    // 检查localStorage中是否有侧边栏状态
    const sidebarState = localStorage.getItem('sidebarOpen');
    
    // 根据屏幕宽度默认值
    const defaultState = window.innerWidth >= 1024;
    
    // 如果有设置，使用保存的设置
    if (sidebarState !== null) {
        const isOpen = sidebarState === 'true';
        toggleSidebar(isOpen);
    } else {
        // 如果没有设置，使用默认值
        toggleSidebar(defaultState);
    }
}

// 切换侧边栏状态
function toggleSidebar(forceState) {
    const sidebar = document.getElementById('sidebar');
    const mainContent = document.getElementById('main-content');
    const header = document.getElementById('header');
    
    if (!sidebar || !mainContent || !header) return;
    
    const isOpen = forceState !== undefined ? forceState : !sidebar.classList.contains('translate-x-0');
    
    if (isOpen) {
        sidebar.classList.remove('-translate-x-full');
        sidebar.classList.add('translate-x-0');
        mainContent.classList.add('sidebar-open');
        header.classList.add('left-[260px]');
        header.classList.remove('left-0');
    } else {
        sidebar.classList.remove('translate-x-0');
        sidebar.classList.add('-translate-x-full');
        mainContent.classList.remove('sidebar-open');
        header.classList.remove('left-[260px]');
        header.classList.add('left-0');
    }
    
    // 保存状态到localStorage
    localStorage.setItem('sidebarOpen', isOpen);
}

// 登录表单验证
function validateLoginForm() {
    const loginForm = document.getElementById('login-form');
    const tempForm = document.getElementById('temp-form');
    
    if (loginForm) {
        loginForm.addEventListener('submit', function(e) {
            const account = document.getElementById('account');
            const password = document.getElementById('password');
            const errorText = document.getElementById('error-text');
            
            if (!account.value || !password.value) {
                e.preventDefault();
                errorText.textContent = t('main.login.form_incomplete', '请填写完整的登录信息');
                errorText.classList.remove('hidden');
                return false;
            }
            
            return true;
        });
    }
    
    if (tempForm) {
        tempForm.addEventListener('submit', function(e) {
            const tempCode = document.getElementById('temp_code');
            const errorText = document.getElementById('error-text');
            
            if (!tempCode.value) {
                e.preventDefault();
                errorText.textContent = t('main.login.temp_code_required', '请输入临时登录码');
                errorText.classList.remove('hidden');
                return false;
            }
            
            return true;
        });
    }
}

// 更新时间显示
function updateTime() {
    const timeElement = document.getElementById('current-time');
    
    if (timeElement) {
        const now = new Date();
        timeElement.textContent = now.toLocaleString('zh-CN');
    }
}

// 页面加载完成后执行
document.addEventListener('DOMContentLoaded', function() {
    // 初始化语言
    loadMainLangDict();
    
    // 初始化主题
    initTheme();
    
    // 检查外部资源加载状态
    checkExternalResources();
    
    // 初始化登录表单验证
    validateLoginForm();
    
    // 在需要验证登录的页面检查登录状态
    const needsAuth = !window.location.pathname.includes('/login');
    if (needsAuth) {
        checkLoginStatus();
        initSidebar();
        checkServerStatus();
        
        // 定时刷新服务器状态 (每60秒)
        setInterval(checkServerStatus, 10001);
        
        // 定时更新时间显示 (每秒)
        updateTime();
        setInterval(updateTime, 1000);
    }
    
    // 为主题切换按钮添加事件监听
    const themeToggleButtons = document.querySelectorAll('.theme-toggle');
    themeToggleButtons.forEach(btn => {
        btn.addEventListener('click', toggleTheme);
    });
    
    // 为侧边栏切换按钮添加事件监听
    const sidebarToggleButtons = document.querySelectorAll('.sidebar-toggle');
    sidebarToggleButtons.forEach(btn => {
        btn.addEventListener('click', () => toggleSidebar());
    });
    
    // 监听语言切换
    document.addEventListener('i18n:changed', (e) => {
        const nextLang = (e && e.detail && e.detail.lang) ? e.detail.lang : mainLang;
        mainLang = nextLang.toLowerCase().startsWith('zh') ? 'zh-CN' : 'en-US';
        loadMainLangDict();
    });
});

// 页面可见性变化时刷新服务器状态
document.addEventListener('visibilitychange', function() {
    if (document.visibilityState === 'visible') {
        const needsAuth = !window.location.pathname.includes('/login');
        if (needsAuth) {
            checkServerStatus();
        }
    }
});

} // 结束防止重复加载的 if 块 