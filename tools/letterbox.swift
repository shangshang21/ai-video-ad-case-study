import AVFoundation
import CoreImage

// usage: letterbox <src> <dst> <cropBottomPx>
// Drops the bottom strip (where burned-in subtitles sit), re-centres the rest, and fills black bars.
let src = URL(fileURLWithPath: CommandLine.arguments[1])
let dst = URL(fileURLWithPath: CommandLine.arguments[2])
let cropBottom = CGFloat(Double(CommandLine.arguments[3]) ?? 110)
try? FileManager.default.removeItem(at: dst)

let asset = AVURLAsset(url: src)
let comp = AVMutableVideoComposition(asset: asset) { req in
    let img = req.sourceImage
    let ext = img.extent
    let visibleH = ext.height - cropBottom
    let bar = cropBottom / 2
    let visible = img
        .cropped(to: CGRect(x: ext.minX, y: ext.minY + cropBottom, width: ext.width, height: visibleH))
        .transformed(by: CGAffineTransform(translationX: 0, y: -(cropBottom - bar)))
    let black = CIImage(color: .black).cropped(to: ext)
    req.finish(with: visible.composited(over: black), context: nil)
}
let exp = AVAssetExportSession(asset: asset, presetName: AVAssetExportPresetHighestQuality)!
exp.videoComposition = comp
exp.outputURL = dst
exp.outputFileType = .mp4
let sem = DispatchSemaphore(value: 0)
exp.exportAsynchronously { sem.signal() }
sem.wait()
print("status:", exp.status.rawValue, exp.error.map { "\($0)" } ?? "ok")
