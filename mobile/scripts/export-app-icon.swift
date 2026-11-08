import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

// Export the site's existing mascot into an opaque app icon without changing the artwork.
let root = URL(fileURLWithPath: CommandLine.arguments.dropFirst().first ?? FileManager.default.currentDirectoryPath)
let source = root.appendingPathComponent("frontend/public/wololo-left.png")
guard let imageSource = CGImageSourceCreateWithURL(source as CFURL, nil),
      let mascot = CGImageSourceCreateImageAtIndex(imageSource, 0, nil),
      let context = CGContext(data: nil, width: 1024, height: 1024, bitsPerComponent: 8,
                              bytesPerRow: 1024 * 4, space: CGColorSpace(name: CGColorSpace.sRGB)!,
                              bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else {
    fatalError("Could not load the site mascot or create the icon canvas")
}
context.setFillColor(CGColor(gray: 1, alpha: 1))
context.fill(CGRect(x: 0, y: 0, width: 1024, height: 1024))
let scale = 832 / CGFloat(max(mascot.width, mascot.height))
let size = CGSize(width: CGFloat(mascot.width) * scale, height: CGFloat(mascot.height) * scale)
context.interpolationQuality = .high
context.draw(mascot, in: CGRect(x: (1024 - size.width) / 2, y: (1024 - size.height) / 2,
                               width: size.width, height: size.height))
guard let icon = context.makeImage() else { fatalError("Could not render the app icon") }
for path in ["mobile/branding/app-icon.png", "mobile/ios/WololoApp/Resources/Assets.xcassets/AppIcon.appiconset/AppIcon.png"] {
    let output = root.appendingPathComponent(path)
    try FileManager.default.createDirectory(at: output.deletingLastPathComponent(), withIntermediateDirectories: true)
    guard let destination = CGImageDestinationCreateWithURL(output as CFURL, UTType.png.identifier as CFString, 1, nil) else {
        fatalError("Could not create icon output")
    }
    CGImageDestinationAddImage(destination, icon, nil)
    guard CGImageDestinationFinalize(destination) else { fatalError("Could not save icon output") }
    print(output.path)
}
