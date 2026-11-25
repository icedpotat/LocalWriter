// File comparison: metadata extraction + Myers line diff.
import AppKit
import CryptoKit
import PDFKit
import UniformTypeIdentifiers

// MARK: - File info

struct FileInfo {
    let url: URL
    var size: Int64 = 0
    var created: Date?
    var modified: Date?
    var kind = ""
    var permissions = ""
    var sha256 = ""
    var text: String?            // nil = binary / unreadable
    var lines: [String] { text.map { $0.components(separatedBy: .newlines) } ?? [] }
    var wordCount: Int { text.map { $0.split { $0.isWhitespace || $0.isNewline }.count } ?? 0 }

    /// Must run on the main thread (rich-text/HTML import uses WebKit).
    static func load(_ url: URL) -> FileInfo {
        var f = FileInfo(url: url)
        let fm = FileManager.default
        if let a = try? fm.attributesOfItem(atPath: url.path) {
            f.size = (a[.size] as? NSNumber)?.int64Value ?? 0
            f.created = a[.creationDate] as? Date
            f.modified = a[.modificationDate] as? Date
            if let p = (a[.posixPermissions] as? NSNumber)?.intValue { f.permissions = posixString(p) }
        }
        f.kind = (try? url.resourceValues(forKeys: [.localizedTypeDescriptionKey]))?.localizedTypeDescription ?? url.pathExtension
        if let data = try? Data(contentsOf: url, options: .alwaysMapped) {
            f.sha256 = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
            f.text = extractText(url: url, data: data)
        }
        return f
    }

    static func extractText(url: URL, data: Data) -> String? {
        let ext = url.pathExtension.lowercased()
        if ext == "pdf" { return PDFDocument(url: url)?.string }
        if ["rtf", "rtfd", "doc", "docx", "odt", "html", "htm", "webarchive"].contains(ext) {
            return try? NSAttributedString(url: url, options: [:], documentAttributes: nil).string
        }
        if data.prefix(8000).contains(0) {   // NUL byte → probably binary, unless UTF-16 with BOM
            if data.starts(with: [0xFF, 0xFE]) || data.starts(with: [0xFE, 0xFF]) { return String(data: data, encoding: .utf16) }
            return nil
        }
        return String(data: data, encoding: .utf8) ?? String(data: data, encoding: .isoLatin1)
    }

    static func posixString(_ p: Int) -> String {
        let chars = Array("rwxrwxrwx")
        return String((0..<9).map { p & (1 << (8 - $0)) != 0 ? chars[$0] : "-" }) + String(format: "  (%o)", p)
    }
}

// MARK: - Diff

enum DiffOp { case equal(Int, Int), delete(Int), insert(Int) }

/// Myers O((N+M)·D) diff over integer-encoded lines. Returns nil if there are more than maxD differences.
func myersDiff(_ a: [Int], _ b: [Int], maxD: Int = 3000) -> [DiffOp]? {
    let n = a.count, m = b.count, mx = n + m
    if mx == 0 { return [] }
    let off = mx + 1
    var v = [Int](repeating: 0, count: 2 * mx + 3)
    var trace: [[Int]] = []   // trace[d] = v[-d...d] before round d
    for d in 0...mx {
        if d > maxD { return nil }
        trace.append(Array(v[(off - d)...(off + d)]))
        var k = -d
        while k <= d {
            var x = (k == -d || (k != d && v[off + k - 1] < v[off + k + 1])) ? v[off + k + 1] : v[off + k - 1] + 1
            var y = x - k
            while x < n && y < m && a[x] == b[y] { x += 1; y += 1 }
            v[off + k] = x
            if x >= n && y >= m { return backtrack(trace, n, m) }
            k += 2
        }
    }
    return nil
}

private func backtrack(_ trace: [[Int]], _ n: Int, _ m: Int) -> [DiffOp] {
    var ops: [DiffOp] = []
    var x = n, y = m
    for d in stride(from: trace.count - 1, through: 0, by: -1) {
        if d == 0 { while x > 0 && y > 0 { x -= 1; y -= 1; ops.append(.equal(x, y)) }; break }
        let vv = trace[d]
        let k = x - y
        let prevK = (k == -d || (k != d && vv[k - 1 + d] < vv[k + 1 + d])) ? k + 1 : k - 1
        let prevX = vv[prevK + d], prevY = prevX - prevK
        while x > prevX && y > prevY { x -= 1; y -= 1; ops.append(.equal(x, y)) }
        if x == prevX { y -= 1; ops.append(.insert(y)) } else { x -= 1; ops.append(.delete(x)) }
    }
    return ops.reversed()
}

struct DiffRow: Identifiable {
    enum Kind { case same, changed, removed, added }
    let id: Int
    let leftNo: Int?, left: String?
    let rightNo: Int?, right: String?
    let kind: Kind
}

struct DiffResult {
    var rows: [DiffRow] = []
    var added = 0, removed = 0, changed = 0, same = 0
    var truncated = false     // too many differences for an exact diff
    var similarity: Double { let t = rows.count; return t == 0 ? 1 : Double(same) / Double(t) }

    /// "- old / + new" text of the changes, for the AI summary.
    func unified(limit: Int = 12000) -> String {
        var s = ""
        for r in rows where r.kind != .same {
            if let l = r.left { s += "- \(l)\n" }
            if let rr = r.right { s += "+ \(rr)\n" }
            if s.count > limit { s += "…\n"; break }
        }
        return s
    }
}

func computeDiff(_ left: [String], _ right: [String]) -> DiffResult {
    // Encode lines as ints (identical lines share an id) so comparisons are cheap.
    var ids: [String: Int] = [:]
    func encode(_ l: String) -> Int {
        if let i = ids[l] { return i }
        let i = ids.count; ids[l] = i; return i
    }
    let a = left.map(encode), b = right.map(encode)

    var res = DiffResult()
    let ops = myersDiff(a, b) ?? {
        res.truncated = true
        return left.indices.map { DiffOp.delete($0) } + right.indices.map { DiffOp.insert($0) }
    }()

    var dels: [Int] = [], ins: [Int] = []
    func flush() {
        for i in 0..<max(dels.count, ins.count) {
            let l = i < dels.count ? dels[i] : nil, r = i < ins.count ? ins[i] : nil
            let kind: DiffRow.Kind = (l != nil && r != nil) ? .changed : (l != nil ? .removed : .added)
            switch kind { case .changed: res.changed += 1; case .removed: res.removed += 1; default: res.added += 1 }
            res.rows.append(DiffRow(id: res.rows.count, leftNo: l.map { $0 + 1 }, left: l.map { left[$0] },
                                    rightNo: r.map { $0 + 1 }, right: r.map { right[$0] }, kind: kind))
        }
        dels.removeAll(); ins.removeAll()
    }
    for op in ops {
        switch op {
        case .delete(let i): dels.append(i)
        case .insert(let j): ins.append(j)
        case .equal(let i, let j):
            flush()
            res.same += 1
            res.rows.append(DiffRow(id: res.rows.count, leftNo: i + 1, left: left[i], rightNo: j + 1, right: right[j], kind: .same))
        }
    }
    flush()
    return res
}
