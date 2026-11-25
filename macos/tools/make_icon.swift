// Renders Resources/AppIcon.icns. Run: swift tools/make_icon.swift
import AppKit

func render(_ size: CGFloat) -> NSBitmapImageRep {
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(size), pixelsHigh: Int(size), bitsPerSample: 8,
                               samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    let s = size / 1024
    let rect = NSRect(x: 100 * s, y: 100 * s, width: 824 * s, height: 824 * s)   // macOS icon grid
    let shape = NSBezierPath(roundedRect: rect, xRadius: 185 * s, yRadius: 185 * s)
    let shadow = NSShadow(); shadow.shadowBlurRadius = 20 * s; shadow.shadowOffset = NSSize(width: 0, height: -8 * s)
    shadow.shadowColor = NSColor.black.withAlphaComponent(0.3); shadow.set()
    NSGradient(colors: [NSColor(red: 0.36, green: 0.30, blue: 0.95, alpha: 1), NSColor(red: 0.12, green: 0.62, blue: 0.95, alpha: 1)])!
        .draw(in: shape, angle: -60)
    NSShadow().set()
    // "page" lines
    NSColor.white.withAlphaComponent(0.9).setFill()
    for (i, w) in [520.0, 440, 480, 300].enumerated() {
        NSBezierPath(roundedRect: NSRect(x: 230 * s, y: (690 - Double(i) * 105) * s, width: w * s, height: 44 * s),
                     xRadius: 22 * s, yRadius: 22 * s).fill()
    }
    // pen glyph
    let cfg = NSImage.SymbolConfiguration(pointSize: 330 * s, weight: .semibold)
    if let pen = NSImage(systemSymbolName: "pencil", accessibilityDescription: nil)?.withSymbolConfiguration(cfg) {
        let tinted = NSImage(size: pen.size, flipped: false) { r in
            pen.draw(in: r); NSColor.white.set(); r.fill(using: .sourceAtop); return true
        }
        tinted.draw(in: NSRect(x: 520 * s, y: 170 * s, width: pen.size.width, height: pen.size.height))
    }
    NSGraphicsContext.restoreGraphicsState()
    return rep
}

let set = URL(fileURLWithPath: "Resources/AppIcon.iconset")
try? FileManager.default.createDirectory(at: set, withIntermediateDirectories: true)
for base in [16, 32, 128, 256, 512] {
    for scale in [1, 2] {
        let px = CGFloat(base * scale)
        let name = "icon_\(base)x\(base)\(scale == 2 ? "@2x" : "").png"
        try! render(px).representation(using: .png, properties: [:])!.write(to: set.appendingPathComponent(name))
    }
}
