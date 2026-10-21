import QtQuick
import QtQuick.Controls
import ".."

// Debounced search box. Emits submitted(text) 300 ms after typing stops (or on Enter). Escape clears it.
TextField {
    id: box
    property int debounce: 300
    property string accessibleName: placeholderText
    signal submitted(string value)
    implicitHeight: 38
    placeholderTextColor: Theme.faint
    color: Theme.ink
    selectByMouse: true
    font.pixelSize: Theme.fsMd - 1
    leftPadding: 14
    rightPadding: 34
    focusPolicy: Qt.StrongFocus
    Accessible.name: accessibleName
    Accessible.role: Accessible.EditableText
    background: Rectangle {
        color: Theme.input
        radius: Theme.radiusSm
        border.color: box.activeFocus ? Theme.accent : Theme.borderStrong
        border.width: box.activeFocus ? 2 : 1
    }
    onTextEdited: timer.restart()
    onAccepted: { timer.stop(); box.submitted(text) }
    Keys.onEscapePressed: { if (text.length > 0) { text = ""; timer.stop(); box.submitted("") } else { focus = false } }
    Timer { id: timer; interval: box.debounce; onTriggered: box.submitted(box.text) }
    // clear button
    Rectangle {
        visible: box.text.length > 0
        anchors.right: parent.right
        anchors.rightMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        width: 22; height: 22; radius: 11
        color: clearArea.containsMouse ? Theme.panelHover : "transparent"
        Accessible.role: Accessible.Button
        Accessible.name: "Clear search"
        Text { anchors.centerIn: parent; text: "✕"; color: Theme.muted; font.pixelSize: 11 }
        MouseArea { id: clearArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
            onClicked: { box.text = ""; timer.stop(); box.submitted(""); box.forceActiveFocus() } }
    }
}
