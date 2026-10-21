import QtQuick
import QtQuick.Controls
import ".."

// Sidebar entry. objectName "nav_<Page>" is what the UI self-tests click.
Button {
    id: nav
    property string page: ""
    property string glyph: ""
    property bool current: false
    property bool compact: false
    property string hint: ""
    objectName: "nav_" + page
    focusPolicy: Qt.StrongFocus
    hoverEnabled: true
    implicitHeight: 42
    Accessible.name: page + (current ? " (current page)" : "")
    Accessible.description: hint
    Accessible.role: Accessible.PageTab
    ToolTip.visible: compact && hovered
    ToolTip.text: page + (hint ? "  ·  " + hint : "")
    ToolTip.delay: 400
    contentItem: Row {
        spacing: 12
        leftPadding: nav.compact ? 0 : 10
        anchors.verticalCenter: parent.verticalCenter
        Item {
            width: nav.compact ? nav.width - 16 : 24
            height: 24
            Text {
                anchors.centerIn: parent
                text: nav.glyph
                color: nav.current ? Theme.accent : Theme.faint
                font.pixelSize: 19
            }
        }
        Text {
            visible: !nav.compact
            anchors.verticalCenter: parent.verticalCenter
            text: nav.page
            color: nav.current ? Theme.ink : Theme.muted
            font.pixelSize: 13
            font.weight: nav.current ? Font.DemiBold : Font.Normal
        }
    }
    background: Rectangle {
        radius: 8
        color: nav.current ? "#1b3340" : (nav.hovered ? "#182737" : "transparent")
        border.color: nav.activeFocus ? Theme.accent : "transparent"
        border.width: 2
    }
}
