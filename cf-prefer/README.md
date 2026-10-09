# 我的 Cloudflare 优选 IP

按照 ahang39/router 公开的“本机测速、输出数据”方式实现；不是其未公开脚本的复刻。
测速工具使用 [XIU2/CloudflareSpeedTest](https://github.com/XIU2/CloudflareSpeedTest)。
本包只含调用和转换脚本，不含第三方程序或虚构测速结果。

## 首次运行

1. 在平时上网的电脑安装 Python 3.9 或更新版本。
2. 从 [官方 Releases](https://github.com/XIU2/CloudflareSpeedTest/releases/latest) 下载对应系统、CPU 的压缩包，将 `cfst` 或 `cfst.exe` 放在本目录。部分旧版本名为 `CloudflareST`，可以修改 config.json 中的 binary 路径。
3. 在本目录打开终端，执行下面的命令。Windows 将 `python3` 换为 `py -3`。

```sh
python3 prefer.py update-ips
python3 prefer.py run
```

macOS/Linux 如提示程序无执行权限，先运行 `chmod +x cfst`。
测速应从你的实际使用网络发起；检查本机/路由器代理或 VPN 是否改变了测速路径。
脚本不会修改系统代理或路由。

输出：

- `output/all.txt`：`IP:443#地区|延迟ms|速度MB/s`，可用作 edgetunnel 自定义优选列表。
- `output/latest.csv`：本轮工具导出的完整 CSV（不是所有 Cloudflare IP 的全量测试）。

地区名称对应测速响应的机房代码；不代表代理出口所在地。

## 默认筛选与调整

config.json 默认并发 30，每个 IP 测 4 次，延迟不超过 300ms、无丢包。
从符合延迟条件的候选中按工具逻辑做 20 个下载测速，每个最长 10 秒，
随后筛出速度至少 1 MB/s 的结果，按下载速度降序、延迟升序选前 10 个。
`min_speed_mb_s` 的单位是 MB/s（与工具 CSV 相同），不是 Mbps。
测速会实际下载数据，数据量取决于速度与测试数量。

`test_url` 留空时采用 CFST 默认地址；上游说明该默认地址不保证可用。
如果全为 0 或失败，填写自己可用的 Cloudflare CDN HTTPS 大文件直链再试。
测速地址应能持续返回足够大小的文件；普通网页不适合作为下载测速文件。
没有合格结果、程序失败或超时，不覆盖上一次的输出。
结果数量可能少于 10；这些只是本次抽样候选中排名靠前的 IP。

已有测速 CSV 时，可以跳过网络测速直接转换：

```sh
python3 prefer.py convert --csv result.csv
```

## 定时与发布

先手动跑通一次，再在同一设备设置每天运行 `prefer.py run`。
Windows 使用任务计划程序；Linux 使用 cron；macOS 使用 launchd。
定时任务需填写 Python 与脚本的绝对路径，设备需要开机联网。
同一输出目录不要同时运行多个任务。

如果需要类似原作者的订阅链接，在自己的公开 GitHub 仓库根目录上传生成的
`all.txt` 与 `latest.csv`，即可通过以下地址访问（替换用户名和仓库名）：

```text
https://raw.githubusercontent.com/你的用户名/你的仓库/main/all.txt
```

本版本只生成本地文件，不会自动上传 GitHub，尚未安装定时任务。
自动上传需要指定你的仓库及本机 GitHub 登录方式；不要把令牌写进公开仓库。
GitHub 托管运行器上直接测速反映的是运行器网络，不是家里的网络。

## 数据和实现来源

- 参考输出格式：https://github.com/ahang39/router
- 测速工具及参数：https://github.com/XIU2/CloudflareSpeedTest
- 候选 IPv4 网段：https://www.cloudflare.com/ips-v4

尚需在你的设备上进行实际测速；本包的离线验证不代表你所在网络的测速结果。
