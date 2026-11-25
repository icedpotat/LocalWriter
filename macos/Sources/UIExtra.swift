// Settings tabs: Snippets (text expansion) and Vault (Touch ID–protected secrets)
import SwiftUI
import AppKit

// MARK: - Snippets

struct SnippetsTab: View {
    @EnvironmentObject var store: Store

    /// Abbreviations used twice, or (in immediate mode) that are a prefix of another — the shorter one would always win.
    var abbreviationIssues: [String] {
        let abbrs = store.cfg.snippets.map(\.abbreviation).filter { !$0.isEmpty }
        var out: [String] = []
        let dups = Dictionary(grouping: abbrs, by: { $0 }).filter { $0.value.count > 1 }.keys.sorted()
        if !dups.isEmpty { out.append(L("Used more than once: ") + dups.joined(separator: ", ")) }
        if store.cfg.snippetTrigger != "delimiter" {
            for a in Set(abbrs) { for b in Set(abbrs) where a != b && b.hasPrefix(a) {
                out.append(String(format: L("“%@” expands before you can finish typing “%@”."), a, b))
            } }
        }
        return out
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                GroupBox {
                    VStack(alignment: .leading, spacing: 8) {
                        Toggle(L("Expand abbreviations while typing"), isOn: $store.cfg.snippetsEnabled)
                        Picker(L("When"), selection: $store.cfg.snippetTrigger) {
                            Text(L("Immediately")).tag("immediate")
                            Text(L("After space or punctuation")).tag("delimiter")
                        }.pickerStyle(.segmented).frame(maxWidth: 420).disabled(!store.cfg.snippetsEnabled)
                        Text(L("Placeholders: {date} {time} {isodate} {clipboard} {cursor} (cursor ends up there)"))
                            .font(.caption).foregroundColor(.secondary).textSelection(.enabled)
                        Text(L("Tip: start abbreviations with a character you rarely type, like ; or //."))
                            .font(.caption).foregroundColor(.secondary)
                        if !AXIsProcessTrusted() {
                            Label(L("Needs Accessibility access (see General)."), systemImage: "exclamationmark.triangle.fill")
                                .foregroundColor(.orange).font(.callout)
                        }
                    }.padding(4).frame(maxWidth: .infinity, alignment: .leading)
                }
                ForEach(abbreviationIssues, id: \.self) {
                    Label($0, systemImage: "exclamationmark.triangle.fill").foregroundColor(.orange).font(.callout)
                }
                HStack {
                    Text(L("Your snippets")).font(.title3.bold())
                    Spacer()
                    Button { store.cfg.snippets.append(Snippet(abbreviation: "", text: "")) } label: {
                        Label(L("New snippet"), systemImage: "plus")
                    }
                }
                if store.cfg.snippets.isEmpty {
                    Text(L("No snippets yet.")).foregroundColor(.secondary)
                } else {
                    VStack(spacing: 0) {
                        ForEach(store.cfg.snippets) { s in
                            SnippetRow(id: s.id, conflict: store.isProblem(s.hotkey))
                            Divider()
                        }
                    }
                    .background(RoundedRectangle(cornerRadius: 8).fill(Color(nsColor: .controlBackgroundColor)))
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.secondary.opacity(0.2)))
                }
            }
            .padding(14)
        }
    }
}

struct SnippetRow: View {
    @EnvironmentObject var store: Store
    let id: UUID
    var conflict: Bool

    var snippet: Binding<Snippet> {
        Binding(get: { store.cfg.snippets.first { $0.id == id } ?? Snippet(abbreviation: "", text: "") },
                set: { nv in if let i = store.cfg.snippets.firstIndex(where: { $0.id == id }) { store.cfg.snippets[i] = nv } })
    }

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            TextField(L("Abbreviation"), text: snippet.abbreviation)
                .font(.system(.body, design: .monospaced)).frame(width: 120)
            TextEditor(text: snippet.text)
                .font(.system(size: 12))
                .frame(minHeight: 44, maxHeight: 120)
                .overlay(RoundedRectangle(cornerRadius: 4).stroke(Color.secondary.opacity(0.3)))
            VStack(alignment: .trailing, spacing: 6) {
                HotkeyRecorder(combo: snippet.hotkey, conflict: conflict)
                Button(role: .destructive) { store.cfg.snippets.removeAll { $0.id == id } } label: {
                    Image(systemName: "trash")
                }.buttonStyle(.borderless).help(L("Delete"))
            }
        }
        .padding(.horizontal, 10).padding(.vertical, 8)
    }
}

// MARK: - Vault

final class VaultModel: ObservableObject {
    @Published var unlocked = false
    @Published var secrets: [String: String] = [:]
    @Published var revealed: Set<UUID> = []

    func unlock() {
        // Editing needs its own authentication; it stays open until the tab is left or locked.
        Vault.shared.authenticate(reason: L("show and edit the vault"), keepUnlocked: 0) { ok in
            guard ok else { return }
            self.secrets = Keychain.load(); self.unlocked = true
        }
    }
    func lock() { unlocked = false; secrets = [:]; revealed = []; Vault.shared.lock() }
    func set(_ id: UUID, _ v: String) { secrets[id.uuidString] = v; Keychain.save(secrets) }
    func remove(_ id: UUID) { secrets[id.uuidString] = nil; Keychain.save(secrets) }
}

