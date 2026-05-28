# NCM 解码工具

这是一个用于在 macOS 上转换网易云音乐 `.ncm` 加密文件的小工具。项目原始目录只包含一个 Windows 版 `main.exe` 和极简 README；现在补充了 macOS 可运行脚本、终端双击入口、原生 Swift GUI，并构建出 `.app`。

## 当前内容

```text
.
├── README.md
├── ncmdump_mac.py              # macOS/Python 核心转换脚本
├── NCM解码.command             # 双击打开 Terminal 的交互入口
├── NCM 解码.app                # 原生 macOS GUI 应用
├── build_app.sh                # 重新构建 .app 的脚本
├── macos-app/
│   ├── NCMDecoderApp.swift     # AppKit GUI 源码
│   └── Info.plist              # App bundle 元信息
├── main.exe                    # 原 Windows 版可执行文件
└── .gitignore
```

## 已实现功能

- 解密网易云音乐 `.ncm` 文件。
- 输出 `.flac` 或 `.mp3`。
- 输出文件默认保存到原 `.ncm` 所在目录。
- 保持原 `.ncm` 文件名，只替换扩展名。
- 如果目标文件重名，自动生成 `文件名 (2).flac` 这种名字。
- 写入常用音频标签：
  - 歌名
  - 艺术家
  - 专辑
  - 封面
- 支持 FLAC Vorbis Comment 和 Picture block。
- 支持 MP3 ID3v2.3 和 APIC 封面。
- 转换后进行自检：
  - FLAC 检查 metadata block 和 STREAMINFO。
  - MP3 检查有效 frame sync。
- 先写临时文件，自检通过后再原子改名，避免留下半成品。
- 支持批量转换和多线程。
- 支持日志文件。
- 失败时显示具体文件和原因。
- 支持失败达到阈值后自动停止后续任务。
- 提供 Terminal 交互入口和原生 macOS GUI。

## GUI 用法

双击：

```text
NCM 解码.app
```

GUI 支持：

- 添加 NCM 文件
- 添加文件夹
- 清空列表
- 开始转换
- 转换完成后打开输出目录
- 可折叠高级选项

高级选项包括：

- 线程数，范围 `1...32`
- 失败阈值，范围 `0...100000`
- 是否递归扫描文件夹
- 是否生成 metadata JSON 和封面 sidecar
- 是否写入音频标签和封面
- 是否写入日志
- 日志路径
- 输出到原文件同目录
- 输出到指定目录

输入校验：

- 线程数必须是整数，不能是字符串、符号、负数、0 或过大数字。
- 失败阈值必须是整数，允许 `0`，表示不因失败次数自动停止。
- 非法输入会弹窗提示，不会开始转换。

## Terminal 双击入口

双击：

```text
NCM解码.command
```

然后把 `.ncm` 文件或文件夹拖进 Terminal，按 Enter。

这个入口适合调试，因为能直接看到终端输出。它调用项目根目录里的 `ncmdump_mac.py`。

## 命令行用法

转换单个文件：

```bash
./ncmdump_mac.py "/path/to/song.ncm"
```

转换目录：

```bash
./ncmdump_mac.py "/path/to/folder" -r
```

指定输出目录：

```bash
./ncmdump_mac.py "/path/to/song.ncm" -o "/path/to/output"
```

设置线程数：

```bash
./ncmdump_mac.py "/path/to/folder" -r --workers 4
```

失败达到 3 个后停止：

```bash
./ncmdump_mac.py "/path/to/folder" -r --max-failures 3
```

禁用失败阈值：

```bash
./ncmdump_mac.py "/path/to/folder" -r --max-failures 0
```

不写标签：

```bash
./ncmdump_mac.py "/path/to/song.ncm" --no-tags
```

生成 metadata JSON 和封面 sidecar：

```bash
./ncmdump_mac.py "/path/to/song.ncm"
```

不生成 sidecar：

```bash
./ncmdump_mac.py "/path/to/song.ncm" --no-sidecars
```

指定日志：

```bash
./ncmdump_mac.py "/path/to/folder" -r --log "/path/to/run.log"
```

禁用日志：

```bash
./ncmdump_mac.py "/path/to/folder" -r --no-log
```

交互模式：

```bash
./ncmdump_mac.py --interactive
```

## CLI 参数

