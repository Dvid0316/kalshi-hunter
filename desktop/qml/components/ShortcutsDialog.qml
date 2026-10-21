import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Keyboard shortcut reference. Opened with F1.
Popup {
    id: dlg
    objectName: "shortcuts_dialog"
    modal: true
    focus: true
    anchors.centerIn: Overlay.overlay
    width: Math.min(560, Overlay.overlay ? Overlay.overlay.width - 40 : 560)
    padding: 24
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    background: Rectangle { color: Theme.panel; radius: Theme.radius; border.color: Theme.borderStrong }
    Overlay.modal: Rectangle { color: "#a0050a10" }
    readonly property var items: [
        ["Ctrl+1 … Ctrl+9, Ctrl+0", "Go to page 1–10 (sidebar order)"],
        ["Ctrl+K   or   /", "Search markets"],
        ["Esc", "Clear the search box / close this window"],
        ["Alt+Left   Alt+Right", "Previous / next page of the current table"],
        ["Up   Down   Enter", "Move through a table, open the row"],
        ["Left   Right  (on a chart)", "Step through archived snapshots"],
        ["F5   or   Ctrl+R", "Reload local data"],
        ["Ctrl+,", "Settings"],
        ["F1", "This help"],
        ["Ctrl+Q", "Quit"]
    ]
    contentItem: ColumnLayout {
        spacing: 14
        Accessible.role: Accessible.Dialog
        Accessible.name: "Keyboard shortcuts"
        Txt { text: "Keyboard shortcuts"; font.pixelSize: Theme.fsXl - 4; font.weight: Font.DemiBold }
        Repeater {
            model: dlg.items
            delegate: RowLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: 16
                Mono { text: modelData[0]; color: Theme.accent; Layout.preferredWidth: 230; elide: Text.ElideRight }
                Small { text: modelData[1]; Layout.fillWidth: true; font.pixelSize: Theme.fsSm + 1; elide: Text.ElideNone; wrapMode: Text.WordWrap }
            }
        }
        Btn { text: "Close"; primary: true; Layout.alignment: Qt.AlignRight; onClicked: dlg.close() }
    }
}
