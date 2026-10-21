import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Record a trade you ALREADY executed on Kalshi. This does not place, change or cancel anything.
Popup {
    id: dlg
    objectName: "record_dialog"
    modal: true
    focus: true
    anchors.centerIn: Overlay.overlay
    width: Math.min(620, Overlay.overlay ? Overlay.overlay.width - 40 : 620)
    padding: 24
    closePolicy: Popup.CloseOnEscape
    property string resultText: ""
    property bool resultOk: true
    background: Rectangle { color: Theme.panel; radius: Theme.radius; border.color: Theme.borderStrong }
    Overlay.modal: Rectangle { color: "#a0050a10" }
    onOpened: { resultText = ""; ticker.forceActiveFocus() }
    Connections {
        target: backend
        function onActionDone(name, result) {
            if (name !== "record") return
            dlg.resultOk = result.ok
            dlg.resultText = result.ok ? result.summary : result.error
        }
    }
    component Field: TextField {
        property string accessibleName: placeholderText
        Layout.fillWidth: true
        placeholderTextColor: Theme.faint
        color: Theme.ink
        selectByMouse: true
        Accessible.name: accessibleName
        background: Rectangle { color: Theme.input; radius: Theme.radiusSm; border.color: parent && parent.activeFocus ? Theme.accent : Theme.borderStrong }
    }
    contentItem: ColumnLayout {
        spacing: 12
        Accessible.role: Accessible.Dialog
        Accessible.name: "Record an executed trade"
        Txt { text: "Record an executed trade"; font.pixelSize: Theme.fsXl - 4; font.weight: Font.DemiBold }
        Banner { Layout.fillWidth: true; kind: "warn"; text: "This only writes a line in YOUR ledger on this computer. Kalshi Hunter never places, changes or cancels orders. Enter what actually happened on Kalshi." }
        GridLayout {
            Layout.fillWidth: true
            columns: 2
            columnSpacing: 12
            rowSpacing: 10
            Field { id: ticker; placeholderText: "Market ticker (e.g. CONTROLS-2026-D)"; Layout.columnSpan: 2 }
            Select { id: side; accessibleName: "Side"; Layout.fillWidth: true; model: [{value: "yes", label: "YES contracts"}, {value: "no", label: "NO contracts"}]; Component.onCompleted: select("yes") }
            Select { id: action; accessibleName: "Action"; Layout.fillWidth: true; model: [{value: "buy", label: "Bought"}, {value: "sell", label: "Sold"}]; Component.onCompleted: select("buy") }
            Field { id: count; placeholderText: "Contracts (e.g. 10)"; validator: DoubleValidator { bottom: 0; decimals: 4 } }
            Field { id: price; placeholderText: "Price in cents (e.g. 35 or 9.3)"; validator: DoubleValidator { bottom: 0; top: 100; decimals: 4 } }
            Field { id: fee; placeholderText: "Fee paid in dollars (e.g. 0.17)"; validator: DoubleValidator { bottom: 0; decimals: 4 } }
            Field { id: when; placeholderText: "When (blank = now; or 2026-10-21 14:05 in Chicago time)" }
        }
        Banner { Layout.fillWidth: true; kind: dlg.resultOk ? "info" : "error"; text: dlg.resultText }
        RowLayout {
            Layout.alignment: Qt.AlignRight
            spacing: 10
            Btn { text: "Close"; onClicked: dlg.close() }
            Btn { text: "Save to my ledger"; primary: true; enabled: ticker.text.length > 0 && count.text.length > 0 && price.text.length > 0
                     onClicked: backend.recordFill(ticker.text, side.currentValue || "yes", action.currentValue || "buy", count.text, price.text, fee.text, when.text) }
        }
    }
}