```text
inputs                 NCM 文件或目录
-o, --output           指定统一输出目录
-r, --recursive        递归扫描目录
-w, --workers          线程数，1 到 32
--max-failures         失败阈值，0 到 100000；0 表示禁用自动停止
--interactive          交互模式，提示拖入文件
--no-sidecars          不输出 metadata JSON 和封面 sidecar
--no-tags              不写入音频标签和封面
--log                  指定日志文件
--no-log               禁用日志
```

默认日志路径：

```text
~/Music/ncmdump_mac.log
```

## 输出行为

默认输出到原 `.ncm` 文件同目录。

例子：

```text
Lady Gaga - Vanish Into You.ncm
```

转换后：

```text
Lady Gaga - Vanish Into You.flac
```

如果目标文件已存在：

```text
Lady Gaga - Vanish Into You (2).flac
```

## 错误处理

单个文件失败不会立刻终止整个批次。脚本会：

- 在终端或 GUI 日志里显示失败文件。
- 显示失败原因。
- 写入日志。
- 达到 `--max-failures` 阈值后停止提交新任务。

常见错误：

```text
not an NCM file: bad magic header
```

说明文件不是有效 `.ncm`。

```text
self-check failed: missing FLAC STREAMINFO block
```

说明转换后的音频结构不完整，建议检查源 `.ncm` 是否损坏。

```text
openssl AES decrypt failed
```

说明 AES 解密失败，可能是文件损坏或 OpenSSL 不可用。

## 转换自检

脚本不会只看扩展名判断成功。

FLAC 自检包括：

- 文件头必须是 `fLaC`。
- metadata block 必须可完整解析。
- 必须存在 STREAMINFO。
- metadata 后必须还有音频帧数据。

MP3 自检包括：

- 跳过已有 ID3 tag。
- 在音频区域查找有效 MP3 frame sync。
- 检查 MPEG version、layer、bitrate 和 sample rate 字段是否合法。

自检失败时不会生成最终输出文件。

## 原子写入

转换结果先写入同目录隐藏临时文件：

```text
.song.flac.<pid>.<thread>.<uuid>.tmp
```

写入和自检都成功后，再用 `os.replace` 改名为最终文件。这样中途失败或异常退出时，不会留下看起来像成功的半成品。

## 重新构建 App

修改 `ncmdump_mac.py` 或 Swift 源码后，需要重新构建 `.app`：

```bash
./build_app.sh
```

构建脚本会：

- 编译 `macos-app/NCMDecoderApp.swift`
- 创建 `NCM 解码.app`
- 复制最新版 `ncmdump_mac.py` 到 app resources
- 写入 `Info.plist`
- 对 `.app` 做 ad-hoc 签名

构建后的脚本位置：

```text
NCM 解码.app/Contents/Resources/ncmdump_mac.py
```

注意：`.command` 使用项目根目录的 `ncmdump_mac.py`；`.app` 使用包内复制的脚本。因此修改脚本后，`.command` 会立即使用新版，`.app` 需要重新构建。

## 依赖

运行脚本需要：

- macOS
- Python 3
- OpenSSL

构建 `.app` 需要：

- Swift 编译器
- Xcode Command Line Tools 或 Xcode

## main.exe 说明

`main.exe` 是原项目中的 Windows 64 位 Go 控制台程序。它不是 macOS 可执行文件。

静态分析可见：

- Go 编译产物。
- 源码路径曾为 `C:/Users/rq200/Desktop/ncmdump-master/main.go`。
- 主要函数包括：
  - `main.processFile`
  - `main.buildKeyBox`
  - `main.decryptAes128Ecb`
  - `main.addFLACCover`
  - `main.addMP3Cover`
- 依赖包括：
  - `github.com/bogem/id3v2`
  - `github.com/go-flac/go-flac`
  - `github.com/go-flac/flacpicture`

当前 macOS 版本复刻了它的核心行为，并额外增加 GUI、日志、并发、输入校验、自检和原子写入。

## 注意事项

- 本工具只处理本地 `.ncm` 文件。
- 不会联网下载封面或元数据。
- 网易云内部字段，例如 `musicId`、`fee`、`privilege`、`albumPic URL`，默认不写入音频标签。
- 这些内部字段通常不是标准播放器会使用的信息。
- 如果需要完整调试信息，可以启用 sidecar 输出保留 JSON。

## 已验证

已在本机样本目录中验证：

- 多个 `.ncm` 文件可批量转换。
- FLAC 输出可被系统 `file` 识别。
- 标签字段写入成功。
- 带封面的样本可写入 FLAC Picture block。
- 坏文件会报错并写入日志。
- GUI 构建通过。
- `.app` 的 `Info.plist`、签名和执行评估通过。
