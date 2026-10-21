import QtQuick
import QtQuick.Layouts
import ".."

// Full-width notice. kind: info | warn | error | sample. Wraps text so nothing is clipped at narrow widths.
Rectangle {
    id: banner
    property string text: ""
    property string kind: "warn"
    property string actionText: ""
    signal actionClicked()
    readonly property color fg: kind === "error" ? Theme.danger : (kind === "sample" ? Theme.sample : (kind === "info" ? Theme.accent : Theme.warn))
    readonly property color bgc: kind === "error" ? Theme.dangerBg : (kind === "sample" ? Theme.sampleBg : (kind === "info" ? Theme.accentBg : Theme.warnBg))
    readonly property color edge: kind === "error" ? Theme.dangerBorder : (kind === "sample" ? Theme.sampleBorder : (kind === "info" ? Theme.borderStrong : Theme.warnBorder))
    visible: text.length > 0
    Layout.fillWidth: true
    implicitHeight: visible ? Math.max(38, label.implicitHeight + 20) : 0
    radius: Theme.radiusSm
    color: bgc
    border.color: edge
    Accessible.role: Accessible.AlertMessage
    Accessible.name: text
    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 14
        anchors.rightMargin: 10
        spacing: 12
        Text {
            id: label
            Layout.fillWidth: true
            text: banner.text
            color: banner.fg
            font.pixelSize: Theme.fsSm + 1
            wrapMode: Text.WordWrap
        }
        Btn { visible: banner.actionText.length > 0; text: banner.actionText; implicitWidth: 80; implicitHeight: 28; onClicked: banner.actionClicked() }
    }
}
