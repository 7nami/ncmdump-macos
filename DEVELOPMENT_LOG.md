# 开发记录

这份文档记录了本次对 `ncmdump-master` 项目做过的主要工作，方便后续维护者理解项目现状、设计取舍和验证过程。

## 1. 初始项目检查

初始目录内容很少：

```text
README.md
main.exe
.gitattributes
```

当时的 `README.md` 只有一句：

```text
转换网易NCM音乐
```

`main.exe` 经检查是：

- Windows PE32+ x86-64 控制台程序。
- Go 编译产物。
- 原始源码路径泄露为 `C:/Users/rq200/Desktop/ncmdump-master/main.go`。
- 不是 macOS 可直接运行的程序。

通过 `strings` 和二进制符号分析，确认它大致功能是：

- 读取网易云音乐 `.ncm` 文件。
- 解密 NCM key。
- 解密音频数据。
- 解析 metadata。
- 输出 MP3 或 FLAC。
- 为 MP3/FLAC 写入标题、艺术家、专辑和封面。

可见的主函数包括：

```text
main.buildKeyBox
main.decryptAes128Ecb
main.PKCS7UnPadding
main.readUint32
main.checkError
main.processFile
main.fixBlockSize
main.addFLACCover
main.addMP3Cover
main.main
```

可见依赖包括：

```text
github.com/bogem/id3v2
github.com/go-flac/go-flac
github.com/go-flac/flacpicture
```

## 2. 编写 macOS 转换脚本

新增了核心脚本：

```text
ncmdump_mac.py
```

脚本实现了 NCM 解码流程：

- 校验 NCM magic header。
- 读取并解密 key。
- 构建 NCM key box。
- 解析 metadata JSON。
- 跳过封面帧。
- 解密音频数据。
- 输出 FLAC 或 MP3。

最初版本用 Python 调用系统 `openssl` 执行 AES-128-ECB 解密，避免引入第三方 Python 依赖。

系统中确认可用：

```text
python3
openssl
```

测试样本来自：

```text
/Users/mcj/Music/网易云音乐
```

该目录中发现多个 `.ncm` 文件，用于验证转换结果。

## 3. 修复 NCM 偏移解析问题

第一次转换后，输出文件扩展名是 `.flac`，但文件头不是 `fLaC`，说明音频解密起始偏移不对。

进一步分析 NCM 文件布局后发现：

- metadata 后不是简单跳过固定 4 字节。
- 该样本使用了 `cover_frame_len` 布局。
- 需要先读取封面帧长度，再读取图片实际长度，再跳过剩余封面帧。

修复后输出文件头变成：

```text
fLaC
```

并被系统 `file` 识别为 FLAC 音频。

## 4. 批量转换验证

用 `/Users/mcj/Music/网易云音乐` 中的 9 个 `.ncm` 文件做过批量测试。

全部转换成功，并被 `file` 识别为 FLAC 音频。

测试输出目录曾为：

```text
converted-test
converted-batch
```

后来按用户要求全部清理。

还清理了临时目录：

```text
/private/tmp/ncmdump-interactive-test
/private/tmp/ncmdump-tag-test
/private/tmp/ncmdump-review-test
/private/tmp/ncmdump-opt-test
/private/tmp/ncmdump-log-test
/private/tmp/ncmdump-final-test
```

## 5. 增加 Terminal 双击入口

新增：

```text
NCM解码.command
```

用途：

- 双击后打开 Terminal。
- 提示用户拖入 `.ncm` 文件或文件夹。
- 支持多文件。
- 支持文件夹递归扫描。
- 输出到原 `.ncm` 同目录。
- 调用项目根目录的 `ncmdump_mac.py`。

默认参数：

```bash
--interactive --workers 4 --max-failures 3
```

## 6. 增加多线程和失败阈值

脚本中加入批量调度逻辑：

- 使用 `ThreadPoolExecutor`。
- 默认 4 线程。
- 单文件失败不影响其他文件继续转换。
- `--max-failures` 达到阈值后停止提交新任务。

失败阈值语义：

- `--max-failures 3`：失败 3 个后停止。
- `--max-failures 0`：禁用自动停止，所有任务都尝试跑完。

后续修复过一个统计问题：

- 触发失败阈值后，不再直接清空 pending future。
- 会取消能取消的任务。
- 已运行任务完成后仍统计结果。
- `skipped` 统计更准确。

## 7. 写入音频标签和封面

为了更接近原 `main.exe` 行为，给脚本补充了标签写入。

FLAC：

- 写入 Vorbis Comment。
- 写入 `TITLE`。
- 写入 `ARTIST`。
- 写入 `ALBUM`。
- 如果 NCM 内有封面，则写入 FLAC Picture block。

MP3：

