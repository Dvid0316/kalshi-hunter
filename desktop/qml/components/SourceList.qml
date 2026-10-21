import QtQuick
import QtQuick.Layouts
import ".."

// Source URLs as plain text with Copy / Open. Kalshi Hunter never fetches these pages itself.
ColumnLayout {
    id: list
    property var urls: []
    spacing: 6
    Repeater {
        model: list.urls
        delegate: RowLayout {
            required property string modelData
            Layout.fillWidth: true
            spacing: 8
            Mono {
                Layout.fillWidth: true
                text: modelData
                color: "#8cc3e6"
                font.pixelSize: Theme.fsXs + 1
                elide: Text.ElideMiddle
                Accessible.role: Accessible.StaticText
                Accessible.name: "Source " + modelData
            }
            Btn { text: "Copy"; implicitWidth: 56; implicitHeight: 26; onClicked: backend.copyText(modelData); Accessible.name: "Copy link " + modelData }
            Btn { text: "Open"; implicitWidth: 56; implicitHeight: 26; onClicked: backend.openLink(modelData)
                     Accessible.name: "Open link " + modelData; Accessible.description: backend.ui.allowLinks ? "Opens in your browser" : "Link opening is off in Settings; copies instead" }
        }
    }
    Small { visible: list.urls.length === 0; text: "No source links recorded."; font.pixelSize: Theme.fsXs }
}
