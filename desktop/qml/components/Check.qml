import QtQuick
import QtQuick.Controls
import ".."

// Check box with a visible, high-contrast indicator and focus ring.
CheckBox {
    id: box
    focusPolicy: Qt.StrongFocus
    implicitHeight: 30
    Accessible.name: text
    Accessible.role: Accessible.CheckBox
    Accessible.checked: checked
    indicator: Rectangle {
        x: 0
        y: (box.height - height) / 2
        width: 20; height: 20; radius: 5
        color: box.checked ? Theme.accent : Theme.input
        border.color: box.activeFocus ? Theme.ink : (box.checked ? Theme.accent : Theme.borderStrong)
        border.width: 2
        Text { anchors.centerIn: parent; visible: box.checked; text: "✓"; color: "#06231f"; font.pixelSize: 14; font.weight: Font.Bold }
    }
    contentItem: Text {
        text: box.text
        color: Theme.ink
        font.pixelSize: Theme.fsSm + 1
        leftPadding: box.indicator.width + 8
        verticalAlignment: Text.AlignVCenter
    }
}
