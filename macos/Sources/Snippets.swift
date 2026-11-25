// Text snippets (TypeIt4Me-style): type an abbreviation anywhere → it's replaced by the snippet text.
// Snippets can also be inserted via their own hotkey, the menu bar or the picker.
import Cocoa
import Carbon.HIToolbox

struct Snippet: Codable, Identifiable, Equatable {
    var id = UUID()
    var abbreviation: String
    var text: String
    var hotkey: String?

    init(abbreviation: String, text: String, hotkey: String? = nil) {
        self.abbreviation = abbreviation; self.text = text; self.hotkey = hotkey
    }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decodeIfPresent(UUID.self, forKey: .id) ?? UUID()
        abbreviation = try c.decodeIfPresent(String.self, forKey: .abbreviation) ?? ""
        text = try c.decodeIfPresent(String.self, forKey: .text) ?? ""
        hotkey = try c.decodeIfPresent(String.self, forKey: .hotkey)
    }

    /// Short label for menus: abbreviation + first line of the text.
    var title: String {
        let first = text.split(separator: "\n", omittingEmptySubsequences: true).first.map(String.init) ?? ""
        let short = first.count > 40 ? first.prefix(40) + "…" : first
        return abbreviation.isEmpty ? String(short) : "\(abbreviation)  →  \(short)"
    }

    static var examples: [Snippet] { [
        Snippet(abbreviation: ";date", text: "{date}"),
        Snippet(abbreviation: ";br", text: L("Best regards,") + "\n"),
    ] }

    /// Resolves placeholders. Returns the text and how many characters the cursor should move back ({cursor}).
    static func resolve(_ s: String) -> (text: String, cursorBack: Int) {
        let loc = Locale(identifier: Lang.current == "de" ? "de_DE" : "en_US")
        func fmt(_ date: DateFormatter.Style, _ time: DateFormatter.Style) -> String {
            let f = DateFormatter(); f.locale = loc; f.dateStyle = date; f.timeStyle = time; return f.string(from: Date())
        }
        let iso = DateFormatter(); iso.dateFormat = "yyyy-MM-dd"
        var t = s
            .replacingOccurrences(of: "{date}", with: fmt(.medium, .none))
            .replacingOccurrences(of: "{time}", with: fmt(.none, .short))
            .replacingOccurrences(of: "{isodate}", with: iso.string(from: Date()))
        if t.contains("{clipboard}") {
            t = t.replacingOccurrences(of: "{clipboard}", with: NSPasteboard.general.string(forType: .string) ?? "")
        }
        var back = 0
        if let r = t.range(of: "{cursor}") {
            back = t[r.upperBound...].count
            t.removeSubrange(r)
        }
        return (t, back)
    }
}

/// Inserts text at the cursor of the frontmost app (via the clipboard, which is restored afterwards).
func insertSnippet(_ s: Snippet, target: NSRunningApplication? = nil) {
    let (text, back) = Snippet.resolve(s.text)
    paste(text, into: target, restoring: ClipboardSnapshot(), cursorBack: back)
}

/// Watches typing system-wide (needs Accessibility) and expands abbreviations.
final class TextExpander {
    static let shared = TextExpander()
    private var tap: CFMachPort?
    private var source: CFRunLoopSource?
    private var buffer = ""
    private var expanding = false
    private var observer: Any?

    var running: Bool { tap != nil }

    func update() {
        let wanted = store.cfg.featureSnippets && store.cfg.snippetsEnabled && store.cfg.snippets.contains { !$0.abbreviation.isEmpty }
        if wanted { start() } else { stop() }
    }

