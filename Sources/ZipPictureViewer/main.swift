import AppKit

let launchOptions = LaunchOptions(arguments: CommandLine.arguments)
if launchOptions.smokeTest {
    exit(SmokeTest.run())
}
let application = NSApplication.shared
let appDelegate = AppDelegate(launch: launchOptions)
application.delegate = appDelegate
application.setActivationPolicy(.regular)
application.run()
