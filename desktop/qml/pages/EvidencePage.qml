import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

// Provenance, integrity, preserved documents and diagnostics.
Item {
    id: page
    property bool fill: false
    implicitHeight: col.implicitHeight
    readonly property var ov: backend.overview
    readonly property var counts: ov.counts || ({})
    readonly property var errors: ov.integrity_errors || []
    readonly property var dq: backend.quality
    readonly property var dg: backend.diagnostics
    readonly property var doc: backend.document

    ColumnLayout {
        id: col
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: Theme.gap
        GridLayout {
            Layout.fillWidth: true
            columns: page.width > 1000 ? 2 : 1
            columnSpacing: Theme.gap
            rowSpacing: Theme.gap
            Panel {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                implicitHeight: intCol.implicitHeight + 44
                ColumnLayout {
                    id: intCol
                    anchors.fill: parent
                    anchors.margins: 22
                    spacing: 10
                    Txt { text: "Evidence integrity"; font.pixelSize: Theme.fsXl - 2; font.weight: Font.DemiBold }
                    Tag { label: page.errors.length ? "VERIFICATION ISSUES (" + page.errors.length + ")" : "HASH CHAIN VERIFIED"; tint: page.errors.length ? Theme.danger : Theme.accent }
                    Repeater { model: page.errors; delegate: Text { required property string modelData; Layout.fillWidth: true; text: "• " + modelData; wrapMode: Text.WordWrap; color: Theme.danger; font.pixelSize: Theme.fsSm } }
                    Small { Layout.fillWidth: true; font.pixelSize: Theme.fsXs; wrapMode: Text.WordWrap; elide: Text.ElideNone
                            text: "Checked " + (page.ov.integrity_checked || "—") + " against the preserved snapshot and checkpoint log (read-only). A valid local hash chain proves internal consistency only: not that the research was right, and not an independently timestamped history." }
                    Repeater {
                        model: [["Protected chain entries", page.counts.hash_chain], ["Snapshot observations", page.counts.snapshots], ["Markets in catalog", page.counts.markets],
                                ["Scans", page.counts.scans], ["Source research records", page.counts.research], ["Screened candidates", page.counts.candidates],
                                ["Alerts", page.counts.alerts], ["Resolutions", page.counts.resolutions], ["Unclassified forecasts", page.ov.unknown_forecasts]]
                        delegate: RowLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            Small { text: modelData[0]; Layout.fillWidth: true }
                            Mono { text: modelData[1] === undefined ? "—" : Number(modelData[1]).toLocaleString(Qt.locale("en_US"), "f", 0) }
                        }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
                    Txt { text: "Naming map"; font.weight: Font.DemiBold }
                    Small { Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone; lineHeight: 1.4
                            text: "Track A · Research forecasts = legacy B/C.\nTrack B · Strategy forecasts = legacy C2 (flb_v1).\nHistorical backtests = legacy A: separate, inconclusive, never pooled." }
                }
            }
            Panel {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                implicitHeight: scanCol.implicitHeight + 44
                ColumnLayout {
                    id: scanCol
                    anchors.fill: parent
                    anchors.margins: 22
                    spacing: 8
                    Txt { text: "Preserved scan history"; font.pixelSize: Theme.fsXl - 2; font.weight: Font.DemiBold }
                    Small { text: "Historical completions of the cloud scanner · not current service health"; Layout.fillWidth: true }
                    Repeater {
                        model: page.ov.scans || []
                        delegate: ColumnLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: 3
                            RowLayout { Mono { text: modelData.time; Layout.fillWidth: true; font.pixelSize: Theme.fsXs + 1 } Tag { label: modelData.status; tint: modelData.status === "ok" ? Theme.accent : Theme.warn } }
                            Small { text: Number(modelData.markets).toLocaleString(Qt.locale("en_US"), "f", 0) + " markets scanned"; font.pixelSize: Theme.fsXs }
                            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
                        }
                    }
                }
            }
        }

        Panel {
            Layout.fillWidth: true
            Layout.preferredHeight: 520
            RowLayout {
                anchors.fill: parent
                anchors.margins: 18
                spacing: 16
                ColumnLayout {
                    Layout.preferredWidth: 300
                    Layout.fillHeight: true
                    spacing: 8
                    Txt { text: "Preserved documents"; font.pixelSize: Theme.fsLg; font.weight: Font.DemiBold }
                    Small { text: "Read-only copies from the research archive."; Layout.fillWidth: true; font.pixelSize: Theme.fsXs }
                    DataTable {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        accessibleName: "Documents"
                        rowHeight: 40
                        keyField: "name"
                        selectedKey: page.doc.name || ""
                        emptyText: "No documents found."
                        busy: backend.ui.loading.indexOf("documents") >= 0
                        rows: backend.documents
                        columns: [{key: "name", title: "File", fill: true}]
                        onRowClicked: function (row) { backend.openDocument(row.name) }
                        onRowActivated: function (row) { backend.openDocument(row.name) }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 8
                    RowLayout {
                        Layout.fillWidth: true
                        Txt { text: page.doc.name || "Select a document"; Layout.fillWidth: true; font.weight: Font.DemiBold }
                        Tag { visible: !!page.doc.name; label: "READ ONLY"; tint: Theme.muted }
                        Btn { visible: !!page.doc.text; text: "Copy"; implicitWidth: 64; implicitHeight: 26; onClicked: backend.copyText(page.doc.text) }
                    }
                    Banner { kind: "warn"; text: page.doc.truncated ? "Showing the first 200 KB of this document." : (page.doc.error || "") }
                    ScrollView {
                        id: docScroll
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        TextArea {
                            readOnly: true
                            selectByMouse: true
                            wrapMode: TextEdit.Wrap
                            text: page.doc.text || ""
                            color: Theme.ink
                            font.family: Theme.mono
                            font.pixelSize: Theme.fsSm + 1
                            Accessible.name: "Document text"
                            background: Rectangle { color: Theme.input; radius: Theme.radiusSm; border.color: Theme.border }
                        }
                    }
                }
            }
        }

        GridLayout {
            Layout.fillWidth: true
            columns: page.width > 1000 ? 2 : 1
            columnSpacing: Theme.gap
            rowSpacing: Theme.gap
            Panel {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                implicitHeight: dqCol.implicitHeight + 40
                ColumnLayout {
                    id: dqCol
                    anchors.fill: parent
                    anchors.margins: 20
                    spacing: 7
                    RowLayout { Layout.fillWidth: true; Txt { text: "Your ledger: data quality"; font.pixelSize: Theme.fsLg; font.weight: Font.DemiBold; Layout.fillWidth: true }
                                Tag { label: page.dq.empty ? "NO ACCOUNT DATA" : (page.dq.ok ? "NO BLOCKING ISSUES" : "ISSUES FOUND"); tint: page.dq.empty ? Theme.muted : (page.dq.ok ? Theme.accent : Theme.warn) } }
                    Repeater { model: (page.dq.items || []).slice(0, 10); delegate: Text { required property var modelData; Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: Theme.fsSm
                               color: modelData.level === "error" ? Theme.danger : (modelData.level === "warn" ? Theme.warn : Theme.muted); text: "• " + modelData.message } }
                    Repeater { model: (page.dq.rejects || []).slice(0, 5); delegate: Small { required property var modelData; Layout.fillWidth: true; text: "Rejected: " + modelData.reason; color: Theme.warn } }
                    Small { text: "Imports"; font.pixelSize: Theme.fsXs; font.letterSpacing: 1; visible: (page.dq.batches || []).length > 0 }
                    Repeater { model: (page.dq.batches || []).slice(0, 5); delegate: Small { required property var modelData; Layout.fillWidth: true; font.pixelSize: Theme.fsXs
                               text: modelData.when + " · " + modelData.kind + " · " + (modelData.label || modelData.source) + " · " + modelData.new + " new, " + modelData.dup + " dup, " + modelData.conflict + " conflict, " + modelData.rejected + " rejected" } }
                    Small { visible: page.dq.empty === true; text: "Nothing imported yet."; Layout.fillWidth: true }
                }
            }
            Panel {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                implicitHeight: dgCol.implicitHeight + 40
                ColumnLayout {
                    id: dgCol
                    anchors.fill: parent
                    anchors.margins: 20
                    spacing: 7
                    Txt { text: "Diagnostics"; font.pixelSize: Theme.fsLg; font.weight: Font.DemiBold }
                    Repeater {
                        model: [["Python", page.dg.python], ["Qt / PySide6", (page.dg.qt || "") + " / " + (page.dg.pyside || "")], ["SQLite", page.dg.sqlite], ["Platform", page.dg.platform],
                                ["Snapshot", page.dg.snapshot], ["Account DB", backend.account_status.path], ["Log file", page.dg.log],
                                ["Account connection", "Disabled · no credentials stored"], ["Scanner / supervisor", "None. This app has no scanner."]]
                        delegate: RowLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: 10
                            Small { text: modelData[0]; Layout.preferredWidth: 130 }
                            Mono { text: modelData[1] || "—"; Layout.fillWidth: true; font.pixelSize: Theme.fsXs + 1; elide: Text.ElideMiddle }
                        }
                    }
                }
            }
        }
    }
}