    private func start() {
        guard tap == nil else { return }
        let mask: CGEventMask = (1 << CGEventType.keyDown.rawValue) | (1 << CGEventType.leftMouseDown.rawValue)
                              | (1 << CGEventType.rightMouseDown.rawValue)
        tap = CGEvent.tapCreate(tap: .cgSessionEventTap, place: .headInsertEventTap, options: .defaultTap,
                                eventsOfInterest: mask, callback: { _, type, event, _ in
            TextExpander.shared.handle(type, event)
            return Unmanaged.passUnretained(event)
        }, userInfo: nil)
        guard let tap else {   // no Accessibility permission yet — try again later
            DispatchQueue.main.asyncAfter(deadline: .now() + 5) { self.update() }
            return
        }
        source = CFMachPortCreateRunLoopSource(nil, tap, 0)
        CFRunLoopAddSource(CFRunLoopGetMain(), source, .commonModes)
        CGEvent.tapEnable(tap: tap, enable: true)
        observer = NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.didActivateApplicationNotification, object: nil, queue: .main) { [weak self] _ in
            self?.buffer = ""
        }
    }

    private func stop() {
        if let tap { CGEvent.tapEnable(tap: tap, enable: false) }
        if let source { CFRunLoopRemoveSource(CFRunLoopGetMain(), source, .commonModes) }
        if let observer { NSWorkspace.shared.notificationCenter.removeObserver(observer) }
        tap = nil; source = nil; observer = nil; buffer = ""
    }

    private func handle(_ type: CGEventType, _ event: CGEvent) {
        if type == .tapDisabledByTimeout || type == .tapDisabledByUserInput {
            if let tap { CGEvent.tapEnable(tap: tap, enable: true) }
            return
        }
        guard type == .keyDown else { buffer = ""; return }   // mouse click: cursor probably moved
        if event.getIntegerValueField(.eventSourceUserData) == Keys.marker || expanding { return }
        // Don't expand inside LocalWriter itself (e.g. while typing an abbreviation in Settings).
        if NSWorkspace.shared.frontmostApplication?.processIdentifier == ProcessInfo.processInfo.processIdentifier {
            buffer = ""; return
        }
        let flags = event.flags
        if flags.contains(.maskCommand) || flags.contains(.maskControl) { buffer = ""; return }

        let code = Int(event.getIntegerValueField(.keyboardEventKeycode))
        switch code {
        case kVK_Delete: if !buffer.isEmpty { buffer.removeLast() }; return
        case kVK_Return, kVK_ANSI_KeypadEnter, kVK_Tab, kVK_Escape, kVK_ForwardDelete,
             kVK_LeftArrow, kVK_RightArrow, kVK_UpArrow, kVK_DownArrow,
             kVK_Home, kVK_End, kVK_PageUp, kVK_PageDown:
            buffer = ""; return
        default: break
        }
        var len = 0
        var chars = [UniChar](repeating: 0, count: 8)
        event.keyboardGetUnicodeString(maxStringLength: 8, actualStringLength: &len, unicodeString: &chars)
        guard len > 0 else { return }
        let typed = String(utf16CodeUnits: chars, count: len)

        if store.cfg.snippetTrigger == "delimiter", typed.count == 1, let ch = typed.first,
           ch.isWhitespace || ".,!?".contains(ch) {
            if let s = match(buffer) { expand(s, delete: s.abbreviation.count + 1, suffix: typed) }
            buffer = ""
            return
        }
        buffer += typed
        if buffer.count > 80 { buffer.removeFirst(buffer.count - 80) }
        if store.cfg.snippetTrigger != "delimiter", let s = match(buffer) {
            expand(s, delete: s.abbreviation.count, suffix: "")
            buffer = ""
        }
    }

    /// Longest abbreviation the buffer ends with. Abbreviations starting with a letter/digit only match at a word start.
    private func match(_ buf: String) -> Snippet? {
        store.cfg.snippets.filter { s in
            let a = s.abbreviation
            guard !a.isEmpty, buf.hasSuffix(a) else { return false }
            guard let first = a.first, first.isLetter || first.isNumber else { return true }
            guard let before = buf.dropLast(a.count).last else { return true }
            return !(before.isLetter || before.isNumber)
        }.max { $0.abbreviation.count < $1.abbreviation.count }
    }

    private func expand(_ s: Snippet, delete: Int, suffix: String) {
        expanding = true
        // Let the app receive the key that completed the abbreviation first.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.03) {
            for _ in 0..<delete { Keys.press(CGKeyCode(kVK_Delete), flags: []) }
            let (text, back) = Snippet.resolve(s.text)
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.03) {
                paste(text + suffix, into: nil, restoring: ClipboardSnapshot(), cursorBack: s.text.contains("{cursor}") ? back + suffix.count : 0)
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { self.expanding = false }
            }
        }
    }
}
