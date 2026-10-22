import AVFoundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
import AppKit

let args = CommandLine.arguments
let url = URL(fileURLWithPath: args[1])
let outDir = URL(fileURLWithPath: args[2])
try? FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)

let asset = AVURLAsset(url: url)
let sem = DispatchSemaphore(value: 0)
var duration = 0.0
var vTracks: [AVAssetTrack] = []
var aTracks: [AVAssetTrack] = []
Task {
    duration = (try? await asset.load(.duration).seconds) ?? 0
    vTracks = (try? await asset.loadTracks(withMediaType: .video)) ?? []
    aTracks = (try? await asset.loadTracks(withMediaType: .audio)) ?? []
    sem.signal()
}
sem.wait()
print("duration:", duration)
for t in vTracks {
    let s2 = DispatchSemaphore(value: 0)
    Task {
        let size = try? await t.load(.naturalSize)
        let fps = try? await t.load(.nominalFrameRate)
        print("video:", size ?? .zero, "fps:", fps ?? 0)
        s2.signal()
    }
    s2.wait()
}
print("audio tracks:", aTracks.count)

// frames
let gen = AVAssetImageGenerator(asset: asset)
gen.appliesPreferredTrackTransform = true
gen.requestedTimeToleranceBefore = .zero
gen.requestedTimeToleranceAfter = .zero
gen.maximumSize = CGSize(width: 640, height: 640)
var times: [Double] = []
var t = 0.3
while t < duration { times.append(t); t += 0.9 }
var frames: [(Double, CGImage)] = []
for tm in times {
    if let img = try? gen.copyCGImage(at: CMTime(seconds: tm, preferredTimescale: 600), actualTime: nil) {
        frames.append((tm, img))
    }
}
// contact sheet
if let first = frames.first?.1 {
    let w = first.width, h = first.height
    let cols = 4
    let rows = (frames.count + cols - 1) / cols
    let ctx = CGContext(data: nil, width: w * cols, height: h * rows, bitsPerComponent: 8, bytesPerRow: 0,
                        space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    ctx.setFillColor(CGColor(red: 0, green: 0, blue: 0, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: w * cols, height: h * rows))
    let nsctx = NSGraphicsContext(cgContext: ctx, flipped: false)
    NSGraphicsContext.current = nsctx
    for (i, (tm, img)) in frames.enumerated() {
        let c = i % cols, r = i / cols
        let x = c * w, y = (rows - 1 - r) * h
        ctx.draw(img, in: CGRect(x: x, y: y, width: w, height: h))
        let label = String(format: "%.1fs", tm) as NSString
        label.draw(at: CGPoint(x: x + 8, y: y + h - 30),
                   withAttributes: [.font: NSFont.boldSystemFont(ofSize: 22), .foregroundColor: NSColor.yellow,
                                    .backgroundColor: NSColor.black.withAlphaComponent(0.6)])
    }
    let out = outDir.appendingPathComponent("sheet.jpg")
    let dest = CGImageDestinationCreateWithURL(out as CFURL, UTType.jpeg.identifier as CFString, 1, nil)!
    CGImageDestinationAddImage(dest, ctx.makeImage()!, [kCGImageDestinationLossyCompressionQuality: 0.85] as CFDictionary)
    CGImageDestinationFinalize(dest)
    print("sheet:", out.path, "frames:", frames.count, "cell:", w, "x", h)
}
// full-res key frames for close inspection
let gen2 = AVAssetImageGenerator(asset: asset)
gen2.appliesPreferredTrackTransform = true
gen2.requestedTimeToleranceBefore = .zero
gen2.requestedTimeToleranceAfter = .zero
for tm in args.dropFirst(3).compactMap(Double.init) {
    if let img = try? gen2.copyCGImage(at: CMTime(seconds: tm, preferredTimescale: 600), actualTime: nil) {
        let out = outDir.appendingPathComponent(String(format: "full_%.1f.jpg", tm))
        let dest = CGImageDestinationCreateWithURL(out as CFURL, UTType.jpeg.identifier as CFString, 1, nil)!
        CGImageDestinationAddImage(dest, img, [kCGImageDestinationLossyCompressionQuality: 0.85] as CFDictionary)
        CGImageDestinationFinalize(dest)
        print("full:", out.path)
    }
}

// audio loudness timeline
if let at = aTracks.first, let reader = try? AVAssetReader(asset: asset) {
    let settings: [String: Any] = [AVFormatIDKey: kAudioFormatLinearPCM, AVLinearPCMBitDepthKey: 16,
                                   AVLinearPCMIsFloatKey: false, AVLinearPCMIsBigEndianKey: false,
                                   AVNumberOfChannelsKey: 1, AVSampleRateKey: 16000]
    let output = AVAssetReaderTrackOutput(track: at, outputSettings: settings)
    reader.add(output)
    reader.startReading()
    var samples: [Int16] = []
    while let sb = output.copyNextSampleBuffer(), let bb = CMSampleBufferGetDataBuffer(sb) {
        let len = CMBlockBufferGetDataLength(bb)
        var data = [Int16](repeating: 0, count: len / 2)
        data.withUnsafeMutableBytes { _ = CMBlockBufferCopyDataBytes(bb, atOffset: 0, dataLength: len, destination: $0.baseAddress!) }
        samples.append(contentsOf: data)
    }
    let win = 16000 / 4
    print("audio loudness (0.25s windows, dBFS):")
    var i = 0
    while i < samples.count {
        let chunk = samples[i..<min(i + win, samples.count)]
        let rms = sqrt(chunk.reduce(0.0) { $0 + Double($1) * Double($1) } / Double(chunk.count))
        let db = rms > 0 ? 20 * log10(rms / 32768) : -99
        let bars = String(repeating: "#", count: max(0, Int((db + 60) / 2)))
        print(String(format: "%5.2fs %6.1f %@", Double(i) / 16000, db, bars))
        i += win
    }
}
