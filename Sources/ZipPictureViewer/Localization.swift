import Foundation
import ViewerCore

/// The UI language the user chose; `system` follows the Mac's language list.
enum AppLanguage: String, CaseIterable {
    case system
    case korean = "ko"
    case english = "en"
}

/// Text in both UI languages, resolved when it is displayed so a language
/// switch also updates messages that were produced earlier.
struct LocalizedText: Equatable {
    let korean: String
    let english: String

    init(_ korean: String, _ english: String) {
        self.korean = korean
        self.english = english
    }

    /// Text that reads the same in both languages, such as "3 / 120".
    init(verbatim text: String) {
        self.init(text, text)
    }

    var string: String { Localization.shared.isKorean ? korean : english }

    /// "<self>  ·  <other>"
    func joined(with other: LocalizedText) -> LocalizedText {
        LocalizedText("\(korean)  ·  \(other.korean)", "\(english)  ·  \(other.english)")
    }
}

/// Stores the language preference and announces changes.
///
/// The choice lives in `settings.json` next to the session file, so it
/// follows `ZIP_PICTURE_VIEWER_CONFIG_DIR` (tests never touch the user's
/// own setting). `-AppLanguage ko|en|system` sets the starting language.
final class Localization {
    static let shared = Localization()
    static let didChange = Notification.Name("ZipPictureViewerLanguageDidChange")
    static let argumentKey = "AppLanguage"

    private static var settingsURL: URL {
        SessionStore.defaultFileURL().deletingLastPathComponent().appendingPathComponent("settings.json")
    }

    private(set) lazy var preference: AppLanguage = {
        let argument = UserDefaults.standard.volatileDomain(forName: UserDefaults.argumentDomain)[Self.argumentKey]
        let stored = (try? Data(contentsOf: Self.settingsURL))
            .flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }?["language"]
        return AppLanguage(rawValue: (argument ?? stored) as? String ?? "") ?? .system
    }()

    func setPreference(_ language: AppLanguage) {
        preference = language
        do {
            try FileManager.default.createDirectory(at: Self.settingsURL.deletingLastPathComponent(), withIntermediateDirectories: true)
            let data = try JSONSerialization.data(withJSONObject: ["language": language.rawValue], options: [.prettyPrinted])
            try data.write(to: Self.settingsURL, options: .atomic)
        } catch {
            NSLog("Cannot save the language setting: %@", error.localizedDescription)
        }
        NotificationCenter.default.post(name: Self.didChange, object: self)
    }

    var isKorean: Bool {
        switch preference {
        case .korean: return true
        case .english: return false
        case .system: return Locale.preferredLanguages.first?.hasPrefix("ko") ?? false
        }
    }

    /// Run `update` now and whenever the language changes. The views using
    /// this live as long as the app, so observers are never removed.
    func observe(_ update: @escaping () -> Void) {
        update()
        observers.append(NotificationCenter.default.addObserver(forName: Self.didChange, object: nil, queue: .main) { _ in
            update()
        })
    }

    private var observers: [NSObjectProtocol] = []
}

/// Shorthand for a Korean/English pair.
func L(_ korean: String, _ english: String) -> LocalizedText {
    LocalizedText(korean, english)
}
