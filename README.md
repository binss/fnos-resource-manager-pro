# 资源管理 Pro · Resource Manager Pro for fnOS

基于飞牛 fnOS 原版资源管理改进，保留原有界面风格与进程管理，新增资源负载历史曲线和多硬件温度曲线。使用 Python 实现后台持续采集，以 FPK 形式安装。

## 功能

- CPU、内存、有线网络和 AMD GPU 的后台记录，关闭窗口也继续采集。
- 实时页预载约 3 分钟记录，最多 60 个点，每 3 秒刷新。
- 1 小时 / 24 小时 / 7 天 / 30 天历史；长期数据按分钟采样并按范围聚合。
- 温度页按 CPU / GPU、RAM、HDD、SSD、Network 分组，支持曲线叠加、悬停聚焦、点击淡化和恢复。
- 温度 SQLite 明细、每日统计、备份与 CSV 导出；设备名称可以通过 JSON 覆盖。
- 手机使用独立的应用网关页面，不启动飞牛网页登录框架；底部导航、资源圆环总览和硬盘卡片；进程列表支持搜索、排序及展开详情，曲线支持触摸查看读数。自动识别窄屏与触摸横屏，也可手动切换布局。
- 风扇控制：NAS 原生静音 / 均衡 / 全速模式及 RPM；可选连接本机 Home Assistant 控制弱电箱风扇，支持手动调速与恢复已有自动温控。
- 使用已安装 fnOS 的资源管理前端组件；本项目不分发、不修改系统前端文件。

## 单个 FPK

`packages/resmonpro` 包含运行状态、进程管理、温度采集、温度页与风扇控制。资源采集器和温度采集器由同一个 Pro 服务管理。

NAS 端使用系统 Python 3 标准库、Linux `/proc`、`/sys` 与 `lsblk`，无需 pip、Docker 或 CDN。实机使用 Python 3.11。macOS 只用于编辑、检查和打包，不用于读取 NAS 硬件。

## 本地检查

需要 Python 3、Node.js 和 Bash；Node.js 仅用于开发检查。

```sh
python3 scripts/check.py
```

检查包括 Python / CGI / JavaScript / Shell 语法、SQLite 存储回归、温度叠加图及平滑曲线断点测试，不连接 NAS。

## 构建

安装飞牛官方 [fnpack](https://developer.fnnas.com/docs/cli/fnpack/)，可通过 PATH、`FNPACK` 环境变量或 `--fnpack` 指定。当前构建验证使用 fnpack 1.2.3。

```sh
python3 scripts/build.py --all --fnpack /path/to/fnpack
# 或指定主包
python3 scripts/build.py resmonpro --fnpack /path/to/fnpack
```

可运行 `python3 scripts/audit_release.py` 检查公开包内是否误带运行数据或本机配置。

结果位于 `dist/public/`，包含一个独立 FPK 和 `SHA256SUMS`。默认构建使用本项目的蓝色曲线备用图标，不读取私人配置，不打包历史数据或官方前端资产。

### 仅供本机的构建

`assets/private/` 和 `tools/private/` 不进入 Git。可将有权使用的 fnOS 原版资源管理图标放到 `assets/private/fnos-resource-manager.png`，将设备别名配置放到 `assets/private/device-aliases.json`。

```sh
python3 scripts/build.py --all --local
```

结果位于 `dist/local/`，与公开构建分开。桌面项目的本地工具和配置已准备好；这些文件不属于待提交源码。

## 风扇控制

桌面侧栏和手机底栏均可打开。NAS 调速复用当前飞牛登录和管理员权限，不发起单独登录或授权，不清理会话凭据；仅在设备声明支持时启用三档按钮。适配不兼容或连接失败时禁用，不直接写入硬件寄存器。风扇页按需加载原生客户端，资源监控入口无需启动此客户端。

弱电箱为可选功能：在连接设置填写本机 Home Assistant 长期访问令牌、风扇实体与温度实体。令牌保存在应用数据目录 `fan/connection.json`，权限 0600，不进入源码和 FPK。连接仅使用本机回环 8123 端口。依赖现有自动化 ID `weak_box_fan_speed_schedule` 和 `weak_box_fan_temperature_cooldown`，不会创建或修改温控规则。手动调速会暂停这两条自动化并取消待执行动作，恢复自动时重新判断档位。页面中的温控阈值和估算电压是原方案参考值，实际行为以 HA 配置和设备回读为准。

## 设备名称

公共默认配置为 `packages/resmonpro/app/ui/device-aliases.json`，初始值是 `{}`。按设备类型及稳定的传感器 key 或型号设置别名，格式见 [示例](assets/device-aliases.example.json)。

```json
{
  "cpu": { "example-cpu-driver": "CPU · Your CPU Model" },
  "network": { "example-network-sensor": "Ethernet 1 · Model · 2.5GbE" }
}
```

别名不会改变传感器 key、历史记录或采集结果。没有匹配别名时显示采集端实际提供的型号 / 驱动名称，不猜测 CPU、GPU 型号或网口带宽。

## 安装、兼容性和 GPU

- [安装与维护](docs/INSTALL.md)
- [架构、数据与兼容限制](docs/ARCHITECTURE.md)
- [第三方资产说明](THIRD_PARTY.md)
- [准备情况与后续事项](docs/RELEASE_NOTES.md)

原生前端适配与 fnOS 安装版本绑定。系统升级可能改变资源管理模块文件名和结构，发布前需要在目标版本验证；不能把“能打包”当成“所有 fnOS 版本兼容”。

## 许可证

本地项目尚未选择开源许可证。发布前由作者确定；fnOS 官方前端、图标及 fnpack 不包含在项目代码的授权范围中。
