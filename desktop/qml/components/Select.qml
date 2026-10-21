import QtQuick
import QtQuick.Controls
import ".."

// Drop-down with the app's look. ``model`` must be a list of {value, label}. Emits picked(value).
ComboBox {
    id: combo
    property string accessibleName: "Choose"
    valueRole: "value"
    signal picked(string value)
    implicitHeight: 34
    implicitWidth: 150
    focusPolicy: Qt.StrongFocus
    textRole: "label"
    Accessible.name: accessibleName + ": " + displayText
    Accessible.role: Accessible.ComboBox

    onActivated: function (index) { picked(String(model[index].value)) }
    function select(value) {
        for (var i = 0; i < model.length; i++) {
            if (String(model[i].value) === String(value)) { currentIndex = i; return }
        }
    }

    delegate: ItemDelegate {
        required property var modelData
        required property int index
        width: combo.popup.width - 2
        highlighted: combo.highlightedIndex === index
        Accessible.name: modelData.label
        contentItem: Text {
            text: modelData.label
            color: Theme.ink
            font.pixelSize: Theme.fsSm + 1
            elide: Text.ElideRight
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle { color: highlighted ? Theme.panelHover : Theme.panel }
    }
    contentItem: Text {
        leftPadding: 12
        rightPadding: 28
        text: combo.displayText
        color: Theme.ink
        font.pixelSize: Theme.fsSm + 1
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    indicator: Text {
        x: combo.width - width - 10
        y: (combo.height - height) / 2
        text: "▾"
        color: Theme.muted
        font.pixelSize: 12
    }
    background: Rectangle {
        radius: Theme.radiusSm
        color: Theme.input
        border.color: combo.activeFocus ? Theme.accent : Theme.borderStrong
        border.width: combo.activeFocus ? 2 : 1
    }
    popup: Popup {
        y: combo.height + 2
        width: Math.max(combo.width, 200)
        implicitHeight: Math.min(contentItem.implicitHeight + 2, 320)
        padding: 1
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: combo.popup.visible ? combo.delegateModel : null
            ScrollBar.vertical: ScrollBar {}
        }
        background: Rectangle { color: Theme.panel; border.color: Theme.borderStrong; radius: Theme.radiusSm }
    }
}
