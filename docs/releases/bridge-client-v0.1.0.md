# fake-ui Bridge Client v0.1.0

这是从 fake-ui 面板 release 中拆出来的独立本机客户端发布。它用于 macOS / Linux / Windows 后端机器本地运行 Xray bridge、打开 `127.0.0.1:19090` 控制台、查看本地服务状态和日志。

## 重点

| 类型 | 内容 |
| --- | --- |
| 独立发布 | 客户端和 VPS 面板分开发布，便于后端机器只下载安装客户端 |
| 通用包 | Release 资产不包含客户域名、UUID、私钥、portal 或真实 `xray-bridge.json` |
| 面板导入 | 真实配置仍由 fake-ui 面板生成，客户把配置导入客户端目录后启动 bridge |
| 三端支持 | 提供 macOS zip、Linux tar.gz、Windows zip 三个资产 |
| 本地控制台 | 客户端自带 `bridge-dashboard.py`，默认只监听 `127.0.0.1:19090` |

## 资产

- `fake-ui-bridge-client-v0.1.0-macos.zip`
- `fake-ui-bridge-client-v0.1.0-linux.tar.gz`
- `fake-ui-bridge-client-v0.1.0-windows.zip`

## 使用

1. 下载对应系统的客户端资产并解压。
2. 从 fake-ui 面板下载真实 `xray-bridge.json`。
3. 把真实配置放入客户端目录。
4. 运行 `start-bridge` 脚本启动 bridge。
5. 运行 `open-dashboard` 脚本打开本地控制台。
