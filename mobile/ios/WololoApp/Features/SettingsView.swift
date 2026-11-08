import SwiftUI
import WololoKit

struct SettingsView: View {
    @Bindable var model: AppModel
    @State private var saved = false

    var body: some View {
        Form {
            Section(L("Server")) {
                TextField(L("Server address"), text: $model.settings.serverURL)
                    .keyboardType(.URL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .accessibilityIdentifier("settings.server")
                    .onChange(of: model.settings.serverURL) { _, _ in model.serverAddressChanged() }
                SecureField(L("Access key"), text: $model.accessKey)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                Button(L("Test connection")) { Task { await model.checkConnection() } }
                if let result = model.connectionMessage { Text(result).font(.footnote) }
            }
            .listRowBackground(WololoPalette.subtle)
            Section(L("Download preferences")) {
                Picker(L("Default format"), selection: $model.settings.format) {
                    ForEach(DownloadFormat.allCases) { Text($0.title).tag($0) }
                }
                Picker(L("Video quality"), selection: $model.settings.videoQuality) {
                    ForEach(VideoQuality.videoOptions) { Text($0.rawValue).tag($0) }
                }
            }
            .listRowBackground(WololoPalette.subtle)
            Section {
                Text(L("Videos are saved to Photos. Audio is saved to Files, under On My iPhone / Wololo."))
                    .font(.footnote)
                Text(L("Use Wololo for content you own or have permission to download."))
                    .font(.footnote).foregroundStyle(.secondary)
                LabeledContent(L("Version"), value: AppConstants.appVersion)
            }
            .listRowBackground(WololoPalette.subtle)
            if saved { Label(L("Settings saved"), systemImage: "checkmark.circle") }
            if let error = model.errorMessage { Label(error, systemImage: "exclamationmark.circle") }
        }
        .scrollContentBackground(.hidden)
        .background(.white)
        .foregroundStyle(WololoPalette.ink)
        .navigationTitle(L("Settings"))
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(.white, for: .navigationBar)
        .toolbar {
            Button(L("Save")) {
                do { try model.saveSettings(); saved = true; model.errorMessage = nil }
                catch { saved = false; model.errorMessage = error.localizedDescription }
            }
        }
    }
}
