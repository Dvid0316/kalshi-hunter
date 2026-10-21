import QtQuick
import QtQuick.Controls
import ".."

// Standard button. Keyboard-focusable with a visible focus ring; accessible name = its text.
Button {
    id: act
    property bool primary: false
    property bool danger: false
    implicitHeight: 34
    implicitWidth: Math.max(96, label.implicitWidth + 28)
    focusPolicy: Qt.StrongFocus
    hoverEnabled: true
    Accessible.name: text
    Accessible.role: Accessible.Button
    contentItem: Text {
        id: label
        text: act.text
        color: !act.enabled ? Theme.faint : (act.primary ? "#06231f" : (act.danger ? Theme.danger : Theme.ink))
        font.pixelSize: Theme.fsSm + 1
        font.weight: act.primary ? Font.DemiBold : Font.Normal
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    background: Rectangle {
        radius: Theme.radiusSm
        color: !act.enabled ? Theme.panelAlt : (act.primary ? (act.hovered ? "#6be8d5" : Theme.accent) : (act.hovered ? "#263d50" : "#1b2b3d"))
        border.color: act.activeFocus ? Theme.accent : (act.primary ? Theme.accent : Theme.borderStrong)
        border.width: act.activeFocus ? 2 : 1
        opacity: act.enabled ? 1 : 0.6
    }
}
