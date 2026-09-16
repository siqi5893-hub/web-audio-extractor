# 通用网页音频提取器

输入公开网页链接，提取其中的音频并输出 MP3。程序以 `yt-dlp` 作为通用提取引擎，并允许针对特定网页播放器增加适配器。提供命令行、网页界面、Docker Compose 和自动测试。

## 支持范围

- 默认接受任意解析到公网地址的 HTTPS 网页，并交给 `yt-dlp` 提取最佳音轨、转换为 MP3。
- 对部分特殊网页播放器包含独立适配器；172Mix 仅作为其中一个兼容示例，不是产品用途限制。
- 可通过 `ALLOWED_DOMAINS` 改成严格白名单，例如 `example.com,example.net`。
- 不支持 DRM、付费墙、私密内容和绕过访问控制。

## 本机安装

需要 Python 3.10+ 与 FFmpeg：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
web-audio-extract 'https://m.172mix.com/play/217861'
```

网页模式：

```bash
export APP_TOKEN='换成随机长密码'
web-audio-extract-server
```

访问 `http://127.0.0.1:8081`。

## Docker Compose

创建 `.env` 并填写 `APP_TOKEN`，然后：

```bash
docker compose up -d --build
```

Linux Compose 使用宿主网络，减少部分媒体站对 Docker NAT 的误拦截，但服务仍只监听 `127.0.0.1:8081`。公网使用时请配置 HTTPS 反向代理和额外身份验证。

如确需 Cookie，在宿主机准备 Netscape 格式 Cookie 文件，将它只读挂载进容器，并通过 `MEDIA_COOKIES` 指向容器内路径；不要把 Cookie 放入代码仓库。

## 安全设计

- 仅 HTTPS；拒绝 URL 凭据、自定义端口、IP 地址和域名伪装。
- 每次任务会解析目标域名并拒绝私网、回环、链路本地和保留地址；可选白名单采用严格的根域名/子域名边界匹配。
- `yt-dlp` 和 FFmpeg 均以参数数组执行，不调用 Shell。
- Cookie 不写入仓库或镜像；只读 Cookie 使用时会复制到 `0600` 临时文件，任务结束即删除。
- 网页模式限制请求体和并发任务，隐藏内部错误，并设置 CSP 等安全响应头。
- 面向公网部署时建议设置 `ALLOWED_DOMAINS`，并让服务保持在反向代理和身份认证后方。

## 测试

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## 使用边界

请只提取你拥有、获授权或平台允许下载的内容。不同站点更新后可能需要升级 `yt-dlp` 或增加新的适配器。
