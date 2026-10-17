import Foundation

/// Loopback control channel used by the end-to-end tests.
///
/// It exists only when the app is launched with `--automation-handshake`
/// and a key in `ZIP_PICTURE_VIEWER_AUTOMATION_KEY`. The protocol is one
/// JSON object per line; the first line must be `{"auth": "<key>"}`.
final class AutomationServer {
    static let keyEnvironment = "ZIP_PICTURE_VIEWER_AUTOMATION_KEY"

    private let commands: AutomationCommands
    private let key: String
    private let listener: Int32

    init(controller: MainWindowController, handshake: URL) throws {
        guard let key = ProcessInfo.processInfo.environment[Self.keyEnvironment], !key.isEmpty else {
            throw AutomationError("\(Self.keyEnvironment) is required for automation")
        }
        self.key = key
        commands = AutomationCommands(controller: controller)
        listener = socket(AF_INET, SOCK_STREAM, 0)
        guard listener >= 0 else { throw AutomationError("socket() failed") }
        var address = sockaddr_in()
        address.sin_family = sa_family_t(AF_INET)
        address.sin_addr.s_addr = inet_addr("127.0.0.1")
        address.sin_port = 0
        var length = socklen_t(MemoryLayout<sockaddr_in>.size)
        let bound = withUnsafeMutablePointer(to: &address) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { generic in
                bind(listener, generic, length) == 0 && listen(listener, 1) == 0
                    && getsockname(listener, generic, &length) == 0
            }
        }
        guard bound else { throw AutomationError("Cannot listen on 127.0.0.1") }
        let port = Int(UInt16(bigEndian: address.sin_port))
        let thread = Thread { [weak self] in self?.serve() }
        thread.name = "automation"
        thread.start()
        try writeHandshake(handshake, port: port)
    }

    private func serve() {
        let client = accept(listener, nil, nil)
        guard client >= 0 else { return }
        let stream = LineStream(descriptor: client)
        guard let first = stream.readJSON(), first["auth"] as? String == key else {
            close(client)
            return
        }
        while let request = stream.readJSON() {
            var reply: [String: Any] = [:]
            DispatchQueue.main.sync {
                do {
                    reply["result"] = try self.commands.run(request)
                } catch {
                    reply["error"] = String(describing: error)
                }
            }
            stream.writeJSON(reply)
        }
        close(client)
    }

    private func writeHandshake(_ url: URL, port: Int) throws {
        let data = try JSONSerialization.data(withJSONObject: ["port": port, "pid": getpid()])
        try data.write(to: url, options: .atomic)
    }
}

struct AutomationError: Error, CustomStringConvertible {
    let description: String
    init(_ description: String) { self.description = description }
}

/// Newline-delimited JSON over a socket.
private final class LineStream {
    private let descriptor: Int32
    private var buffer = Data()

    init(descriptor: Int32) { self.descriptor = descriptor }

    func readJSON() -> [String: Any]? {
        while true {
            if let newline = buffer.firstIndex(of: 0x0A) {
                let line = buffer[buffer.startIndex..<newline]
                buffer.removeSubrange(buffer.startIndex...newline)
                return (try? JSONSerialization.jsonObject(with: line)) as? [String: Any] ?? [:]
            }
            var chunk = [UInt8](repeating: 0, count: 65_536)
            let count = read(descriptor, &chunk, chunk.count)
            guard count > 0 else { return nil }
            buffer.append(contentsOf: chunk[0..<count])
        }
    }

    func writeJSON(_ object: [String: Any]) {
        guard var data = try? JSONSerialization.data(withJSONObject: object) else { return }
        data.append(0x0A)
        data.withUnsafeBytes { bytes in
            var offset = 0
            while offset < bytes.count {
                let written = write(descriptor, bytes.baseAddress! + offset, bytes.count - offset)
                if written <= 0 { return }
                offset += written
            }
        }
    }
}
