# HTTPS 配置指南

> [!WARNING]
> 本文 100% 由 AI 编写，不保证以下内容的准确性

本文档介绍如何为 Sleepy 配置 HTTPS，以便通过安全连接访问您的状态页面。

## 为什么使用 HTTPS？

HTTPS 提供了以下好处：

1. **加密通信**：保护数据在传输过程中不被窃取或篡改
2. **身份验证**：确保用户连接到的是真实的服务器
3. **数据完整性**：确保数据在传输过程中不被修改
4. **SEO 优势**：搜索引擎更喜欢 HTTPS 网站
5. **现代浏览器兼容性**：许多现代浏览器功能需要 HTTPS

## 配置步骤

### 1. 获取 SSL 证书

您需要一个 SSL 证书才能启用 HTTPS。有几种方式可以获取证书：

#### 使用 Let's Encrypt（推荐）

[Let's Encrypt](https://letsencrypt.org/) 提供免费的 SSL 证书。您可以使用 [Certbot](https://certbot.eff.org/) 工具自动获取和更新证书。

```bash
# 安装 Certbot（Ubuntu/Debian）
sudo apt-get update
sudo apt-get install certbot

# 获取证书（独立模式）
sudo certbot certonly --standalone -d your-domain.com

# 证书将保存在 /etc/letsencrypt/live/your-domain.com/ 目录下
```

#### 自签名证书（仅用于测试）

对于测试环境，您可以创建自签名证书：

```bash
# 生成私钥和证书
openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365
```

注意：自签名证书会导致浏览器显示安全警告，不建议在生产环境中使用。

### 2. 配置 Sleepy 使用 HTTPS

编辑您的 `.env` 文件，添加以下配置：

```
# 启用 HTTPS
sleepy_main_https_enabled = true

# SSL 证书路径（相对于项目根目录或绝对路径）
sleepy_main_ssl_cert = "/path/to/your/cert.pem"

# SSL 密钥路径（相对于项目根目录或绝对路径）
sleepy_main_ssl_key = "/path/to/your/key.pem"
```

如果您使用 Let's Encrypt，路径可能如下：

```
sleepy_main_ssl_cert = "/etc/letsencrypt/live/your-domain.com/fullchain.pem"
sleepy_main_ssl_key = "/etc/letsencrypt/live/your-domain.com/privkey.pem"
```

### 3. 重启 Sleepy 服务

配置完成后，重启 Sleepy 服务以应用更改：

```bash
# 如果使用 systemd
sudo systemctl restart sleepy

# 或者如果使用 panel.sh
./scripts/panel.sh restart
```

## 故障排除

### 证书权限问题

如果遇到权限错误，确保 Sleepy 运行的用户有权读取证书文件：

```bash
# 假设 Sleepy 以 sleepy 用户运行
sudo chown sleepy:sleepy /path/to/your/cert.pem /path/to/your/key.pem
# 或者添加读取权限
sudo chmod 644 /path/to/your/cert.pem
sudo chmod 640 /path/to/your/key.pem
```

### 证书路径错误

确保在 `.env` 文件中指定的路径是正确的。可以使用绝对路径避免混淆。

### 证书过期

Let's Encrypt 证书有效期为 90 天。确保设置自动续期：

```bash
# 添加 cron 任务自动续期
echo "0 0,12 * * * root python -c 'import random; import time; time.sleep(random.random() * 3600)' && certbot renew -q" | sudo tee -a /etc/crontab > /dev/null
```

## 高级配置

### 同时支持 HTTP 和 HTTPS

如果您希望同时支持 HTTP 和 HTTPS，可以使用 Nginx 或 Apache 作为反向代理，将 HTTP 流量重定向到 HTTPS。

#### Nginx 配置示例

```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:9010;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 安全最佳实践

1. **定期更新证书**：确保您的证书不会过期
2. **使用强密码套件**：如果使用 Nginx 或 Apache，配置强密码套件
3. **启用 HSTS**：告诉浏览器始终使用 HTTPS 连接
4. **保护私钥**：确保私钥文件的权限设置正确，不允许未授权访问
