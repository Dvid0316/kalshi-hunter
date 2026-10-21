import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

Item {
    id: page
    readonly property bool narrow: width < 1060
    property bool fill: !narrow
    property int minHeight: 560
    implicitHeight: narrow ? 1300 : 560
    readonly property var payload: backend.alerts
    readonly property var cand: payload.candidates || ({rows: [], total: 0, offset: 0, sort: "edge"})
    property int selectedId: -1
    readonly property var selected: {
        var rows = cand.rows || []
        for (var i = 0; i < rows.length; i++) if (rows[i].id === selectedId) return rows[i]
        return rows.length ? rows[0] : null
    }
    Connections { target: backend; function onStepPageRequested(d) { if (backend.ui.page === "Alerts") backend.pageCandidates(d) } }

    GridLayout {
        anchors.fill: parent
        columns: page.narrow ? 1 : 2
        columnSpacing: Theme.gap
        rowSpacing: Theme.gap
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: !page.narrow
            Layout.preferredHeight: page.narrow ? 720 : -1
            Layout.preferredWidth: 640
            spacing: 12
            Panel {
                Layout.fillWidth: true
                implicitHeight: statusCol.implicitHeight + 36
                ColumnLayout {
                    id: statusCol
                    anchors.fill: parent
                    anchors.margins: 18
                    spacing: 8
                    RowLayout {
                        Layout.fillWidth: true
                        Txt { text: (page.payload.count || 0) + " qualified alerts in this snapshot"; font.pixelSize: Theme.fsLg; font.weight: Font.DemiBold; Layout.fillWidth: true }
                        Tag { label: "HISTORICAL · NOT A LIVE FEED"; tint: Theme.warn }
                    }
                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.muted; font.pixelSize: Theme.fsSm + 1; lineHeight: 1.35
                           text: (page.payload.count || 0) === 0
                                 ? "No alert passed the auditor's depth, fee and ambiguity checks in the preserved data. Live research and notification delivery need a separately approved integration (see docs/LIVE_RESEARCH_INTEGRATION.md)."
                                 : "Alerts below were approved by the auditor at the time shown. They are historical and must be re-checked against current prices before any decision." }
                    Repeater {
                        model: page.payload.alerts || []
                        delegate: RowLayout { required property var modelData; Layout.fillWidth: true
                            Mono { text: modelData.ticker; Layout.fillWidth: true } Mono { text: modelData.side.toUpperCase() + " @ " + modelData.price } Small { text: modelData.when } }
                    }
                }
            }
            Panel {
                Layout.fillWidth: true
                Layout.fillHeight: true
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 8
                    RowLayout {
                        Layout.fillWidth: true
                        Txt { text: "Screened candidates"; font.pixelSize: Theme.fsLg; font.weight: Font.DemiBold; Layout.fillWidth: true }
                        Tag { label: "NOT ALERTS"; tint: Theme.warn }
                    }
                    Small { Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone; font.pixelSize: Theme.fsXs
                            text: "Structural screens from the scanner: buying every YES in a mutually-exclusive event costs less than the $1 it would pay IF exactly one outcome must occur. That 'if' was never verified, so none of these is an arbitrage claim." }
                    DataTable {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        accessibleName: "Screened candidates"
                        rowHeight: 52
                        emptyText: "No screened candidates."
                        busy: backend.ui.loading.indexOf("alerts") >= 0
                        rows: page.cand.rows || []
                        keyField: "id"
                        selectedKey: page.selected ? String(page.selected.id) : ""
                        sortKey: page.cand.sort === "event" ? "event" : "edge"
                        sortDesc: page.cand.sort === "edge"
                        columns: [
                            {key: "event", title: "Event", fill: true, sub: "kind", sortKey: "event"},
                            {key: "edge", title: "Gross gap", width: 90, mono: true, align: "right", tone: "accent", sortKey: "edge"},
                            {key: "cost", title: "Cost", width: 70, mono: true, align: "right"},
                            {key: "n_legs", title: "Legs", width: 48, mono: true, align: "right"}
                        ]
                        onSortRequested: function (k) { backend.sortCandidates(k) }
                        onRowClicked: function (row) { page.selectedId = row.id }
                    }
                    Pager {
                        Layout.fillWidth: true
                        page: Math.floor((page.cand.offset || 0) / 30) + 1
                        pages: Math.max(1, Math.ceil((page.cand.total || 0) / 30))
                        total: page.cand.total || 0
                        unit: "candidates"
                        onPrevious: backend.pageCandidates(-1)
                        onNext: backend.pageCandidates(1)
                    }
                }
            }
        }
        Panel {
            Layout.fillWidth: true
            Layout.fillHeight: !page.narrow
            Layout.preferredHeight: page.narrow ? 520 : -1
            Layout.preferredWidth: 440
            ScrollView {
                id: sv
                anchors.fill: parent
                anchors.margins: 18
                contentWidth: availableWidth
                clip: true
                ColumnLayout {
                    width: sv.availableWidth
                    spacing: 10
                    EmptyState { visible: !page.selected; Layout.fillWidth: true; heading: "No candidate selected"; description: "Pick a screened candidate to see its legs." }
                    ColumnLayout {
                        visible: !!page.selected
                        Layout.fillWidth: true
                        spacing: 10
                        Tag { label: page.selected ? page.selected.status.replace("_", " ") : ""; tint: Theme.warn }
                        Txt { text: page.selected ? page.selected.event : ""; font.pixelSize: Theme.fsLg; font.weight: Font.DemiBold; Layout.fillWidth: true }
                        Small { Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone
                                text: page.selected ? ("Buying YES on all " + page.selected.n_legs + " listed outcomes would cost " + page.selected.cost + " per set at the screened prices (a gross gap of " + page.selected.edge + " against the $1 payout, before fees and depth). It pays $1 only if the outcome set is exhaustive and exactly one resolves YES. Neither is verified.") : "" }
                        Small { text: "LEGS AT SCAN TIME"; font.pixelSize: Theme.fsXs; font.letterSpacing: 1 }
                        Repeater {
                            model: page.selected ? page.selected.legs : []
                            delegate: RowLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                spacing: 8
                                Mono { text: modelData.ticker; Layout.fillWidth: true; elide: Text.ElideMiddle; font.pixelSize: Theme.fsXs + 1 }
                                Mono { text: modelData.side.toUpperCase() + " " + modelData.price; color: Theme.accent }
                                Btn { text: "Open"; implicitWidth: 52; implicitHeight: 24; onClicked: { backend.select(modelData.ticker); backend.navigate("Markets") }
                                      Accessible.name: "Open market " + modelData.ticker }
                            }
                        }
                        Small { Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone; font.pixelSize: Theme.fsXs; text: "Screened " + (page.selected ? page.selected.when : "") + ". Prices are those archived at that scan." }
                    }
                }
            }
        }
    }
}
