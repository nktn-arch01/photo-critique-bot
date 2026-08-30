import AppKit
import Darwin
import Foundation

final class GuidedDockDelegate: NSObject, NSApplicationDelegate {
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if let raw = ProcessInfo.processInfo.environment["GUIDED_PY_PID"],
           let pid = Int32(raw), pid > 1 {
            kill(pid, SIGTERM)
        }
        return .terminateNow
    }
}

let app = NSApplication.shared
let delegate = GuidedDockDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.activate(ignoringOtherApps: true)
app.run()
