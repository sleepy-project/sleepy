// screen_usage_time.js - 处理设备使用时间统计数据

class ScreenUsageTime {
    constructor() {
        this.container = null;
        this.data = null;
        this.init();
    }

    init() {
        // 等待DOM加载完成
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', this.setup.bind(this));
        } else {
            this.setup();
        }
    }

    setup() {
        // 创建容器
        this.container = document.createElement('div');
        this.container.className = 'screen-usage-time';
        
        // 添加到页面中
        const container = document.querySelector('.container') || document.body;
        container.appendChild(this.container);
        
        // 初始化SSE连接
        this.setupSSE();
        
        // 初始获取数据
        this.fetchData();
    }

    setupSSE() {
        // 连接SSE事件流
        const eventSource = new EventSource('/api/status/events');
        
        // 处理 update 事件
        eventSource.addEventListener('update', (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.screen_usage_time) {
                    this.data = data.screen_usage_time;
                    this.render();
                }
            } catch (error) {
                console.error('Error parsing SSE data:', error);
            }
        });
        
        // 处理 message 事件（兼容旧版）
        eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.screen_usage_time) {
                    this.data = data.screen_usage_time;
                    this.render();
                }
            } catch (error) {
                // 忽略错误，因为这可能是心跳事件
            }
        };
        
        eventSource.onerror = (error) => {
            console.error('SSE error:', error);
            // 尝试重新连接
            setTimeout(() => {
                eventSource.close();
                this.setupSSE();
            }, 5000);
        };
    }

    async fetchData() {
        try {
            const response = await fetch('/api/status/query');
            if (response.ok) {
                const data = await response.json();
                if (data.screen_usage_time) {
                    this.data = data.screen_usage_time;
                    this.render();
                }
            }
        } catch (error) {
            console.error('Error fetching data:', error);
        }
    }

    render() {
        if (!this.data) return;
        
        const { app_usage, website_usage, last_updated } = this.data;
        
        // 格式化最后更新时间
        let formattedLastUpdated = '';
        if (last_updated) {
            const date = new Date(last_updated);
            formattedLastUpdated = date.toLocaleString('zh-CN', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
        }
        
        // 渲染HTML
        const html = `
            <h3>使用时长统计</h3>
            ${formattedLastUpdated ? `<p id="last-updated">最后更新: ${formattedLastUpdated}</p>` : ''}
            <div class="usage-container">
                <!-- 应用使用时长 -->
                <div class="usage-section">
                    <h4>应用</h4>
                    <div class="usage-list app-list">
                        ${this.renderUsageItems(app_usage)}
                    </div>
                </div>
                
                <!-- 网站使用时长 -->
                <div class="usage-section">
                    <h4>网站</h4>
                    <div class="usage-list website-list">
                        ${this.renderUsageItems(website_usage)}
                    </div>
                </div>
            </div>
        `;
        
        this.container.innerHTML = html;
    }

    renderUsageItems(items) {
        if (!items || Object.keys(items).length === 0) {
            return '<div class="usage-item">暂无数据</div>';
        }
        
        // 按使用时长排序（progress值）
        const sortedItems = Object.entries(items).sort(([, dataA], [, dataB]) => {
            return dataB.progress - dataA.progress;
        });
        
        return sortedItems.map(([name, data]) => {
            const { icon, formatted_time, progress } = data;
            let iconHtml = '';
            
            if (icon) {
                iconHtml = `
                    <img src="/plugin/screen_usage_time/icons/${icon}" alt="${name}" onerror="this.style.display='none';this.nextElementSibling.style.display='block';">
                    <svg t="1770737402316" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="4872" width="40" height="40" style="display: none;"><path d="M512 51.2c254.08 0 460.8 206.72 460.8 460.8 0 254.08-206.72 460.8-460.8 460.8-254.08 0-460.8-206.72-460.8-460.8C51.2 257.92 257.92 51.2 512 51.2M512 0C229.248 0 0 229.248 0 512c0 282.752 229.248 512 512 512 282.752 0 512-229.248 512-512C1024 229.248 794.752 0 512 0L512 0 512 0zM512 0M477.888 640c-0.256 0-0.32-14.4-0.32-18.88 0-26.496 3.776-48.704 11.264-67.968 5.504-14.528 14.4-28.8 26.624-43.584 9.024-10.752 25.216-26.24 48.576-46.848 23.36-20.608 38.592-36.992 45.568-49.28C616.512 401.152 620.096 387.84 620.096 373.312c0-26.24-10.24-49.344-30.72-69.184-20.48-19.84-45.696-29.824-75.456-29.824-28.736 0-52.736 9.024-72 27.008C422.592 319.36 409.984 347.52 403.968 385.728L334.656 377.472c6.272-51.264 24.832-90.496 55.68-117.76C421.184 232.448 461.952 218.88 512.704 218.88c53.76 0 96.64 14.656 128.64 43.904 32 29.248 48 64.64 48 106.112 0 24-5.632 46.144-16.896 66.368-11.264 20.224-33.28 44.864-65.984 73.856C584.448 528.64 570.112 542.976 563.392 552.256 556.608 561.536 551.616 570.752 548.416 582.784 545.152 594.88 543.232 640 542.784 640L477.888 640 477.888 640zM479.872 768.384l0-64.192 64.192 0 0 64.192L479.872 768.384 479.872 768.384z" fill="#272636" p-id="4873"></path></svg>
                `;
            } else {
                iconHtml = `
                    <svg t="1770737402316" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="4872" width="40" height="40"><path d="M512 51.2c254.08 0 460.8 206.72 460.8 460.8 0 254.08-206.72 460.8-460.8 460.8-254.08 0-460.8-206.72-460.8-460.8C51.2 257.92 257.92 51.2 512 51.2M512 0C229.248 0 0 229.248 0 512c0 282.752 229.248 512 512 512 282.752 0 512-229.248 512-512C1024 229.248 794.752 0 512 0L512 0 512 0zM512 0M477.888 640c-0.256 0-0.32-14.4-0.32-18.88 0-26.496 3.776-48.704 11.264-67.968 5.504-14.528 14.4-28.8 26.624-43.584 9.024-10.752 25.216-26.24 48.576-46.848 23.36-20.608 38.592-36.992 45.568-49.28C616.512 401.152 620.096 387.84 620.096 373.312c0-26.24-10.24-49.344-30.72-69.184-20.48-19.84-45.696-29.824-75.456-29.824-28.736 0-52.736 9.024-72 27.008C422.592 319.36 409.984 347.52 403.968 385.728L334.656 377.472c6.272-51.264 24.832-90.496 55.68-117.76C421.184 232.448 461.952 218.88 512.704 218.88c53.76 0 96.64 14.656 128.64 43.904 32 29.248 48 64.64 48 106.112 0 24-5.632 46.144-16.896 66.368-11.264 20.224-33.28 44.864-65.984 73.856C584.448 528.64 570.112 542.976 563.392 552.256 556.608 561.536 551.616 570.752 548.416 582.784 545.152 594.88 543.232 640 542.784 640L477.888 640 477.888 640zM479.872 768.384l0-64.192 64.192 0 0 64.192L479.872 768.384 479.872 768.384z" fill="#272636" p-id="4873"></path></svg>
                `;
            }

            return `
                <div class="usage-item">
                    <div class="app-icon">
                        ${iconHtml}
                    </div>
                    <div class="app-info">
                        <div class="app-name">${name}</div>
                        <div class="app-time">${formatted_time}</div>
                    </div>
                    <div class="app-progress">
                        <div class="progress-bar" style="width: ${progress}%"></div>
                    </div>
                </div>
            `;
        }).join('');
    }
}

// 初始化
if (typeof window !== 'undefined') {
    window.ScreenUsageTime = ScreenUsageTime;
    // 当DOM加载完成后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            window.screenUsageTime = new ScreenUsageTime();
        });
    } else {
        window.screenUsageTime = new ScreenUsageTime();
    }
}
