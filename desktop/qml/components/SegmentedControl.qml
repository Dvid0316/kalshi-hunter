import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Segmented selector. ``options`` = [{value, label}] or plain strings; emits picked(value).
Rectangle {
    id: seg
    property var options: []
    property string current: ""
    property string accessibleName: "Options"
    signal picked(string value)
    implicitHeight: 34
    implicitWidth: row.implicitWidth + 8
    radius: Theme.radiusSm
    color: Theme.input
    border.color: Theme.borderStrong
    Accessible.role: Accessible.RadioButton
    Accessible.name: accessibleName
    Row {
        id: row
        anchors.centerIn: parent
        spacing: 2
        Repeater {
            model: seg.options
            delegate: Button {
                id: b
                required property var modelData
                readonly property string value: typeof modelData === "string" ? modelData : modelData.value
                readonly property string caption: typeof modelData === "string" ? modelData : modelData.label
                focusPolicy: Qt.StrongFocus
                implicitHeight: 28
                implicitWidth: cap.implicitWidth + 24
                checkable: true
                checked: seg.current === value
                onClicked: seg.picked(value)
                Accessible.name: seg.accessibleName + ": " + caption
                Accessible.role: Accessible.RadioButton
                Accessible.checked: checked
                contentItem: Text {
                    id: cap
                    text: b.caption
                    color: b.checked ? "#06231f" : Theme.muted
                    font.pixelSize: Theme.fsSm + 1
                    font.weight: b.checked ? Font.DemiBold : Font.Normal
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    radius: 5
                    color: b.checked ? Theme.accent : (b.hovered ? Theme.panelHover : "transparent")
                    border.color: b.activeFocus ? Theme.ink : "transparent"
                    border.width: 2
                }
            }
        }
    }
}
