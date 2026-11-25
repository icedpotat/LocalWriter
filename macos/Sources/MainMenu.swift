// Main menu bar, shown while the Settings window is open (the app is then a regular app with a Dock icon).
import Cocoa

final class MainMenu: NSObject {
    static let shared = MainMenu()

    static func build() { shared.build() }

    private func build() {
        let main = NSMenu()

        // App menu
        let app = NSMenu()
        app.addItem(item(L("About LocalWriter"), #selector(about)))
        app.addItem(.separator())
        app.addItem(item(L("Settings…"), #selector(settings), ","))
        app.addItem(.separator())
        app.addItem(withTitle: L("Hide LocalWriter"), action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        let others = app.addItem(withTitle: L("Hide Others"), action: #selector(NSApplication.hideOtherApplications(_:)), keyEquivalent: "h")
        others.keyEquivalentModifierMask = [.command, .option]
        app.addItem(withTitle: L("Show All"), action: #selector(NSApplication.unhideAllApplications(_:)), keyEquivalent: "")
        app.addItem(.separator())
        app.addItem(item(L("Quit LocalWriter"), #selector(quit), "q"))
        add(main, "LocalWriter", app)

        // Edit — also makes ⌘C/⌘V/⌘A/⌘Z work in text fields
        let edit = NSMenu(title: L("Edit"))
        edit.addItem(withTitle: L("Undo"), action: Selector(("undo:")), keyEquivalent: "z")
        edit.addItem(withTitle: L("Redo"), action: Selector(("redo:")), keyEquivalent: "Z")
        edit.addItem(.separator())
        edit.addItem(withTitle: L("Cut"), action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: L("Copy"), action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: L("Paste"), action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        let pms = edit.addItem(withTitle: L("Paste and Match Style"), action: #selector(NSTextView.pasteAsPlainText(_:)), keyEquivalent: "v")
        pms.keyEquivalentModifierMask = [.command, .option, .shift]
        edit.addItem(withTitle: L("Delete"), action: #selector(NSText.delete(_:)), keyEquivalent: "")
        edit.addItem(withTitle: L("Select All"), action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        add(main, L("Edit"), edit)

        // View — jump to settings tabs with ⌘1…
        let view = NSMenu(title: L("View"))
        let c = store.cfg
        var tabs: [(String, SettingsTab)] = [(L("General"), .general), (L("Appearance"), .appearance)]
        if c.featureAI { tabs.append((L("Shortcuts"), .shortcuts)) }
        if c.featureSnippets { tabs.append((L("Snippets"), .snippets)) }
        if c.featureVault { tabs.append((L("Vault"), .vault)) }
        if c.featureCompare { tabs.append((L("Compare"), .compare)) }
        for (i, t) in tabs.enumerated() {
            let it = item(t.0, #selector(showTab(_:)), i < 9 ? "\(i + 1)" : "")
            it.representedObject = t.1; view.addItem(it)
        }
        add(main, L("View"), view)

        // Tools
        let tools = NSMenu(title: L("Tools"))
        tools.addItem(item(L("Edit config file…"), #selector(openConfig)))
        tools.addItem(item(L("Show config folder in Finder"), #selector(revealConfig)))
        tools.addItem(item(L("Reload config"), #selector(reloadConfig), "r"))
        if c.featureVault {
            tools.addItem(.separator())
            tools.addItem(item(L("Lock vault now"), #selector(lockVault), "l"))
        }
        if c.featureAI {
            tools.addItem(.separator())
            tools.addItem(item(L("Open Ollama model library"), #selector(ollamaLibrary)))
        }
        add(main, L("Tools"), tools)

        // Window
        let window = NSMenu(title: L("Window"))
        window.addItem(withTitle: L("Minimize"), action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        window.addItem(withTitle: L("Zoom"), action: #selector(NSWindow.performZoom(_:)), keyEquivalent: "")
        window.addItem(withTitle: L("Close"), action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        window.addItem(.separator())
        window.addItem(withTitle: L("Bring All to Front"), action: #selector(NSApplication.arrangeInFront(_:)), keyEquivalent: "")
        add(main, L("Window"), window)
        NSApp.windowsMenu = window

        // Help
        let help = NSMenu(title: L("Help"))
        help.addItem(item(L("Grant Accessibility access…"), #selector(openAccessibility)))
        help.addItem(.separator())
        help.addItem(item("☕ " + L("Support LocalWriter on Ko-fi"), #selector(kofi)))
        help.addItem(item(L("Website"), #selector(website)))
        add(main, L("Help"), help)
        NSApp.helpMenu = help

        NSApp.mainMenu = main
    }

    private func add(_ main: NSMenu, _ title: String, _ sub: NSMenu) {
        let it = NSMenuItem(title: title, action: nil, keyEquivalent: ""); sub.title = title; it.submenu = sub; main.addItem(it)
    }
    private func item(_ t: String, _ s: Selector, _ key: String = "") -> NSMenuItem {
        let i = NSMenuItem(title: t, action: s, keyEquivalent: key); i.target = self; return i
    }

    @objc func about() { NSApp.activate(ignoringOtherApps: true); NSApp.orderFrontStandardAboutPanel(nil) }
    @objc func settings() { SettingsWindow.show(store.tab) }
    @objc func quit() { NSApp.terminate(nil) }
    @objc func kofi() { NSWorkspace.shared.open(Links.kofi) }
    @objc func website() { NSWorkspace.shared.open(Links.website) }
    @objc func showTab(_ s: NSMenuItem) { if let t = s.representedObject as? SettingsTab { SettingsWindow.show(t) } }
    @objc func openConfig() { NSWorkspace.shared.open(Config.file) }
    @objc func revealConfig() { NSWorkspace.shared.activateFileViewerSelecting([Config.file]) }
    @objc func reloadConfig() { store.cfg = Config.load() }
    @objc func lockVault() { Vault.shared.lock(); notify(L("Vault"), L("Vault locked.")) }
    @objc func ollamaLibrary() { NSWorkspace.shared.open(URL(string: "https://ollama.com/library")!) }
    @objc func openAccessibility() {
        NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")!)
    }
}
