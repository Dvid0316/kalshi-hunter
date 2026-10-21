import QtQuick
import ".."

// Small status chip. Always carries text (never colour alone).
Rectangle {
    id: tag
    property string label: ""
    property color tint: Theme.accent
    implicitWidth: chipText.implicitWidth + 20
    implicitHeight: 24
    radius: 6
    color: Qt.rgba(tint.r, tint.g, tint.b, 0.10)
    border.color: Qt.rgba(tint.r, tint.g, tint.b, 0.32)
    Accessible.role: Accessible.StaticText
    Accessible.name: label
    Text {
        id: chipText
        anchors.centerIn: parent
        text: tag.label
        color: tag.tint
        font.pixelSize: Theme.fsXs
        font.weight: Font.DemiBold
        font.letterSpacing: 0.4
        font.capitalization: Font.AllUppercase
    }
}
