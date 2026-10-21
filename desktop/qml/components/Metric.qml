import QtQuick
import QtQuick.Layouts
import ".."

// Headline number with a label and a one-line explanation. Unavailable values stay visibly unavailable.
Panel {
    id: metric
    property string label: ""
    property string value: ""
    property string note: ""
    property color valueColor: Theme.ink
    implicitHeight: 128
    implicitWidth: 200
    Accessible.role: Accessible.StaticText
    Accessible.name: label + ": " + value + ". " + note
    Column {
        anchors.fill: parent
        anchors.margins: Theme.pad
        spacing: 8
        Small { text: metric.label; width: parent.width }
        Txt {
            text: metric.value
            width: parent.width
            color: metric.valueColor
            font.pixelSize: metric.value.length > 13 ? 21 : 28
            font.weight: Font.DemiBold
        }
        Small { text: metric.note; width: parent.width; font.pixelSize: Theme.fsXs; wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight }
    }
}
