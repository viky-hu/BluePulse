# PolicePulse Quick Tunnel 演示

此流程把本机生产版 Pulse 暂时暴露到 Cloudflare Quick Tunnel。访问者能读取当前业务数据库中的公开内容；本机浏览器收藏、已读和历史不会同步给老师。Quick Tunnel 没有在线时长保证，电脑、网络、Pulse 服务和 `cloudflared` 都须保持运行。电脑关机、睡眠或任一进程停止时，网站不可用。

## 启动

1. 确认 `cloudflared` 可从 PowerShell 执行，且本机端口 3000 和 8000 未被其他程序占用。
2. 在 PowerShell 窗口 A 运行下列命令并保持窗口打开：

   ```powershell
   cloudflared tunnel --url http://127.0.0.1:3000
   ```

   从输出复制 HTTPS `trycloudflare.com` 地址。若当前 Quick Tunnel 仍在运行，可继续使用其地址；停止后再启动通常会分配新域名。任何持有该地址的人都能访问演示站。

3. 在 PowerShell 窗口 B，设置隧道域名并启动 Pulse。把示例地址替换成窗口 A 输出的完整 HTTPS 地址：

   ```powershell
   Set-Location D:\pulse
   $env:BLUEPULSE_QUICK_TUNNEL = '1'
   $env:BLUEPULSE_SITE_ORIGIN = 'https://boats-genetics-publishers-retailer.trycloudflare.com'
   $env:BLUEPULSE_API_URL = 'http://127.0.0.1:8000'
   $env:BLUEPULSE_TRUST_PROXY = '0'
   $env:BLUEPULSE_COLLECT_ENABLED = '1'
   $env:BLUEPULSE_MODEL_CALLS_ENABLED = '1'
   .\Pulse.bat --check-config
   .\Pulse.bat
   ```

   启动器只允许明确开启的 HTTPS Quick Tunnel Origin，API 仍只绑定本机，且不会信任转发头。worker 按常规配置运行采集和模型任务，供应商 API 费用正常产生。

4. 用输出的公网地址从外部网络检查主页、全部动态、搜索、文章详情、热点榜和日报。管理员仍须通过 `/admin` 登录；不要把管理员密码放到公开页面或链接里。运行 `Pulse.bat --check-health` 查看本机运行链路。

## 停止、重启和更换域名

- 演示结束时在窗口 B 执行 `Pulse.bat --stop`，再在窗口 A 按 Ctrl+C 停止隧道。
- Quick Tunnel 重启后若获得新域名，在窗口 B 更新 `BLUEPULSE_SITE_ORIGIN`，先执行 `Pulse.bat --stop`，再重新运行 `Pulse.bat --check-config` 和 `Pulse.bat`。站点 Origin 参与服务配置签名；不停止旧服务直接改域名会被启动器拒绝。
- 普通本机启动保持原样：不设置 `BLUEPULSE_QUICK_TUNNEL` 时，`BLUEPULSE_SITE_ORIGIN` 必须匹配本机 Web 地址。

Quick Tunnels 是测试用途，官方说明没有 SLA，最多支持 200 个同时进行中的请求且不支持 SSE。要让电脑关机后仍可访问，应按[公网首发部署手册](policepulse-launch.md)部署到常驻服务器。
