import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

// Research (Track A) and Strategy (Track B) share this page; backend.ui.cohort picks the cohort.
Item {
    id: page
    readonly property bool narrow: width < 1060
    property bool fill: !narrow
    property int minHeight: 560
    implicitHeight: narrow ? 1500 : 560
    readonly property string cohort: backend.ui.cohort
    readonly property bool isResearch: cohort === "research"
    readonly property var cards: (backend.cards[cohort] || [])
    readonly property var stats: backend.overview.cohorts ? backend.overview.cohorts[cohort] : ({forecasts_total: 0, resolved: 0, rows: [], cost: 0})
    readonly property int events: {
        var seen = {}, n = 0, rows = stats.rows || []
        for (var i = 0; i < rows.length; i++) if (!seen[rows[i].series]) { seen[rows[i].series] = true; n++ }
        return n
    }

    GridLayout {
        anchors.fill: parent
        columns: page.narrow ? 1 : 2
        columnSpacing: Theme.gap
        rowSpacing: Theme.gap
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: !page.narrow
            Layout.preferredHeight: page.narrow ? 700 : -1
            Layout.preferredWidth: 520
            spacing: 12
            GridLayout {
                Layout.fillWidth: true
                columns: 3
                columnSpacing: 12
                Metric { Layout.fillWidth: true; label: "Paper entries"; value: String(page.stats.forecasts_total); valueColor: page.isResearch ? Theme.accent : Theme.accent2
                         note: page.isResearch ? "Researched forecasts" : "Frozen flb_v1 · " + page.events + " event(s)" }
                Metric { Layout.fillWidth: true; label: "Resolved outcomes"; value: String(page.stats.resolved); note: "Accuracy needs outcomes" }
                Metric { Layout.fillWidth: true; label: "Entry cost incl. fees"; value: "$" + Number(page.stats.cost || 0).toFixed(2); note: "Paper cost · not exposure" }
            }
            Banner {
                kind: "warn"
                text: page.isResearch
                      ? "Experimental estimates. Recorded paper forecasts are not verified trading edges, and several were wider than the market's own bid–ask. They are not your positions."
                      : "All " + page.stats.forecasts_total + " strategy entries share " + page.events + " event(s), so they are not independent samples. Registered 12:00:44 CDT on Oct 21 (see ERRATA §3). No advantage has been demonstrated."
            }
            Flickable {
                id: list
                Layout.fillWidth: true
                Layout.fillHeight: true
                contentWidth: width
                contentHeight: cardCol.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {}
                Accessible.role: Accessible.List
                Accessible.name: page.isResearch ? "Research forecasts" : "Strategy forecasts"
                ColumnLayout {
                    id: cardCol
                    width: list.width - 10
                    spacing: 10
                    EmptyState { visible: page.cards.length === 0; Layout.fillWidth: true; heading: "No forecasts in this cohort"; badge: "EMPTY"
                                 description: "Nothing is shown here that was not recorded in the preserved research database." ; busy: backend.ui.loading.indexOf("cohort_cards") >= 0 }
                    Repeater {
                        model: page.cards
                        delegate: ForecastCard {
                            required property var modelData
                            card: modelData
                            selected: backend.ui.selectedTicker === modelData.ticker
                            onClicked: backend.select(modelData.ticker)
                        }
                    }
                }
            }
        }
        Panel {
            Layout.fillWidth: true
            Layout.fillHeight: !page.narrow
            Layout.preferredHeight: page.narrow ? 900 : -1
            Layout.preferredWidth: 600
            MarketDetail { anchors.fill: parent; anchors.margins: 16; tab: page.isResearch ? "Research" : "Forecasts" }
        }
    }
}