struct VaultTab: View {
    @EnvironmentObject var store: Store
    @StateObject private var vm = VaultModel()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                GroupBox {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(L("Vault picker")).font(.headline)
                                Text(L("Lists your vault entries at the mouse pointer.")).font(.caption).foregroundColor(.secondary)
                            }
                            Spacer()
                            HotkeyRecorder(combo: Binding(get: { store.cfg.vaultHotkey.isEmpty ? nil : store.cfg.vaultHotkey },
                                                          set: { store.cfg.vaultHotkey = $0 ?? "" }),
                                           conflict: store.isProblem(store.cfg.vaultHotkey))
                        }
                        HStack {
                            Text(L("Time to authenticate"))
                            Slider(value: $store.cfg.vaultAuthTimeout, in: 5...60, step: 5)
                            Text("\(Int(store.cfg.vaultAuthTimeout)) s").monospacedDigit().frame(width: 44)
                        }
                        HStack {
                            Text(L("Stay unlocked after use"))
                            Slider(value: $store.cfg.vaultUnlockFor, in: 0...300, step: 15)
                            Text(store.cfg.vaultUnlockFor == 0 ? L("never") : "\(Int(store.cfg.vaultUnlockFor)) s")
                                .monospacedDigit().frame(width: 52)
                        }
                        Picker(L("Insert by"), selection: $store.cfg.vaultMethod) {
                            Text(L("Pasting (hidden from clipboard managers)")).tag("paste")
                            Text(L("Typing (for fields that block pasting)")).tag("type")
                        }
                        Text(L("Secrets are stored in your login Keychain, never in the config file. Every use asks for Touch ID or your Mac password."))
                            .font(.caption).foregroundColor(.secondary)
                    }.padding(4)
                }

                HStack {
                    Text(L("Entries")).font(.title3.bold())
                    Spacer()
                    if vm.unlocked {
                        Button { store.cfg.vault.append(VaultEntry(name: L("New entry"))) } label: {
                            Label(L("New entry"), systemImage: "plus")
                        }
                        Button { vm.lock() } label: { Label(L("Lock"), systemImage: "lock") }
                    }
                }

                if !vm.unlocked {
                    VStack(spacing: 10) {
                        Image(systemName: "lock.fill").font(.system(size: 34)).foregroundColor(.secondary)
                        Text(String(format: L("%d entries"), store.cfg.vault.count)).foregroundColor(.secondary)
                        Button { vm.unlock() } label: { Label(L("Unlock to view and edit"), systemImage: "touchid") }
                            .controlSize(.large)
                    }.frame(maxWidth: .infinity).padding(30)
                } else if store.cfg.vault.isEmpty {
                    Text(L("No entries yet.")).foregroundColor(.secondary)
                } else {
                    VStack(spacing: 0) {
                        ForEach(store.cfg.vault) { e in
                            VaultRow(id: e.id, vm: vm, conflict: store.isProblem(e.hotkey))
                            Divider()
                        }
                    }
                    .background(RoundedRectangle(cornerRadius: 8).fill(Color(nsColor: .controlBackgroundColor)))
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.secondary.opacity(0.2)))
                }
            }
            .padding(14)
        }
        .onDisappear { vm.lock() }
    }
}

struct VaultRow: View {
    @EnvironmentObject var store: Store
    let id: UUID
    @ObservedObject var vm: VaultModel
    var conflict: Bool

    var entry: Binding<VaultEntry> {
        Binding(get: { store.cfg.vault.first { $0.id == id } ?? VaultEntry(name: "") },
                set: { nv in if let i = store.cfg.vault.firstIndex(where: { $0.id == id }) { store.cfg.vault[i] = nv } })
    }
    var secret: Binding<String> {
        Binding(get: { vm.secrets[id.uuidString] ?? "" }, set: { vm.set(id, $0) })
    }

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "key").foregroundColor(.secondary)
            TextField(L("Name"), text: entry.name).frame(width: 160)
            Group {
                if vm.revealed.contains(id) { TextField(L("Secret"), text: secret) }
                else { SecureField(L("Secret"), text: secret) }
            }.font(.system(.body, design: .monospaced))
            Button { if vm.revealed.contains(id) { vm.revealed.remove(id) } else { vm.revealed.insert(id) } } label: {
                Image(systemName: vm.revealed.contains(id) ? "eye.slash" : "eye")
            }.buttonStyle(.borderless).help(L("Show/hide"))
            HotkeyRecorder(combo: entry.hotkey, conflict: conflict)
            Button(role: .destructive) {
                vm.remove(id); store.cfg.vault.removeAll { $0.id == id }
            } label: { Image(systemName: "trash") }.buttonStyle(.borderless).help(L("Delete"))
        }
        .padding(.horizontal, 10).padding(.vertical, 7)
    }
}
