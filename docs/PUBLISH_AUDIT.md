# v1.0.0 发布前检查

日期：2026-11-06。

- Git 可提交源码经常见凭据、私钥、令牌、私人部署路径和运行数据检查，未发现匹配。
- 数据库、温度种子、日志、备份、私人设备别名、官方图标及本地工具不在提交范围。
- 公开 FPK 使用空设备别名配置和项目自有备用图标，没有携带本机历史数据。
- Python / CGI / Shell / JavaScript 检查、11 项 Python 存储与整合测试、图表与别名回归通过。
- manifest 和版本说明统一为 1.0.0，发行包配套 SHA256SUMS。
- Git 提交使用 GitHub noreply 地址。

可复查：

```sh
python3 scripts/check.py
python3 scripts/audit_source.py
python3 scripts/build.py --all
python3 scripts/audit_release.py
```

这份检查覆盖本次源码与公开构建内容，不代替目标 fnOS 上的安装兼容性验证。
