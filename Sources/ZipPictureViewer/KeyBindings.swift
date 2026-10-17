import AppKit

/// Maps key presses on the image to viewer commands.
enum KeyBindings {
    static func command(for event: NSEvent) -> ViewerCommand? {
        let modifiers = event.modifierFlags.intersection([.command, .control, .option, .shift])
        let siblingModifier = modifiers.contains(.command) || modifiers.contains(.control)
        switch event.keyCode {
        case 123: return modifiers.isEmpty ? .previous : nil
        case 124: return modifiers.isEmpty ? .next : nil
        case 126: return siblingModifier ? .previousFolder : (modifiers.isEmpty ? .previousBundle : nil)
        case 125: return siblingModifier ? .nextFolder : (modifiers.isEmpty ? .nextBundle : nil)
        case 49: return modifiers.isEmpty ? .next : nil
        case 53: return .exitFullscreen
        default: break
        }
        guard !modifiers.contains(.command), !modifiers.contains(.control) else { return nil }
        switch event.charactersIgnoringModifiers?.lowercased() {
        case "o": return .openFolder
        case "r": return .refresh
        case "f": return .fullscreen
        case "0": return .fit
        case "1": return .actualSize
        case "+", "=": return .zoomIn
        case "-": return .zoomOut
        case "?", "/": return modifiers.contains(.shift) || event.characters == "?" ? .help : nil
        default: return nil
        }
    }
}