- 写入 ID3v2.3。
- 写入 `TIT2`。
- 写入 `TPE1`。
- 写入 `TALB`。
- 如果有封面，则写入 APIC。

还修过标签相关细节：

- MP3 ID3v2.3 文本帧使用 UTF-16，带 BOM，更符合 ID3v2.3。
- FLAC Picture block 的 depth 从简单 bit depth 改为 bits-per-pixel。
  - 例如 JPEG RGB 封面写为 `24`。
- ID3 tag size 加了 syncsafe 上限检查。

## 8. 关于 NCM metadata 的取舍

讨论过是否要完整保留 NCM metadata。

最终决定：

- 保留标准播放器常用字段：
  - 歌名
  - 艺术家
  - 专辑
  - 封面
- 不默认保留网易云内部字段：
  - `musicId`
  - `albumId`
  - `mp3DocId`
  - `mvId`
  - `fee`
  - `privilege`
  - `albumPic URL`
  - `volumeDelta`

原因：

- 这些不是标准播放器普遍识别的核心标签。
- 离开网易云客户端后通常没有实际作用。
- 如果需要调试或追溯，可以启用 sidecar JSON 输出。

## 9. 输出命名策略修改

早期脚本按 metadata 命名：

```text
Artist - Title.flac
```

后来用户要求改为：

```text
原 .ncm 文件名，只改扩展名
```

因此现在行为是：

```text
Martin Garrix,Mesto - WIEE.ncm
Martin Garrix,Mesto - WIEE.flac
```

如果文件已存在：

```text
Martin Garrix,Mesto - WIEE (2).flac
```

还修过一个细节：

- `safe_filename` 不再压缩连续空格。
- 只替换 macOS 路径非法字符，并裁剪过长文件名。

## 10. 原子写入和自检

为了避免留下半成品文件，加入了原子写入：

- 先写同目录隐藏临时文件。
- 自检通过后用 `os.replace` 改名为最终文件。
- 失败时删除临时文件。

临时文件形如：

```text
.song.flac.<pid>.<thread>.<uuid>.tmp
```

加入转换后自检：

FLAC 自检：

- 必须以 `fLaC` 开头。
- metadata block 必须能完整解析。
- 必须存在 STREAMINFO。
- metadata 后必须存在音频帧数据。

MP3 自检：

- 跳过已有 ID3 tag。
- 查找有效 MP3 frame sync。
- 检查 MPEG version、layer、bitrate、sample rate 字段。

自检失败时会提示用户检查源 `.ncm` 是否损坏。

## 11. 增加日志

加入日志文件功能。

默认日志路径：

```text
~/Music/ncmdump_mac.log
```

支持：

```bash
--log /path/to/run.log
--no-log
```

日志内容包括：

- 运行开始时间。
- worker 数。
- 失败阈值。
- 总文件数。
- 每个文件的 OK 或 FAIL。
- 输出路径。
- 失败原因。
- 结束统计。

终端和 GUI 中也会显示失败汇总。

测试过：

- 一个坏 `.ncm` 文件会输出：

```text
[FAIL 1/2] /path/to/broken.ncm
  Reason: not an NCM file: bad magic header
```

## 12. 增加输入校验

后来检查发现：

- GUI 使用 `integerValue` 时，字符串、符号会被 Cocoa 转成 `0`。
- 线程数会被悄悄修正成 `1`。
- 失败阈值会被悄悄修正成 `0`。
- CLI 对超大正数也没有限制。

因此补了显式校验。

现在：

- 线程数必须是 `1...32` 的整数。
- 失败阈值必须是 `0...100000` 的整数。
- 字符串拒绝。
- 特殊符号拒绝。
- 负数拒绝。
- 线程数 `0` 拒绝。
- 失败阈值 `0` 允许，表示禁用自动停止。
- 过大数字拒绝。

CLI 验证过：

```text
--workers abc      -> 拒绝
--workers 0        -> 拒绝
--workers @@       -> 拒绝
--workers 超大数字 -> 拒绝
--max-failures -1  -> 拒绝
--max-failures nan -> 拒绝
--max-failures 0   -> 允许
```

## 13. Swift 原生 GUI

新增 Swift AppKit GUI：

```text
macos-app/NCMDecoderApp.swift
macos-app/Info.plist
```

构建脚本：

```text
build_app.sh
```

构建结果：

```text
NCM 解码.app
```

GUI 功能：

- 添加 NCM 文件。
- 添加文件夹。
- 清空列表。
- 开始转换。
- 运行日志窗口。
- 完成后可选择打开输出目录。
- 失败时弹窗提示。
- 可折叠高级选项。

高级选项包含：

- 线程数。
- 失败阈值。
- 递归扫描文件夹。
- 生成 sidecar。
- 写入音频标签和封面。
- 写入日志。
- 日志路径。
- 输出到原文件同目录。
- 输出到指定目录。

