# 安装与维护

## 首次安装

1. 运行源码检查并构建 `resmonpro` FPK。
2. 登录 fnOS，在应用中心手动安装并启动资源管理 Pro。
3. 验证侧栏「运行状态 → 进程管理 → 硬件温度」。

资源与温度采集由 Pro 同时启停，无需安装独立温度应用。

直接打开 CGI 链接而没有有效登录态可能返回 `invalid token`。应从已登录的 fnOS 桌面启动应用；不要把后端回环端口暴露到局域网或公网。

## AMD GPU 的 Compute / Encoder

基础 GPU 利用率、温度和显存通过只读 sysfs 获取。跨进程 DRM 引擎计数需要单独的只读辅助服务。

在 NAS 上由管理员执行一次：

```sh
sudo python3 /var/apps/resmonpro/target/support/install-gpu-helper.py
```

安装器将代码复制到 root 所有的 `/usr/local/lib/resmonpro/`，创建并启用 `resmonpro-gpu.service`。该服务无网络访问，只输出聚合的 GPU 引擎指标到 `/run/resmonpro-gpu/engines.json`，不输出进程信息或命令行。主应用和 CGI 仍使用包用户。辅助服务在主采集器停止时暂停，FPK 移除后退出。

没有安装辅助服务、读数过期或指标不支持时，Compute / Encoder 记录为空值，不伪造 0%。当前集成验证于 AMD Radeon 780M；没有验证 NVIDIA、Intel GPU。

更新辅助服务时，重新运行安装器以刷新 root 所有的副本。若不再需要：

```sh
sudo systemctl disable --now resmonpro-gpu.service
```

## 数据位置

| 数据 | 位置 |
|---|---|
| Pro 资源历史 | `/var/apps/resmonpro/var/history.sqlite3` |
| 温度历史与统计 | `/var/apps/resmonpro/var/temperature/history.sqlite3` |
| 温度备份 | `/var/apps/resmonpro/var/temperature/backups/` |
| 手机实时计数缓存（非历史） | `/var/apps/resmonpro/var/mobile-counters.json` |
| 应用日志 | 各应用 `var/` 目录 |

传感器元数据可能包含主机名、硬盘序列号和设备路径。不要将这些运行目录作为项目源码提交。

## 升级前

备份 Pro 的数据目录（包括 temperature 子目录），通过 fnOS 支持的安装 / 升级入口操作。检查安装后的版本、采样进程、数据库和历史曲线；不要仅依赖安装命令返回码。旧历史不随源码或发行包提供，新安装不会得到开发设备的历史记录。

## 前端适配检查

`native.py` 从目标 fnOS 的 `/usr/trim/www` 只读加载模块，注入 Pro 自有适配代码，不修改系统文件。

如果把源码放到 NAS，可先运行：

```sh
python3 scripts/check_fnos_assets.py --web /usr/trim/www
```

这个检查核对文件、结构替换条件和已知哈希，不代表浏览器回归已完成。还需验证登录入口、三个侧栏页签、四档历史和温度页交互。
