import SwiftUI
import UniformTypeIdentifiers
import WololoKit

struct ShareView: View {
    @Bindable var model: AppModel
    let sharedText: String
    let finish: () -> Void
    @State private var activeID: UUID?
    @State private var export: LocalDownload?

    private var active: LocalDownload? { model.entries.first { $0.id == activeID } }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    if let entry = active {
                        Text(entry.title ?? L("Your download")).font(.title2.bold()).lineLimit(3)
                        Text(statusTitle(entry.status)).foregroundStyle(.secondary)
                        if let error = entry.errorMessage { Text(error).foregroundStyle(.red) }
                        if [.queued, .processing, .transferring].contains(entry.status) {
                            ProgressView(value: min(max(entry.progress, 0), 100), total: 100)
                            Text(L("Keep this sheet open while the server prepares your file. If you close it now, open Wololo to resume."))
                                .font(.footnote).foregroundStyle(.secondary)
                            Button(L("Cancel download"), role: .destructive) {
                                Task { await model.cancel(entry) }
                            }
                        }
                        if entry.status == .readyToSave {
                            if entry.format == .mp3 {
                                Button(L("Save to Files")) { export = entry }
                                    .buttonStyle(.borderedProminent)
                            } else {
                                Button(L("Save to Photos")) { model.save(entry) }
                                    .buttonStyle(.borderedProminent)
                            }
                        }
                        if entry.status == .saved {
                            Label(L("Saved"), systemImage: "checkmark.circle.fill").foregroundStyle(.green)
                        }
                        if entry.status == .failed || entry.status == .cancelled {
                            Button(L("Try again")) { activeID = nil }
                        }
                    } else {
                        Text(L("Save this moment")).font(.largeTitle.bold())
                        Text(LinkParser.firstSupportedLink(in: sharedText)?.url.absoluteString ?? L("Share a supported video link to get started."))
                            .font(.subheadline).foregroundStyle(.secondary).lineLimit(3)
                        Picker(L("Format"), selection: $model.settings.format) {
                            ForEach(DownloadFormat.allCases) { Text($0.title).tag($0) }
                        }.pickerStyle(.segmented)
                        if model.settings.format == .mp4 {
                            Picker(L("Video quality"), selection: $model.settings.videoQuality) {
                                ForEach(VideoQuality.videoOptions) { Text($0.rawValue).tag($0) }
                            }
                        }
                        Button {
                            Task { activeID = await model.submit(text: sharedText) }
                        } label: {
                            HStack {
                                if model.isSubmitting { ProgressView() }
                                Text(L("Download"))
                            }.frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(model.isSubmitting || LinkParser.firstSupportedLink(in: sharedText) == nil)
                    }
                    if let error = model.errorMessage { Text(error).font(.footnote).foregroundStyle(.red) }
                }.padding(24)
            }
            .navigationTitle("Wololo")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button(L("Done"), action: finish) } }
            .tint(Color(red: 0.91, green: 0.36, blue: 0.14))
        }
        .task {
            while !Task.isCancelled {
                model.reload()
                model.reconcileTransfers()
                try? await Task.sleep(for: .seconds(0.5))
            }
        }
        .sheet(item: $export) { entry in
            if let path = entry.localPath {
                FileExporter(file: URL(fileURLWithPath: path)) {
                    model.markExported(entry)
                    export = nil
                }
            }
        }
    }
}

struct FileExporter: UIViewControllerRepresentable {
    let file: URL
    let completion: () -> Void
    func makeCoordinator() -> Coordinator { Coordinator(completion: completion) }
    func makeUIViewController(context: Context) -> UIDocumentPickerViewController {
        let picker = UIDocumentPickerViewController(forExporting: [file], asCopy: true)
        picker.delegate = context.coordinator
        return picker
    }
    func updateUIViewController(_ controller: UIDocumentPickerViewController, context: Context) {}
    final class Coordinator: NSObject, UIDocumentPickerDelegate {
        let completion: () -> Void
        init(completion: @escaping () -> Void) { self.completion = completion }
        func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
            if !urls.isEmpty { completion() }
        }
    }
}
