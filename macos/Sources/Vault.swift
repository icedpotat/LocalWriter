// Vault: secrets (passwords etc.) kept in the macOS Keychain. Pasting one needs Touch ID or the Mac password.
// The config file only stores names and hotkeys — never the secret values.
import Cocoa
import LocalAuthentication
import Security

struct VaultEntry: Codable, Identifiable, Equatable {
    var id = UUID()
    var name: String
    var hotkey: String?

    init(name: String, hotkey: String? = nil) { self.name = name; self.hotkey = hotkey }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decodeIfPresent(UUID.self, forKey: .id) ?? UUID()
        name = try c.decodeIfPresent(String.self, forKey: .name) ?? ""
        hotkey = try c.decodeIfPresent(String.self, forKey: .hotkey)
    }
}

/// All secrets live in one generic-password item as JSON {entryID: secret}.
enum Keychain {
    static let base: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                      kSecAttrService as String: "local.localwriter.vault",
                                      kSecAttrAccount as String: "vault"]

    static func load() -> [String: String] {
        var q = base
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var out: AnyObject?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let data = out as? Data,
              let dict = try? JSONDecoder().decode([String: String].self, from: data) else { return [:] }
        return dict
    }

    @discardableResult
    static func save(_ dict: [String: String]) -> Bool {
        guard let data = try? JSONEncoder().encode(dict) else { return false }
        let status = SecItemUpdate(base as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            var q = base; q[kSecValueData as String] = data
            q[kSecAttrLabel as String] = "LocalWriter vault"
            return SecItemAdd(q as CFDictionary, nil) == errSecSuccess
        }
        return status == errSecSuccess
    }
}

final class Vault {
    static let shared = Vault()
    private var unlockedUntil = Date.distantPast
    private var authenticating = false

    var isUnlocked: Bool { Date() < unlockedUntil }
    func lock() { unlockedUntil = .distantPast }

    /// Touch ID / password. Fails if not completed within `vaultAuthTimeout` seconds.
    /// After success the vault stays unlocked for `vaultUnlockFor` seconds (0 = ask every time).
    func authenticate(reason: String, keepUnlocked: Double? = nil, completion: @escaping (Bool) -> Void) {
        if isUnlocked { completion(true); return }
        guard !authenticating else { NSSound.beep(); completion(false); return }
        let ctx = LAContext()
        var err: NSError?
        guard ctx.canEvaluatePolicy(.deviceOwnerAuthentication, error: &err) else {
            notify(L("Vault"), err?.localizedDescription ?? L("Authentication is not available."))
            completion(false); return
        }
        authenticating = true
        var done = false
        let finish: (Bool) -> Void = { ok in
            guard !done else { return }
            done = true; self.authenticating = false
            if ok { self.unlockedUntil = Date().addingTimeInterval(keepUnlocked ?? store.cfg.vaultUnlockFor) }
            completion(ok)
        }
        let timeout = store.cfg.vaultAuthTimeout
        if timeout > 0 {
            DispatchQueue.main.asyncAfter(deadline: .now() + timeout) {
                if !done { ctx.invalidate(); finish(false); notify(L("Vault"), L("Authentication timed out.")) }
            }
        }
        ctx.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: reason) { ok, _ in
            DispatchQueue.main.async { finish(ok) }
        }
    }

    /// Asks for Touch ID/password, then pastes (or types) the secret into `target`.
    func insert(_ id: UUID, target: NSRunningApplication?) {
        // If triggered from our own menu/picker, LocalWriter may be frontmost — never paste into ourselves.
        let target = target?.processIdentifier == ProcessInfo.processInfo.processIdentifier ? nil : target
        guard let entry = store.cfg.vault.first(where: { $0.id == id }) else { return }
        waitForModifiersReleased {
            self.authenticate(reason: String(format: L("insert “%@”"), entry.name)) { ok in
                guard ok else { bringToFront(target); return }
                guard let secret = Keychain.load()[id.uuidString], !secret.isEmpty else {
                    notify(L("Vault"), L("This entry has no value yet.")); return
                }
                // Hand focus back to the app (and its text field) the hotkey was pressed in, then wait until it is frontmost.
                NSApp.hide(nil)
                bringToFront(target)
                waitUntilFrontmost(target) {
                    if store.cfg.vaultMethod == "type" { typeText(secret) }
                    else { paste(secret, into: nil, restoring: ClipboardSnapshot(), concealed: true) }
                }
            }
        }
    }
}

func waitUntilFrontmost(_ app: NSRunningApplication?, tries: Int = 0, _ then: @escaping () -> Void) {
    let front = NSWorkspace.shared.frontmostApplication?.processIdentifier
    if app == nil || front == app?.processIdentifier || tries > 40 {
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15, execute: then)   // let the window regain key focus
        return
    }
    if tries % 10 == 9 { bringToFront(app) }
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) { waitUntilFrontmost(app, tries: tries + 1, then) }
}

/// Types text via synthesized keyboard events — works in fields that block pasting.
func typeText(_ s: String) {
    let src = CGEventSource(stateID: .combinedSessionState)
    for ch in s {
        var units = Array(String(ch).utf16)
        for down in [true, false] {
            let e = CGEvent(keyboardEventSource: src, virtualKey: 0, keyDown: down)
            e?.flags = []
            e?.setIntegerValueField(.eventSourceUserData, value: Keys.marker)
            e?.keyboardSetUnicodeString(stringLength: units.count, unicodeString: &units)
            e?.post(tap: .cghidEventTap)
        }
        usleep(4000)
    }
}
