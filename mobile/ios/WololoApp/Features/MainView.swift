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
                ScrollView {
                    VStack(spacing: 20) {
                        WololoBrandHeader().padding(.vertical, 8)
                        WololoCard {
                            VStack(alignment: .leading, spacing: 16) {
                                TextField(L("Paste a video link"), text: $text, axis: .vertical)
                                    .textInputAutocapitalization(.never)
                                    .autocorrectionDisabled()
                                    .keyboardType(.URL)
                                    .lineLimit(3...5)
                                    .font(.subheadline)
                                    .padding(14)
                                    .background(WololoPalette.subtle, in: RoundedRectangle(cornerRadius: 10))
                                    .overlay(RoundedRectangle(cornerRadius: 10).stroke(WololoPalette.border, lineWidth: 1))
                                    .accessibilityIdentifier("download.url")
                                    .focused($isEditingLink)
                                Picker(L("Format"), selection: $model.settings.format) {
                                    ForEach(DownloadFormat.allCases) { format in
                                        Text(format.title).tag(format)
                                    }
                                }.pickerStyle(.segmented)
                                if model.settings.format == .mp4 {
                                    HStack {
                                        Text(L("Video quality")).font(.subheadline)
                                        Spacer()
                                        Picker(L("Video quality"), selection: $model.settings.videoQuality) {
                                            ForEach(VideoQuality.videoOptions) { Text($0.rawValue).tag($0) }
                                        }.pickerStyle(.menu)
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
                                        Label(L("Download"), systemImage: "arrow.down")
                                    }
                                }
                                .buttonStyle(WololoPrimaryButtonStyle())
                                .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || model.isSubmitting)
                                .accessibilityIdentifier("download.start")
                            }
                        }
                        Text(L("You can also share a link to Wololo from another app."))
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal, 8)
                        if let error = model.errorMessage {
                            WololoCard {
                                VStack(alignment: .leading, spacing: 12) {
                                    Label(error, systemImage: "exclamationmark.circle")
                                        .font(.subheadline)
                                    Button(L("Dismiss")) { model.errorMessage = nil }
                                        .font(.subheadline.weight(.semibold))
                                }
                            }
                        }
                        WololoCard {
                            VStack(alignment: .leading, spacing: 16) {
                                if model.entries.isEmpty {
                                    VStack(spacing: 12) {
                                        Image(systemName: "tray")
                                            .font(.title2)
                                            .foregroundStyle(.secondary)
                                            .padding(16)
                                            .background(WololoPalette.muted, in: Circle())
                                        Text(L("Your download queue is empty"))
                                            .font(.headline)
                                        Text(L("Your downloads will appear here."))
                                            .font(.subheadline)
                                            .foregroundStyle(.secondary)
                                    }
                                    .multilineTextAlignment(.center)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 24)
                                } else {
                                    Text(L("Downloads"))
                                        .font(.headline)
                                        .accessibilityAddTraits(.isHeader)
                                    ForEach(model.entries) { entry in
                                        DownloadRow(entry: entry, model: model)
                                        if entry.id != model.entries.last?.id { Divider() }
                                    }
                                }
                            }
                        }
                    }
                    .frame(maxWidth: 600)
                    .padding(20)
                    .frame(maxWidth: .infinity)
                }
                .background(.white)
                .toolbar(.hidden, for: .navigationBar)
                .refreshable { model.refreshAndResume() }
            }
            .tabItem { Label(L("Downloads"), systemImage: "arrow.down.circle") }
            NavigationStack { SettingsView(model: model) }
                .tabItem { Label(L("Settings"), systemImage: "gearshape") }
        }
        .toolbarBackground(.white, for: .tabBar)
        .toolbarBackground(.visible, for: .tabBar)
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
            if let error = entry.errorMessage {
                Label(error, systemImage: "exclamationmark.circle").font(.caption)
            }
            if [.queued, .processing, .transferring].contains(entry.status) {
                ProgressView(value: min(max(entry.progress, 0), 100), total: 100)
                    .accessibilityLabel(L("Download progress"))
                Button(L("Cancel"), role: .destructive) { Task { await model.cancel(entry) } }
                    .buttonStyle(.borderless)
                    .foregroundStyle(WololoPalette.ink)
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