GUI 调用 `.app` 包内的：

```text
NCM 解码.app/Contents/Resources/ncmdump_mac.py
```

`.command` 调用项目根目录的：

```text
ncmdump_mac.py
```

因此修改脚本后：

- `.command` 立即使用新脚本。
- `.app` 需要重新运行 `./build_app.sh`。

## 14. GUI 布局问题和修复

第一次加入高级选项时 UI 很差：

- 高级选项展开后控件重叠。
- 复选框和主按钮区压在一起。
- 使用 `NSBox + NSGridView + disclosure bezel` 的布局不稳定。

用户截图指出后，重新检查并修复：

- 删除旧布局。
- 改成明确的 vertical stack。
- 高级选项单独放入固定高度 panel。
- 展开时设置 panel 高度为 `150`。
- 折叠时高度为 `0`。
- 控件按行分组。
- 实际打开 `.app` 视觉检查默认态和展开态。

修复后确认：

- 默认状态无重叠。
- 展开高级选项无重叠。

## 15. App 构建和签名

`build_app.sh` 会：

- 删除旧 `.app`。
- 编译 Swift 源码。
- 创建 app bundle。
- 复制 `Info.plist`。
- 复制最新版 `ncmdump_mac.py`。
- 设置可执行权限。
- ad-hoc 签名。

曾经发现：

```text
codesign --verify --deep --strict
```

不通过。

修复方式：

```bash
codesign --force --deep --sign - "NCM 解码.app"
```

现在 `build_app.sh` 已自动执行该步骤。

验证过：

```bash
plutil -lint "NCM 解码.app/Contents/Info.plist"
codesign --verify --deep --strict "NCM 解码.app"
spctl --assess --type execute "NCM 解码.app"
```

## 16. README 补全

原 README 已被替换为完整文档，内容包括：

- 项目用途。
- 文件结构。
- 功能说明。
- GUI 用法。
- `.command` 用法。
- CLI 用法。
- 参数说明。
- 输出行为。
- 错误处理。
- 转换自检。
- 原子写入。
- App 构建。
- 依赖。
- `main.exe` 说明。
- 注意事项。
- 已验证内容。

## 17. 当前项目结构

当前主要文件：

```text
README.md
DEVELOPMENT_LOG.md
ncmdump_mac.py
NCM解码.command
NCM 解码.app
build_app.sh
macos-app/NCMDecoderApp.swift
macos-app/Info.plist
main.exe
.gitattributes
.gitignore
```

`.DS_Store` 可能由 Finder 生成，已在 `.gitignore` 中忽略。

`__pycache__` 和 `*.pyc` 也已在 `.gitignore` 中忽略。

## 18. 最终验证过的方面

已做过的验证包括：

- Python 语法检查：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B -m py_compile ncmdump_mac.py
```

- `.command` zsh 语法检查：

```bash
zsh -n NCM解码.command
```

- Swift 编译。
- `.app` 重新构建。
- `Info.plist` 校验。
- codesign 校验。
- spctl 执行评估。
- 实际打开 `.app` 检查默认 UI。
- 实际打开高级选项检查展开态 UI。
- 使用真实 `.ncm` 样本转换。
- 使用带封面 `.ncm` 样本验证 Picture block。
- 使用坏 `.ncm` 文件验证失败提示和日志。
- 验证输出命名保留原 `.ncm` 文件名。
- 验证重名时生成 `(2)` 文件。
- 验证非法线程数和失败阈值会被拒绝。

## 19. 设计取舍

没有引入第三方 Python 包，原因：

- 降低安装门槛。
- 直接使用系统或 Homebrew 的 OpenSSL。

GUI 用 AppKit 而不是 SwiftUI，原因：

- 单文件 Swift 编译简单。
- 不需要 Xcode project。
- `swiftc + AppKit` 足够满足本工具需求。

保留 `.command`，原因：

- 方便调试。
- 可以直接看到完整终端输出。
- 不需要重新构建 `.app` 就能使用最新版脚本。

默认不生成 sidecar，原因：

- 日常使用只需要音频文件。
- 避免污染音乐目录。
- 高级选项中仍可打开 sidecar。

默认写入标签和封面，原因：

- 更接近原 Windows `main.exe` 行为。
- 转换后的文件更适合导入播放器。

## 20. 后续可考虑的优化

仍可进一步优化：

- 改成真正流式解密，降低大文件批量转换时的内存占用。
- 增加拖文件到 `.app` 图标直接转换的能力。
- 增加进度条。
- 增加取消按钮。
- 给 GUI 增加转换完成统计面板。
- 做正式开发者签名和 notarization。
- 为 Intel Mac 同时构建 x86_64 或 universal binary。
