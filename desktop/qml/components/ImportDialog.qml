import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import ".."

// Import trades YOU executed from a local CSV/JSON file. Nothing is sent anywhere.
Popup {
    id: dlg
    objectName: "import_dialog"
    modal: true
    focus: true
    anchors.centerIn: Overlay.overlay
    width: Math.min(660, Overlay.overlay ? Overlay.overlay.width - 40 : 660)
    padding: 24
    closePolicy: Popup.CloseOnEscape
    property string resultText: ""
    property bool resultOk: true
    background: Rectangle { color: Theme.panel; radius: Theme.radius; border.color: Theme.borderStrong }
    Overlay.modal: Rectangle { color: "#a0050a10" }
    onOpened: { resultText = ""; path.forceActiveFocus() }
    Connections {
        target: backend
        function onActionDone(name, result) {
            if (name !== "import") return
            dlg.resultOk = result.ok
            dlg.resultText = result.ok ? (result.summary + (result.rejects && result.rejects.length ? "\nFirst problems:\n" + result.rejects.map(function (r) { return "• " + r.reason }).join("\n") : "")) : result.error
        }
    }
    FileDialog {
        id: picker
        title: "Choose a CSV or JSON file of your trades"
        nameFilters: ["Trade files (*.csv *.json)", "All files (*)"]
        onAccepted: path.text = selectedFile.toString().replace("file://", "")
    }
    contentItem: ColumnLayout {
        spacing: 12
        Accessible.role: Accessible.Dialog
        Accessible.name: "Import trades from a file"
        Txt { text: "Import trades from a file"; font.pixelSize: Theme.fsXl - 4; font.weight: Font.DemiBold }
        Small { Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone
                text: "Reads a local file with your fills, settlements or deposits/withdrawals (columns listed in docs/ACCOUNT_DATA_CONTRACT.md). Safe to repeat: records already present are skipped, conflicting copies are kept out and flagged. No account login, no network." }
        RowLayout {
            Layout.fillWidth: true
            TextField {
                id: path
                Layout.fillWidth: true
                placeholderText: "/path/to/fills.csv"
                placeholderTextColor: Theme.faint
                color: Theme.ink
                selectByMouse: true
                Accessible.name: "File path"
                background: Rectangle { color: Theme.input; radius: Theme.radiusSm; border.color: path.activeFocus ? Theme.accent : Theme.borderStrong; border.width: path.activeFocus ? 2 : 1 }
                onAccepted: go.clicked()
            }
            Btn { text: "Browse…"; implicitWidth: 90; onClicked: picker.open() }
        }
        RowLayout {
            spacing: 14
            Select { id: kind; accessibleName: "File contents"; implicitWidth: 200
                     model: [{value: "", label: "Detect automatically"}, {value: "fills", label: "Fills (trades)"}, {value: "settlements", label: "Settlements"}, {value: "cash", label: "Deposits / withdrawals"}]
                     Component.onCompleted: select("") }
            Select { id: unit; accessibleName: "Price unit"; implicitWidth: 180
                     model: [{value: "dollars", label: "Prices in dollars (0.40)"}, {value: "cents", label: "Prices in cents (40)"}]
                     Component.onCompleted: select("dollars") }
        }
        Banner { Layout.fillWidth: true; kind: dlg.resultOk ? "info" : "error"; text: dlg.resultText }
        RowLayout {
            Layout.alignment: Qt.AlignRight
            spacing: 10
            Btn { text: "Close"; onClicked: dlg.close() }
            Btn { id: go; text: "Import"; primary: true; enabled: path.text.length > 0
                     onClicked: backend.importFile(path.text, kind.currentValue, unit.currentValue || "dollars") }
        }
    }
}
