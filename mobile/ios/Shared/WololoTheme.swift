import SwiftUI

enum WololoPalette {
    static let ink = Color(red: 0.102, green: 0.102, blue: 0.102)
    static let subtle = Color(red: 0.98, green: 0.98, blue: 0.98)
    static let muted = Color(red: 0.96, green: 0.96, blue: 0.96)
    static let border = Color(red: 0.898, green: 0.898, blue: 0.898)
}

struct WololoBrandHeader: View {
    var compact = false

    var body: some View {
        HStack(spacing: 10) {
            Image("WololoMascot")
                .resizable()
                .scaledToFit()
                .frame(width: compact ? 38 : 48, height: compact ? 42 : 54)
                .accessibilityHidden(true)
            Text("Wololo Converter")
                .font(compact ? .headline : .title2.weight(.semibold))
                .foregroundStyle(WololoPalette.ink)
        }
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isHeader)
    }
}

struct WololoCard<Content: View>: View {
    let content: Content

    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    var body: some View {
        content
            .padding(20)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.white, in: RoundedRectangle(cornerRadius: 16))
            .overlay(RoundedRectangle(cornerRadius: 16).stroke(WololoPalette.border, lineWidth: 1))
    }
}

struct WololoPrimaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(.white)
            .tint(.white)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background(isEnabled ? Color.black : Color(white: 0.55), in: RoundedRectangle(cornerRadius: 10))
            .opacity(configuration.isPressed ? 0.8 : 1)
    }
}
