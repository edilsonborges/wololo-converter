import SwiftUI
import UIKit
import UniformTypeIdentifiers
import WololoKit

final class ShareViewController: UIViewController {
    private let model = AppModel(isExtension: true)
    private var loadTask: Task<Void, Never>?

    override func viewDidLoad() {
        super.viewDidLoad()
        preferredContentSize = CGSize(width: 400, height: 520)
        loadTask = Task {
            let text = await sharedText()
            guard !Task.isCancelled else { return }
            let view = ShareView(model: model, sharedText: text, finish: { [weak self] in self?.finish() })
            let host = UIHostingController(rootView: view)
            addChild(host)
            host.view.translatesAutoresizingMaskIntoConstraints = false
            self.view.addSubview(host.view)
            NSLayoutConstraint.activate([
                host.view.leadingAnchor.constraint(equalTo: self.view.leadingAnchor),
                host.view.trailingAnchor.constraint(equalTo: self.view.trailingAnchor),
                host.view.topAnchor.constraint(equalTo: self.view.topAnchor),
                host.view.bottomAnchor.constraint(equalTo: self.view.bottomAnchor),
            ])
            host.didMove(toParent: self)
        }
    }

    override func viewDidDisappear(_ animated: Bool) {
        super.viewDidDisappear(animated)
        model.pausePolling()
    }

    private func finish() {
        loadTask?.cancel()
        model.pausePolling()
        extensionContext?.completeRequest(returningItems: nil)
    }

    private func sharedText() async -> String {
        let items = extensionContext?.inputItems as? [NSExtensionItem] ?? []
        var firstText = ""
        for item in items {
            for provider in item.attachments ?? [] {
                let identifiers = [UTType.url.identifier, UTType.plainText.identifier, UTType.text.identifier]
                for type in identifiers where provider.hasItemConformingToTypeIdentifier(type) {
                    if let text = try? await text(from: provider, type: type) {
                        if LinkParser.firstSupportedLink(in: text) != nil { return text }
                        if firstText.isEmpty { firstText = text }
                    }
                }
            }
            if let text = item.attributedContentText?.string {
                if LinkParser.firstSupportedLink(in: text) != nil { return text }
                if firstText.isEmpty { firstText = text }
            }
        }
        return firstText
    }

    private func text(from provider: NSItemProvider, type: String) async throws -> String? {
        try await withCheckedThrowingContinuation { continuation in
            provider.loadItem(forTypeIdentifier: type, options: nil) { item, error in
                if let error { continuation.resume(throwing: error); return }
                let text: String?
                if let url = item as? URL { text = url.absoluteString }
                else if let string = item as? String { text = string }
                else if let data = item as? Data { text = String(data: data, encoding: .utf8) }
                else { text = nil }
                continuation.resume(returning: text)
            }
        }
    }
}
