import QtQuick
import QtQuick.Layouts
import ".."
import "../components"

ColumnLayout {
    id: page
    property bool fill: false
    readonly property var ov: backend.overview
    readonly property var research: ov.cohorts ? ov.cohorts.research : ({rows: [], forecasts_total: 0, resolved: 0})
    readonly property var strategy: ov.cohorts ? ov.cohorts.strategy : ({rows: [], forecasts_total: 0, resolved: 0})
    readonly property var summary: backend.positions.summary || ({})
    readonly property var counts: ov.counts || ({})
    readonly property bool wide: width > 1000
    spacing: Theme.gap

    function distinctEvents(rows) {
        var seen = {}, n = 0
        for (var i = 0; i < rows.length; i++) { if (!seen[rows[i].series]) { seen[rows[i].series] = true; n++ } }
        return n
    }

    GridLayout {
        Layout.fillWidth: true
        columns: page.width > 1080 ? 4 : 2
        columnSpacing: 14
        rowSpacing: 14
        Metric { Layout.fillWidth: true; label: "Snapshot market universe"; value: page.counts.markets !== undefined ? Number(page.counts.markets).toLocaleString(Qt.locale("en_US"), "f", 0) : "—"
                 note: "Catalog records, incl. closed & dropped" }
        Metric { Layout.fillWidth: true; label: "Track A · Research forecasts"; value: String(page.research.forecasts_total); valueColor: Theme.accent
                 note: "Paper entries · " + page.research.resolved + " resolved" }
        Metric { Layout.fillWidth: true; label: "Track B · Strategy forecasts"; value: String(page.strategy.forecasts_total); valueColor: Theme.accent2
                 note: "Paper entries · " + page.distinctEvents(page.strategy.rows || []) + " distinct event(s) · " + page.strategy.resolved + " resolved" }
        Metric { Layout.fillWidth: true; label: backend.ui.sample ? "SAMPLE realized P&L" : "Your realized P&L (ledger)"; value: page.summary.realized || "Unavailable"
                 valueColor: backend.ui.sample ? Theme.sample : (page.summary.realized && page.summary.realized !== "Unavailable" ? Theme.ink : Theme.muted)
                 note: page.summary.realized_note || "Account not connected" }
    }

    GridLayout {
        Layout.fillWidth: true
        columns: page.wide ? 2 : 1
        columnSpacing: Theme.gap
        rowSpacing: Theme.gap
        Panel {
            Layout.fillWidth: true
            Layout.preferredWidth: 700
            Layout.preferredHeight: 420
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 20
                spacing: 10
                RowLayout {
                    Layout.fillWidth: true
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Txt { text: "Market history"; font.pixelSize: Theme.fsLg; font.weight: Font.DemiBold }
                        Small { text: (backend.detail.title || "") ; Layout.fillWidth: true }
                    }
                    Tag { label: "ARCHIVED QUOTES"; tint: Theme.warn }
                    Btn { text: "Open in Markets"; implicitWidth: 130; onClicked: backend.navigate("Markets") }
                }
                PriceChart { id: chart; Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 160; points: backend.detail.points || []; side: "yes" }
                Small { Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone; font.pixelSize: Theme.fsXs
                        text: (backend.detail.ticker || "") + "  ·  " + (backend.detail.n_points || 0) + " snapshots  ·  " + (backend.detail.span || "") + "  ·  YES bid/ask shown" }
            }
        }
        Panel {
            Layout.fillWidth: true
            Layout.preferredWidth: 360
            Layout.preferredHeight: 420
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 20
                spacing: 11
                Txt { text: "Snapshot health"; font.pixelSize: Theme.fsLg; font.weight: Font.DemiBold }
                RowLayout {
                    spacing: 8
                    Tag { label: page.ov.freshness ? page.ov.freshness.label : "…"; tint: Theme.warn }
                    Tag { label: (page.ov.integrity_errors || []).length ? "INTEGRITY ISSUES" : "HASH CHAIN VERIFIED"; tint: (page.ov.integrity_errors || []).length ? Theme.danger : Theme.accent }
                }
                Small { Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone; text: page.ov.freshness ? page.ov.freshness.detail : "" }
                Small { Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone
                        text: page.ov.coverage ? page.ov.coverage.scans + " scans, " + page.ov.coverage.first + " → " + page.ov.coverage.last : "" }
                Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
                Small { text: "Markets by category" }
                Repeater {
                    model: (page.ov.categories || []).slice(0, 5)
                    delegate: ColumnLayout {
                        required property var modelData
                        required property int index
                        Layout.fillWidth: true
                        spacing: 4
                        RowLayout { Small { text: modelData.name; Layout.fillWidth: true } Mono { text: Number(modelData.count).toLocaleString(Qt.locale("en_US"), "f", 0); font.pixelSize: Theme.fsXs + 1 } }
                        Rectangle { Layout.fillWidth: true; height: 5; radius: 2; color: "#26354a"
                            Rectangle { width: parent.width * modelData.count / Math.max(1, page.ov.categories[0].count); height: 5; radius: 2; color: index === 0 ? Theme.accent : "#6385a8" } }
                    }
                }
                Item { Layout.fillHeight: true }
            }
        }
    }

    Panel {
        Layout.fillWidth: true
        implicitHeight: tableCol.implicitHeight + 40
        ColumnLayout {
            id: tableCol
            anchors.fill: parent
            anchors.margins: 20
            spacing: 8
            RowLayout {
                Layout.fillWidth: true
                Txt { text: "Track A · Research forecasts"; font.pixelSize: Theme.fsLg; font.weight: Font.DemiBold; Layout.fillWidth: true }
                Tag { label: "PAPER ONLY · EXPERIMENTAL"; tint: Theme.warn }
                Btn { text: "Open research"; onClicked: backend.navigate("Research") }
            }
            DataTable {
                Layout.fillWidth: true
                autoHeight: true
                accessibleName: "Research forecasts"
                rows: page.research.rows || []
                selectedKey: backend.ui.selectedTicker
                columns: [
                    {key: "ticker", title: "Market", fill: true, sub: "status"},
                    {key: "side", title: "Side", width: 56, tone: "accent"},
                    {key: "probability", title: "P(YES)", width: 76, mono: true, align: "right"},
                    {key: "price", title: "Paper fill", width: 82, mono: true, align: "right"},
                    {key: "qty", title: "Qty", width: 48, mono: true, align: "right"},
                    {key: "pnl_text", title: "Paper P&L", width: 96, mono: true, align: "right", tone: "muted"}
                ]
                onRowClicked: function (row) { backend.select(row.ticker) }
                onRowActivated: function (row) { backend.select(row.ticker); backend.navigate("Research") }
            }
        }
    }
}
