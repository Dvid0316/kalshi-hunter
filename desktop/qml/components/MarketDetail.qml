import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Right-hand market detail: quotes, history, settlement rules, linked research and forecasts.
ScrollView {
    id: sv
    property var d: backend.detail
    property string side: "yes"
    property string tab: "Rules"
    contentWidth: availableWidth
    clip: true
    Accessible.role: Accessible.Pane
    Accessible.name: "Market detail" + (d && d.ticker ? " for " + d.ticker : "")
    ColumnLayout {
        width: sv.availableWidth
        spacing: 14
        EmptyState { visible: !sv.d || !sv.d.ticker; Layout.fillWidth: true; Layout.preferredHeight: 200
                     heading: backend.ui.loading.indexOf("detail") >= 0 ? "Loading market…" : "Select a market"
                     description: "Pick a row to see its executable quotes, settlement rules and linked research."
                     busy: backend.ui.loading.indexOf("detail") >= 0 }
        ColumnLayout {
            visible: !!sv.d && !!sv.d.ticker
            Layout.fillWidth: true
            spacing: 14
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Tag { label: sv.d.status || ""; tint: sv.d.status === "active" ? Theme.accent : Theme.muted }
                Tag { visible: !!sv.d.result; label: "Result: " + (sv.d.result || ""); tint: Theme.gain }
                Tag { label: sv.d.freshness || ""; tint: Theme.warn }
                Item { Layout.fillWidth: true }
            }
            Text { Layout.fillWidth: true; text: sv.d.title || ""; color: Theme.ink; font.pixelSize: Theme.fsXl - 2; font.weight: Font.DemiBold; wrapMode: Text.WordWrap
                   Accessible.role: Accessible.Heading; Accessible.name: text }
            Small { visible: !!sv.d.subtitle; text: sv.d.subtitle || ""; Layout.fillWidth: true; font.pixelSize: Theme.fsSm + 1; wrapMode: Text.WordWrap; elide: Text.ElideNone }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Mono { text: sv.d.ticker || ""; color: Theme.muted; Layout.fillWidth: true; elide: Text.ElideMiddle }
                Btn { text: "Copy ticker"; implicitWidth: 92; implicitHeight: 26; onClicked: backend.copyText(sv.d.ticker) }
            }
            Small { Layout.fillWidth: true; font.pixelSize: Theme.fsXs; text: (sv.d.category || "") + "  ·  event " + (sv.d.event_ticker || "") + (sv.d.siblings > 1 ? " (" + sv.d.siblings + " markets)" : "") }

            QuoteCard { Layout.fillWidth: true; quote: sv.d.quote || null }

            Panel {
                Layout.fillWidth: true
                implicitHeight: chartCol.implicitHeight + 2 * Theme.pad
                ColumnLayout {
                    id: chartCol
                    anchors.fill: parent
                    anchors.margins: Theme.pad
                    spacing: 8
                    RowLayout {
                        Layout.fillWidth: true
                        Txt { text: "Price history"; font.weight: Font.DemiBold; Layout.fillWidth: true }
                        SegmentedControl { options: [{value: "yes", label: "YES"}, {value: "no", label: "NO"}]; current: sv.side; accessibleName: "Chart side"; onPicked: function (v) { sv.side = v } }
                    }
                    PriceChart { Layout.fillWidth: true; Layout.preferredHeight: 210; points: sv.d.points || []; side: sv.side; objectName: "detail_chart" }
                    Row { spacing: 14
                        Row { spacing: 5; Rectangle { width: 12; height: 3; color: Theme.accent; anchors.verticalCenter: parent.verticalCenter } Small { text: (sv.side === "yes" ? "YES" : "NO") + " ask (buy)"; font.pixelSize: Theme.fsXs } }
                        Row { spacing: 5; Rectangle { width: 12; height: 3; color: Theme.accent2; anchors.verticalCenter: parent.verticalCenter } Small { text: (sv.side === "yes" ? "YES" : "NO") + " bid (sell)"; font.pixelSize: Theme.fsXs } } }
                    Small { Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone; font.pixelSize: Theme.fsXs
                            text: (sv.d.n_points || 0) + " two-sided archived snapshots of " + (sv.d.n_snapshots || 0) + ", " + (sv.d.span || "") + ". Lines join archived snapshots only; they do not imply trades in between." }
                }
            }

            SegmentedControl {
                options: [{value: "Rules", label: "Rules"}, {value: "Research", label: "Research (" + (sv.d.research || []).length + ")"}, {value: "Forecasts", label: "Forecasts (" + (sv.d.forecasts || []).length + ")"}]
                current: sv.tab
                accessibleName: "Detail section"
                onPicked: function (v) { sv.tab = v }
            }
            ColumnLayout {
                visible: sv.tab === "Rules"
                Layout.fillWidth: true
                spacing: 10
                Txt { text: "Settlement rules"; font.weight: Font.DemiBold }
                Text { Layout.fillWidth: true; text: sv.d.rules || ""; wrapMode: Text.WordWrap; color: Theme.muted; font.pixelSize: Theme.fsSm + 1; lineHeight: 1.4 }
                Text { visible: !!sv.d.secondary; Layout.fillWidth: true; text: sv.d.secondary || ""; wrapMode: Text.WordWrap; color: Theme.muted; font.pixelSize: Theme.fsSm + 1; lineHeight: 1.4 }
                GridLayout {
                    Layout.fillWidth: true
                    columns: 2
                    columnSpacing: 14
                    rowSpacing: 6
                    Small { text: "Closes" } Mono { text: sv.d.close_text || "—"; Layout.fillWidth: true }
                    Small { text: "Time to close" } Mono { text: sv.d.time_to_close || "—"; Layout.fillWidth: true }
                    Small { text: "Expected expiration" } Mono { text: sv.d.expected_expiration || "—"; Layout.fillWidth: true }
                    Small { visible: !!sv.d.strike; text: "Strike" } Mono { visible: !!sv.d.strike; text: sv.d.strike || ""; Layout.fillWidth: true }
                    Small { text: "Series" } Mono { text: sv.d.series || "—"; Layout.fillWidth: true }
                }
                Small { Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone; font.pixelSize: Theme.fsXs
                        text: "Rules and close times are as preserved in the snapshot. Kalshi may have amended them since; confirm on Kalshi before trading." }
            }
            ColumnLayout {
                visible: sv.tab === "Research"
                Layout.fillWidth: true
                spacing: 10
                Small { visible: (sv.d.research || []).length === 0; text: "No Grok research is linked to this market."; Layout.fillWidth: true }
                Repeater { model: sv.d.research || []; delegate: ResearchRecord { required property var modelData; record: modelData } }
            }
            ColumnLayout {
                visible: sv.tab === "Forecasts"
                Layout.fillWidth: true
                spacing: 10
                Banner { kind: "warn"; text: "Experimental paper forecasts. They are not verified trading edges and are not your positions." }
                Small { visible: (sv.d.forecasts || []).length === 0; text: "No paper forecast has been recorded for this market."; Layout.fillWidth: true }
                Repeater { model: sv.d.forecasts || []; delegate: ForecastCard { required property var modelData; card: modelData; showTitle: false; selected: true } }
            }
        }
    }
}
