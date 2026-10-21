import QtQuick
import QtQuick.Layouts
import ".."

// Honest empty / loading / error state. Optional action buttons go inside as children.
Panel {
    id: empty
    property string heading: ""
    property string description: ""
    property string badge: ""
    property color badgeTint: Theme.muted
    property bool busy: false
    default property alias actions: actionRow.data
    implicitHeight: Math.max(220, col.implicitHeight + 64)
    Accessible.role: Accessible.StaticText
    Accessible.name: heading + ". " + description
    ColumnLayout {
        id: col
        anchors.centerIn: parent
        width: Math.min(parent.width - 60, 640)
        spacing: 14
        Tag { visible: empty.badge.length > 0; label: empty.badge; tint: empty.badgeTint; Layout.alignment: Qt.AlignHCenter }
        BusyDots { visible: empty.busy; Layout.alignment: Qt.AlignHCenter }
        Txt { text: empty.heading; Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; font.pixelSize: Theme.fsXl - 2
              font.weight: Font.DemiBold; wrapMode: Text.WordWrap; elide: Text.ElideNone }
        Text { text: empty.description; color: Theme.muted; Layout.fillWidth: true; wrapMode: Text.WordWrap
               horizontalAlignment: Text.AlignHCenter; font.pixelSize: Theme.fsMd; lineHeight: 1.4; visible: empty.description.length > 0 }
        Row { id: actionRow; spacing: 10; Layout.alignment: Qt.AlignHCenter }
    }
}
