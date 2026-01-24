// 登录页面初始化

// 登录函数
async function login() {
    const secret = document.getElementById('secret').value;
    if (!secret) {
        document.getElementById('error-message').style.display = 'block';
        document.getElementById('error-message').textContent = '请输入密钥';
        return;
    }
        try {
            // 现代方式：使用fetch API发送登录请求
            const response = await fetch('/panel/api/init', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ "password": secret,"hashed": true})
            });

            if (response.ok) {
                const response = await fetch('/panel/api/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ password: secret })
                });
                if (response.ok) {
                    // 登录成功，重定向到管理面板
                    // 构建重定向URL，保留主题参数
                    const data = await response.json();

                    document.cookie = `sleepy_secret_token=${data.token};sleepy_secret_refresh_token=${data.refresh_token}; max-age=${30 * 24 * 60 * 60}; path=/; samesite=Lax`;
                    window.location.href = '/panel';
                } else {
                    // 登录失败
                    const data = await response.json();
                    document.getElementById('error-message').style.display = 'block';
                    document.getElementById('error-message').textContent = data.message || '登录错误，请重试';
                    window.location.href = '/panel/login';
                }
            } else {
                // 登录失败
                const data = await response.json();
                document.getElementById('error-message').style.display = 'block';
                document.getElementById('error-message').textContent = data.message || '密钥错误，请重试';
            }
        } catch (error) {
            console.error('登录请求失败:', error);
            document.getElementById('error-message').style.display = 'block';
            document.getElementById('error-message').textContent = '登录请求失败，请检查网络连接';
        }
}

// 验证 cookie 是否有效
async function validateCookie() {
    try {
        // 使用 /panel/verify 验证 cookie 是否有效
        const response = await fetch('/panel/api/init', {
            method: 'GET',
            credentials: 'include', // 包含 cookie
            cache: 'no-cache' // 禁用缓存
        });

        if (response.ok) {
            // cookie 有效，重定向到管理面板
            console.log('Cookie 验证成功，正在重定向到管理面板...');
            window.location.href = '/panel';
            return true;
        } else {
            // cookie 无效，显示登录表单
            console.log('Cookie 验证失败，需要登录');
            return false;
        }
    } catch (error) {
        console.error('验证 cookie 时出错:', error);
        return false;
    }
}

// 初始化事件监听器
document.addEventListener('DOMContentLoaded', function () {
    // 验证 cookie 是否有效
    validateCookie().then(isValid => {
        if (!isValid) {
            // 如果 cookie 无效，设置登录表单事件监听器

            // 按下回车键时触发登录按钮
            document.getElementById('secret').addEventListener('keyup', function (event) {
                if (event.key === 'Enter') {
                    login();
                }
            });

            // 如果存在登录按钮，添加点击事件
            const loginBtn = document.querySelector('.login-btn');
            if (loginBtn) {
                loginBtn.addEventListener('click', login);
            }

            // 隐藏加载消息
            document.getElementById('loading-message').style.display = 'none';
            // 显示登录表单
            document.querySelector('.login-form').style.display = 'block';
        }
    });
});
