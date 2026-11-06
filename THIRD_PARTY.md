# 第三方组件与资产

## fnOS 原生界面

资源管理 Pro 的 `native.py` 在用户已安装的 fnOS 中读取资源管理模块，做运行时适配。仓库没有复制这些 JavaScript / CSS / 翻译 / 图片模块；`docs/fnos-assets.json` 只包含文件名和哈希，便于核对兼容性。

fnOS 官方资源管理图标不放入可提交源码。源码使用项目自己的备用图标，生成脚本为 `scripts/make_fallback_icon.py`。本机可以把官方图标放在 Git 忽略的 `assets/private/`，显式使用 `--local` 构建。

## fnpack

fnpack 是飞牛官方的打包工具，不作为仓库源码分发。本地 `tools/private/` 可保存工具副本，该目录被 Git 忽略。

文档：https://developer.fnnas.com/docs/cli/fnpack/

## Python / SQLite

应用使用系统 Python 标准库及其 SQLite 模块，没有 pip 运行依赖。Node.js 仅用于开发时的语法和图表测试。
