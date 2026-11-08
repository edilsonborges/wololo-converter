import SwiftUI
import WololoKit

struct MainView: View {
    @Bindable var model: AppModel
    @State private var text = ""
    @FocusState private var isEditingLink: Bool
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        TabView {
            NavigationStack {
                List {
                    Section {
                        TextField(L("Paste a video link"), text: $text, axis: .vertical)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .keyboardType(.URL)
                            .lineLimit(2...4)
                            .accessibilityIdentifier("download.url")
                            .focused($isEditingLink)
                        Picker(L("Format"), selection: $model.settings.format) {
                            ForEach(DownloadFormat.allCases) { format in
                                Text(format.title).tag(format)
                            }
                        }.pickerStyle(.segmented)
                        if model.settings.format == .mp4 {
                            Picker(L("Video quality"), selection: $model.settings.videoQuality) {
                                ForEach(VideoQuality.videoOptions) { Text($0.rawValue).tag($0) }
                            }
                        }
                        Button {
                            isEditingLink = false
                            Task {
                                if await model.submit(text: text) != nil { text = "" }
                            }
                        } label: {
                            HStack {
                                if model.isSubmitting { ProgressView() }
                                Label(L("Download"), systemImage: "arrow.down.circle.fill")
                            }.frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || model.isSubmitting)
                        .accessibilityIdentifier("download.start")
                    } footer: {
                        Text(L("You can also share a link to Wololo from another app."))
                    }
                    if let error = model.errorMessage {
                        Section {
                            Text(error).foregroundStyle(.red)
                            Button(L("Dismiss")) { model.errorMessage = nil }
                        }
                    }
                    Section(L("Downloads")) {
                        if model.entries.isEmpty {
                            ContentUnavailableView(L("Ready when you are"), systemImage: "arrow.down.to.line",
                                description: Text(L("Your downloads will appear here.")))
                        }
                        ForEach(model.entries) { entry in
                            DownloadRow(entry: entry, model: model)
                        }
                    }
                }
                .navigationTitle("Wololo")
                .refreshable { model.refreshAndResume() }
            }
            .tabItem { Label(L("Downloads"), systemImage: "arrow.down.circle") }
            NavigationStack { SettingsView(model: model) }
                .tabItem { Label(L("Settings"), systemImage: "gearshape") }
        }
        .task(id: scenePhase) {
            guard scenePhase == .active else { return }
            while !Task.isCancelled {
                model.refreshAndResume()
                try? await Task.sleep(for: .seconds(1))
            }
        }
        .onOpenURL { url in
            guard url.scheme == "wololo", let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
                  let shared = components.queryItems?.first(where: { $0.name == "url" })?.value else { return }
            text = shared
        }
    }
}

struct DownloadRow: View {
    let entry: LocalDownload
    let model: AppModel

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                Text(entry.title ?? entry.sourceURL).font(.headline).lineLimit(2)
                Spacer(minLength: 8)
                Text(entry.format.title).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            }
            Text(statusTitle(entry.status)).font(.subheadline).foregroundStyle(.secondary)
            if let error = entry.errorMessage { Text(error).font(.caption).foregroundStyle(.red) }
            if [.queued, .processing, .transferring].contains(entry.status) {
                ProgressView(value: min(max(entry.progress, 0), 100), total: 100)
                    .accessibilityLabel(L("Download progress"))
                Button(L("Cancel"), role: .destructive) { Task { await model.cancel(entry) } }
                    .buttonStyle(.borderless)
            }
            if entry.status == .readyToSave {
                Button(L("Save")) { model.save(entry) }.buttonStyle(.bordered)
            }
            if entry.status == .failed || entry.status == .cancelled || entry.status == .saved {
                HStack {
                    Button(L("Download again")) { Task { await model.retry(entry) } }
                        .buttonStyle(.borderless)
                    if entry.status == .saved, let path = entry.localPath {
                        ShareLink(item: URL(fileURLWithPath: path)) { Text(L("Share file")) }
                            .buttonStyle(.borderless)
                    }
                }
            }
        }.padding(.vertical, 4)
    }
}
