import AppKit
import UniformTypeIdentifiers

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var window: NSWindow!
    private var tableView: NSTableView!
    private var logView: NSTextView!
    private var convertButton: NSButton!
    private var advancedButton: NSButton!
    private var advancedPanel: NSView!
    private var advancedHeight: NSLayoutConstraint!

    private var openOutputCheckbox: NSButton!
    private var workersField: NSTextField!
    private var maxFailuresField: NSTextField!
    private var recursiveCheckbox: NSButton!
    private var sidecarsCheckbox: NSButton!
    private var tagsCheckbox: NSButton!
    private var logCheckbox: NSButton!
    private var logPathField: NSTextField!
    private var originalOutputRadio: NSButton!
    private var customOutputRadio: NSButton!
    private var outputPathField: NSTextField!

    private var selectedPaths: [String] = []
    private var outputDirectories: Set<String> = []
    private var failures: [(String, String)] = []
    private var process: Process?

    func applicationDidFinishLaunching(_ notification: Notification) {
        buildWindow()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    private func buildWindow() {
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 860, height: 660),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "NCM 解码"
        window.center()

        let content = NSView()
        window.contentView = content

        let mainStack = NSStackView()
        mainStack.orientation = .vertical
        mainStack.alignment = .leading
        mainStack.spacing = 12
        mainStack.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(mainStack)

        let controls = buildControls()
        let advancedToggleRow = buildAdvancedToggle()
        advancedPanel = buildAdvancedPanel()
        advancedPanel.isHidden = true

        let listLabel = sectionLabel("待转换项目")
        let tableScroll = buildTable()
        let logLabel = sectionLabel("运行日志")
        let logScroll = buildLog()

        let arrangedViews: [NSView] = [controls, advancedToggleRow, advancedPanel, listLabel, tableScroll, logLabel, logScroll]
        for view in arrangedViews {
            mainStack.addArrangedSubview(view)
        }

        advancedHeight = advancedPanel.heightAnchor.constraint(equalToConstant: 0)
        advancedHeight.isActive = true

        NSLayoutConstraint.activate([
            mainStack.topAnchor.constraint(equalTo: content.topAnchor, constant: 18),
            mainStack.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 20),
            mainStack.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -20),
            mainStack.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -18),

            controls.widthAnchor.constraint(equalTo: mainStack.widthAnchor),
            advancedToggleRow.widthAnchor.constraint(equalTo: mainStack.widthAnchor),
            advancedPanel.widthAnchor.constraint(equalTo: mainStack.widthAnchor),
            tableScroll.widthAnchor.constraint(equalTo: mainStack.widthAnchor),
            tableScroll.heightAnchor.constraint(equalToConstant: 190),
            logScroll.widthAnchor.constraint(equalTo: mainStack.widthAnchor),
            logScroll.heightAnchor.constraint(greaterThanOrEqualToConstant: 190),
        ])

        window.makeKeyAndOrderFront(nil)
    }

    private func buildControls() -> NSStackView {
        let addFilesButton = NSButton(title: "添加 NCM 文件", target: self, action: #selector(addFiles))
        let addFolderButton = NSButton(title: "添加文件夹", target: self, action: #selector(addFolder))
        let clearButton = NSButton(title: "清空", target: self, action: #selector(clearFiles))
        convertButton = NSButton(title: "开始转换", target: self, action: #selector(startConvert))
        convertButton.bezelStyle = .rounded
        openOutputCheckbox = NSButton(checkboxWithTitle: "转换完成后打开输出目录", target: nil, action: nil)
        openOutputCheckbox.state = .on

        let row = NSStackView(views: [addFilesButton, addFolderButton, clearButton, convertButton, openOutputCheckbox])
        row.orientation = .horizontal
        row.spacing = 12
        row.alignment = .centerY
        return row
    }

    private func buildAdvancedToggle() -> NSStackView {
        advancedButton = NSButton(title: "显示高级选项", target: self, action: #selector(toggleAdvanced))
        advancedButton.bezelStyle = .rounded
        let row = NSStackView(views: [advancedButton])
        row.orientation = .horizontal
        row.alignment = .leading
        return row
    }

    private func buildAdvancedPanel() -> NSView {
        let panel = NSView()
        panel.translatesAutoresizingMaskIntoConstraints = false
        panel.wantsLayer = true
        panel.layer?.borderWidth = 1
        panel.layer?.borderColor = NSColor.separatorColor.cgColor
        panel.layer?.cornerRadius = 6

        workersField = smallNumberField("4")
        maxFailuresField = smallNumberField("3")

        recursiveCheckbox = NSButton(checkboxWithTitle: "递归扫描文件夹", target: nil, action: nil)
        recursiveCheckbox.state = .on
        sidecarsCheckbox = NSButton(checkboxWithTitle: "生成 metadata JSON 和封面 sidecar", target: nil, action: nil)
        tagsCheckbox = NSButton(checkboxWithTitle: "写入音频标签和封面", target: nil, action: nil)
        tagsCheckbox.state = .on
        logCheckbox = NSButton(checkboxWithTitle: "写入日志", target: self, action: #selector(updateLogControls))
        logCheckbox.state = .on

        logPathField = pathField("\(NSHomeDirectory())/Music/ncmdump_mac.log")
        let chooseLogButton = NSButton(title: "选择日志", target: self, action: #selector(chooseLogPath))

        originalOutputRadio = NSButton(radioButtonWithTitle: "输出到原文件同目录", target: self, action: #selector(selectOriginalOutput))
        originalOutputRadio.state = .on
        customOutputRadio = NSButton(radioButtonWithTitle: "输出到指定目录", target: self, action: #selector(selectCustomOutput))
        outputPathField = pathField("")
        outputPathField.placeholderString = "未选择"
        outputPathField.isEnabled = false
        let chooseOutputButton = NSButton(title: "选择输出目录", target: self, action: #selector(chooseOutputDirectory))

        let stack = NSStackView()
        stack.orientation = .vertical
        stack.spacing = 10
        stack.alignment = .leading
        stack.translatesAutoresizingMaskIntoConstraints = false
        panel.addSubview(stack)

        stack.addArrangedSubview(row([label("线程数"), workersField, label("失败阈值"), maxFailuresField]))
        stack.addArrangedSubview(row([recursiveCheckbox, sidecarsCheckbox, tagsCheckbox]))
        stack.addArrangedSubview(row([logCheckbox, logPathField, chooseLogButton]))
        stack.addArrangedSubview(row([originalOutputRadio, customOutputRadio, outputPathField, chooseOutputButton]))

        NSLayoutConstraint.activate([
            stack.topAnchor.constraint(equalTo: panel.topAnchor, constant: 12),
            stack.leadingAnchor.constraint(equalTo: panel.leadingAnchor, constant: 14),
            stack.trailingAnchor.constraint(lessThanOrEqualTo: panel.trailingAnchor, constant: -14),
        ])

        return panel
    }

    private func buildTable() -> NSScrollView {
        tableView = NSTableView()
        let column = NSTableColumn(identifier: NSUserInterfaceItemIdentifier("path"))
        column.title = "路径"
        column.resizingMask = .autoresizingMask
        tableView.addTableColumn(column)
        tableView.delegate = self
        tableView.dataSource = self

        let scroll = NSScrollView()
        scroll.documentView = tableView
        scroll.hasVerticalScroller = true
        scroll.borderType = .bezelBorder
        scroll.translatesAutoresizingMaskIntoConstraints = false
        return scroll
    }

    private func buildLog() -> NSScrollView {
        logView = NSTextView()
        logView.isEditable = false
        logView.font = NSFont.monospacedSystemFont(ofSize: 12, weight: .regular)

        let scroll = NSScrollView()
        scroll.documentView = logView
        scroll.hasVerticalScroller = true
        scroll.borderType = .bezelBorder
        scroll.translatesAutoresizingMaskIntoConstraints = false
        return scroll
    }

    private func sectionLabel(_ text: String) -> NSTextField {
        let field = NSTextField(labelWithString: text)
        field.font = NSFont.boldSystemFont(ofSize: 13)
        return field
    }

    private func label(_ text: String) -> NSTextField {
        NSTextField(labelWithString: text)
    }

    private func smallNumberField(_ value: String) -> NSTextField {
        let field = NSTextField(string: value)
        field.alignment = .right
        field.widthAnchor.constraint(equalToConstant: 56).isActive = true
        return field
    }

    private func pathField(_ value: String) -> NSTextField {
        let field = NSTextField(string: value)
        field.lineBreakMode = .byTruncatingMiddle
        field.widthAnchor.constraint(greaterThanOrEqualToConstant: 360).isActive = true
        return field
    }

    private func row(_ views: [NSView]) -> NSStackView {
        let row = NSStackView(views: views)
        row.orientation = .horizontal
        row.spacing = 10
        row.alignment = .centerY
        return row
    }

    @objc private func toggleAdvanced() {
        let shouldShow = advancedPanel.isHidden
        advancedPanel.isHidden = !shouldShow
        advancedHeight.constant = shouldShow ? 150 : 0
        advancedButton.title = shouldShow ? "隐藏高级选项" : "显示高级选项"
        window.layoutIfNeeded()
    }

    @objc private func updateLogControls() {
        logPathField.isEnabled = logCheckbox.state == .on
    }

    @objc private func selectOriginalOutput() {
        originalOutputRadio.state = .on
        customOutputRadio.state = .off
        outputPathField.isEnabled = false
    }

    @objc private func selectCustomOutput() {
        originalOutputRadio.state = .off
        customOutputRadio.state = .on
        outputPathField.isEnabled = true
    }

    @objc private func chooseLogPath() {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "ncmdump_mac.log"
        if panel.runModal() == .OK, let url = panel.url {
            logPathField.stringValue = url.path
            logCheckbox.state = .on
            updateLogControls()
        }
    }

    @objc private func chooseOutputDirectory() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            outputPathField.stringValue = url.path
            selectCustomOutput()
        }
    }

    @objc private func addFiles() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        if let ncmType = UTType(filenameExtension: "ncm") {
            panel.allowedContentTypes = [ncmType]
        }
        if panel.runModal() == .OK {
            add(paths: panel.urls.map { $0.path })
        }
    }

    @objc private func addFolder() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        if panel.runModal() == .OK {
            add(paths: panel.urls.map { $0.path })
        }
    }

    private func add(paths: [String]) {
        for path in paths where !selectedPaths.contains(path) {
            selectedPaths.append(path)
        }
        tableView.reloadData()
    }

    @objc private func clearFiles() {
        guard process == nil else { return }
        selectedPaths.removeAll()
        tableView.reloadData()
        logView.string = ""
    }

    @objc private func startConvert() {
        guard process == nil else { return }
        guard !selectedPaths.isEmpty else {
            showAlert(title: "没有选择文件", message: "请先添加 .ncm 文件或包含 .ncm 的文件夹。")
            return
        }
        guard let scriptPath = Bundle.main.resourcePath.map({ "\($0)/ncmdump_mac.py" }) else {
            showAlert(title: "缺少脚本", message: "无法定位 ncmdump_mac.py。")
            return
        }

        guard let workers = parseIntegerField(workersField, name: "线程数", minimum: 1, maximum: 32) else {
            return
        }
        guard let maxFailures = parseIntegerField(maxFailuresField, name: "失败阈值", minimum: 0, maximum: 100000) else {
            return
        }
        if customOutputRadio.state == .on && outputPathField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            showAlert(title: "未选择输出目录", message: "请在高级选项中选择输出目录，或改为输出到原文件同目录。")
            return
        }

        outputDirectories.removeAll()
        failures.removeAll()
        logView.string = ""
        convertButton.isEnabled = false

        var args = [scriptPath]
        args.append(contentsOf: selectedPaths)
        if recursiveCheckbox.state == .on {
            args.append("-r")
        }
        args.append(contentsOf: ["--workers", "\(workers)", "--max-failures", "\(maxFailures)"])
        if sidecarsCheckbox.state == .off {
            args.append("--no-sidecars")
        }
        if tagsCheckbox.state == .off {
            args.append("--no-tags")
        }
        if logCheckbox.state == .on {
            args.append(contentsOf: ["--log", logPathField.stringValue])
        } else {
            args.append("--no-log")
        }
        if customOutputRadio.state == .on {
            args.append(contentsOf: ["-o", outputPathField.stringValue])
        }

        let task = Process()
        let executable = pythonURL()
        task.executableURL = executable
        task.arguments = pythonArguments(args, executable: executable)
        task.environment = processEnvironment()

        let pipe = Pipe()
        task.standardOutput = pipe
        task.standardError = pipe
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else { return }
            DispatchQueue.main.async {
                self?.appendLog(text)
                self?.captureResultLines(text)
            }
        }

        task.terminationHandler = { [weak self] finished in
            DispatchQueue.main.async {
                pipe.fileHandleForReading.readabilityHandler = nil
                self?.process = nil
                self?.convertButton.isEnabled = true
                self?.handleCompletion(exitCode: finished.terminationStatus)
            }
        }

        do {
            process = task
            try task.run()
        } catch {
            process = nil
            convertButton.isEnabled = true
            showAlert(title: "启动失败", message: error.localizedDescription)
        }
    }

    private func pythonURL() -> URL {
        let candidates = [
            "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3",
            "/Library/Frameworks/Python.framework/Versions/Current/bin/python3",
            "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3",
            "/usr/bin/python3",
        ]
        for path in candidates where FileManager.default.isExecutableFile(atPath: path) {
            return URL(fileURLWithPath: path)
        }
        return URL(fileURLWithPath: "/usr/bin/env")
    }

    private func parseIntegerField(_ field: NSTextField, name: String, minimum: Int, maximum: Int) -> Int? {
        let raw = field.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard raw.range(of: #"^\d+$"#, options: .regularExpression) != nil, let value = Int(raw) else {
            showAlert(title: "\(name)无效", message: "\(name)必须是 \(minimum) 到 \(maximum) 之间的整数。")
            return nil
        }
        guard value >= minimum && value <= maximum else {
            showAlert(title: "\(name)超出范围", message: "\(name)必须是 \(minimum) 到 \(maximum) 之间的整数。")
            return nil
        }
        return value
    }

    private func pythonArguments(_ args: [String], executable: URL) -> [String] {
        executable.path == "/usr/bin/env" ? ["python3"] + args : args
    }

    private func processEnvironment() -> [String: String] {
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/Current/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return env
    }

    private func appendLog(_ text: String) {
        logView.textStorage?.append(NSAttributedString(string: text))
        logView.scrollToEndOfDocument(nil)
    }

    private func captureResultLines(_ text: String) {
        for line in text.split(separator: "\n", omittingEmptySubsequences: false).map(String.init) {
            if line.hasPrefix("[OK"), let range = line.range(of: " -> ") {
                let outputPath = String(line[range.upperBound...])
                outputDirectories.insert((outputPath as NSString).deletingLastPathComponent)
            } else if line.hasPrefix("[FAIL") {
                let path = line.replacingOccurrences(of: #"^\[FAIL[^\]]*\]\s*"#, with: "", options: .regularExpression)
                failures.append((path, "转换失败，日志中包含具体 Reason。请检查该 NCM 文件是否完整或已损坏。"))
            } else if line.trimmingCharacters(in: .whitespaces).hasPrefix("Reason:"), !failures.isEmpty {
                let reason = line.replacingOccurrences(of: "Reason:", with: "").trimmingCharacters(in: .whitespaces)
                failures[failures.count - 1].1 = reason + "。请检查该音乐文件是否完整或已损坏。"
            }
        }
    }

    private func handleCompletion(exitCode: Int32) {
        if exitCode == 0 {
            if openOutputCheckbox.state == .on {
                openOutputDirectories()
            }
            showAlert(title: "转换完成", message: "全部文件已转换完成。")
        } else {
            let detail = failures.prefix(5).map { "\($0.0)\n\($0.1)" }.joined(separator: "\n\n")
            showAlert(title: "部分文件转换失败", message: detail.isEmpty ? "请查看窗口日志确认失败原因。" : detail)
        }
    }

    private func openOutputDirectories() {
        for directory in outputDirectories {
            NSWorkspace.shared.open(URL(fileURLWithPath: directory))
        }
    }

    private func showAlert(title: String, message: String) {
        let alert = NSAlert()
        alert.messageText = title
        alert.informativeText = message
        alert.alertStyle = .informational
        alert.runModal()
    }
}

extension AppDelegate: NSTableViewDataSource, NSTableViewDelegate {
    func numberOfRows(in tableView: NSTableView) -> Int {
        selectedPaths.count
    }

    func tableView(_ tableView: NSTableView, viewFor tableColumn: NSTableColumn?, row: Int) -> NSView? {
        let identifier = NSUserInterfaceItemIdentifier("cell")
        let cell = tableView.makeView(withIdentifier: identifier, owner: self) as? NSTableCellView ?? NSTableCellView()
        cell.identifier = identifier
        let textField = cell.textField ?? NSTextField(labelWithString: "")
        textField.lineBreakMode = .byTruncatingMiddle
        textField.stringValue = selectedPaths[row]
        if cell.textField == nil {
            textField.translatesAutoresizingMaskIntoConstraints = false
            cell.addSubview(textField)
            cell.textField = textField
            NSLayoutConstraint.activate([
                textField.leadingAnchor.constraint(equalTo: cell.leadingAnchor, constant: 6),
                textField.trailingAnchor.constraint(equalTo: cell.trailingAnchor, constant: -6),
                textField.centerYAnchor.constraint(equalTo: cell.centerYAnchor),
            ])
        }
        return cell
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.activate(ignoringOtherApps: true)
app.run()
