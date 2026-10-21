import QtQuick
import ".."

// Transient message at the bottom of the window. Announced to assistive tech as an alert.
Rectangle {
    id: toast
    property string message: ""
    property string kind: "info"
    readonly property color tint: kind === "error" ? Theme.danger : (kind === "warn" ? Theme.warn : (kind === "ok" ? Theme.gain : Theme.accent))
    function show(text, k) { message = text; kind = k || "info"; visible = true; opacity = 1; timer.restart() }
    visible: false
    opacity: 0
    width: Math.min(560, label.implicitWidth + 40)
    height: Math.max(40, label.implicitHeight + 22)
    radius: 9
    color: "#101c29"
    border.color: tint
    z: 100
    Accessible.role: Accessible.AlertMessage
    Accessible.name: message
    Behavior on opacity { NumberAnimation { duration: 180 } }
    Text {
        id: label
        anchors.centerIn: parent
        width: Math.min(520, implicitWidth)
        text: toast.message
        color: Theme.ink
        font.pixelSize: Theme.fsSm + 1
        wrapMode: Text.WordWrap
        horizontalAlignment: Text.AlignHCenter
    }
    Timer { id: timer; interval: 4200; onTriggered: { toast.opacity = 0; hide.start() } }
    Timer { id: hide; interval: 220; onTriggered: toast.visible = false }
}
