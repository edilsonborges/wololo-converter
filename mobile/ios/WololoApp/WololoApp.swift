import SwiftUI
import UIKit
import UserNotifications

@main
struct WololoApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            MainView(model: delegate.model)
                .tint(Color(red: 0.91, green: 0.36, blue: 0.14))
                .task {
                    _ = try? await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound])
                }
                .onChange(of: scenePhase) { _, phase in
                    if phase == .active { delegate.model.refreshAndResume() }
                    if phase == .background { delegate.model.pausePolling() }
                }
        }
    }
}

final class AppDelegate: NSObject, UIApplicationDelegate {
    let model = AppModel()

    func application(
        _ application: UIApplication, handleEventsForBackgroundURLSession identifier: String,
        completionHandler: @escaping () -> Void
    ) {
        model.handleBackgroundEvents(identifier: identifier, completion: completionHandler)
    }
}
