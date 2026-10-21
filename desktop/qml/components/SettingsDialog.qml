import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

Popup {
    id: dlg
    objectName: "settings_dialog"
    modal: true
    focus: true
    anchors.centerIn: Overlay.overlay
    width: Math.min(620, Overlay.overlay ? Overlay.overlay.width - 40 : 620)
    padding: 24
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    background: Rectangle { color: Theme.panel; radius: Theme.radius; border.color: Theme.borderStrong }
    Overlay.modal: Rectangle { color: "#a0050a10" }
    contentItem: ColumnLayout {
        spacing: 14
        Accessible.role: Accessible.Dialog
        Accessible.name: "Settings"
        Txt { text: "Settings"; font.pixelSize: Theme.fsXl - 4; font.weight: Font.DemiBold }
        Switch {
            id: links
            checked: backend.ui.allowLinks
            Accessible.name: "Allow opening source links in my web browser"
            text: "Allow opening source links in my web browser"
            focusPolicy: Qt.StrongFocus
            onToggled: backend.setAllowLinks(checked)
            contentItem: Text { text: links.text; color: Theme.ink; font.pixelSize: Theme.fsMd - 1; leftPadding: links.indicator.width + 10; verticalAlignment: Text.AlignVCenter }
        }
        Small { Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone
                text: "Off by default. Kalshi Hunter never fetches web pages itself. When this is on, clicking a source link hands it to your own browser; when it is off the link is copied to the clipboard instead." }
        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
        Small { text: "Where your data lives"; font.weight: Font.DemiBold; color: Theme.ink }
        Mono { Layout.fillWidth: true; text: "Research snapshot (read-only):  " + (backend.diagnostics.snapshot || "see Evidence › Diagnostics"); elide: Text.ElideMiddle }
        Mono { Layout.fillWidth: true; text: "Your ledger & journal:  " + (backend.account_status.path || "var/account.db"); elide: Text.ElideMiddle }
        Mono { Layout.fillWidth: true; text: "Log file:  " + (backend.diagnostics.log || "var/log/kalshi-hunter.log"); elide: Text.ElideMiddle }
        Btn { text: "Done"; primary: true; Layout.alignment: Qt.AlignRight; onClicked: dlg.close() }
    }
}
