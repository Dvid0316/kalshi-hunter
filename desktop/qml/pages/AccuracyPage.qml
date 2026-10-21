import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

// Forecast quality. Shows a metric only when resolved outcomes exist; otherwise says exactly why not.
Item {
    id: page
    property bool fill: false
    implicitHeight: col.implicitHeight
    readonly property var a: backend.accuracy
    readonly property var bt: a.backtest || ({available: false, status: "UNKNOWN", rules: []})

    component CohortPanel: Panel {
        id: cp
        property var c: ({})
        property color tint: Theme.accent
        Layout.fillWidth: true
        implicitHeight: cpCol.implicitHeight + 40
        ColumnLayout {
            id: cpCol
            anchors.fill: parent
            anchors.margins: 20
            spacing: 10
            RowLayout {
                Layout.fillWidth: true
                Txt { text: cp.c.label || ""; font.pixelSize: Theme.fsLg; font.weight: Font.DemiBold; Layout.fillWidth: true; color: cp.tint }
                Tag { label: cp.c.resolved > 0 ? cp.c.resolved + " RESOLVED" : "INSUFFICIENT OUTCOMES"; tint: cp.c.resolved > 0 ? Theme.accent : Theme.warn }
            }
            GridLayout {
                Layout.fillWidth: true
                columns: 4
                columnSpacing: 14
                Column { Small { text: "Paper entries"; font.pixelSize: Theme.fsXs } Mono { text: String(cp.c.forecasts_total); font.pixelSize: Theme.fsLg } }
                Column { Small { text: "Resolved"; font.pixelSize: Theme.fsXs } Mono { text: String(cp.c.resolved); font.pixelSize: Theme.fsLg } }
                Column { Small { text: "Brier score"; font.pixelSize: Theme.fsXs } Mono { text: cp.c.brier !== null && cp.c.brier !== undefined ? Number(cp.c.brier).toFixed(4) : "Unavailable"; font.pixelSize: Theme.fsLg; color: cp.c.brier !== null && cp.c.brier !== undefined ? Theme.ink : Theme.muted } }
                Column { Small { text: "Log loss"; font.pixelSize: Theme.fsXs } Mono { text: cp.c.log_loss !== null && cp.c.log_loss !== undefined ? Number(cp.c.log_loss).toFixed(4) : "Unavailable"; font.pixelSize: Theme.fsLg; color: cp.c.log_loss !== null && cp.c.log_loss !== undefined ? Theme.ink : Theme.muted } }
            }
            Small { Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone
                    text: cp.c.resolved > 0
                          ? "Computed from " + cp.c.n_brier + " resolved forecast(s); market Brier uses the " + cp.c.n_brier_paired + " with a recorded market price. " + (cp.c.note || "")
                          : "Brier score, log loss and realized paper P&L need resolved outcomes. None exist, so none are shown, and no calibration curve is drawn." }
            Small { visible: (cp.c.distinct_events || 0) > 0 && (cp.c.distinct_events || 0) < (cp.c.forecasts_total || 0); Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone; color: Theme.warn
                    text: cp.c.forecasts_total + " entries share only " + cp.c.distinct_events + " event(s): they are correlated, not independent samples." }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
            Small { text: "FORECAST UNCERTAINTY AT ENTRY (not accuracy)"; font.pixelSize: Theme.fsXs; font.letterSpacing: 1 }
            Repeater {
                model: cp.c.bands || []
                delegate: ColumnLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: 2
                    RowLayout { Layout.fillWidth: true
                        Mono { text: modelData.ticker; Layout.fillWidth: true; font.pixelSize: Theme.fsXs + 1; elide: Text.ElideMiddle }
                        Mono { text: Math.round(modelData.lo * 100) + "–" + Math.round(modelData.hi * 100) + "%  (est " + (modelData.p * 100).toFixed(1) + "%)"; font.pixelSize: Theme.fsXs + 1 } }
                    ProbBand { Layout.fillWidth: true; lo: modelData.lo; hi: modelData.hi; p: modelData.p; showLegend: false }
                }
            }
            Small { visible: (cp.c.reliability || []).length > 0; text: "RELIABILITY BY FORECAST BIN (tiny n: do not over-read)"; font.pixelSize: Theme.fsXs; font.letterSpacing: 1 }
            Repeater {
                model: cp.c.reliability || []
                delegate: RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: 12
                    Mono { text: modelData.bin; Layout.preferredWidth: 90 }
                    Mono { text: "n=" + modelData.n; Layout.preferredWidth: 60 }
                    Mono { text: "forecast " + (modelData.mean_p * 100).toFixed(0) + "%"; Layout.preferredWidth: 130 }
                    Mono { text: "happened " + (modelData.freq * 100).toFixed(0) + "%"; Layout.fillWidth: true }
                }
            }
        }
    }

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
            CohortPanel { c: (page.a.cohorts || {}).research || ({}); tint: Theme.accent }
            CohortPanel { c: (page.a.cohorts || {}).strategy || ({}); tint: Theme.accent2 }
        }
        Panel {
            Layout.fillWidth: true
            implicitHeight: btCol.implicitHeight + 40
            ColumnLayout {
                id: btCol
                anchors.fill: parent
                anchors.margins: 20
                spacing: 10
                RowLayout {
                    Layout.fillWidth: true
                    Txt { text: "Historical backtests (legacy Track A)"; font.pixelSize: Theme.fsLg; font.weight: Font.DemiBold; Layout.fillWidth: true }
                    Tag { label: page.bt.status; tint: page.bt.status === "INCONCLUSIVE" ? Theme.warn : Theme.muted }
                }
                Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.warn; font.pixelSize: Theme.fsSm + 1; lineHeight: 1.35
                       text: "Retrospective, with unverifiable availability of candles and expiry times. The preserved review concluded no profitable advantage is demonstrated. Nothing here is shown as prospective performance." }
                Repeater {
                    model: page.bt.rules || []
                    delegate: RowLayout { required property var modelData; Layout.fillWidth: true
                        Mono { text: modelData.rule; Layout.preferredWidth: 160 } Mono { text: modelData.rows + " rows" } Item { Layout.fillWidth: true } }
                }
                Small { visible: page.bt.available; text: page.bt.total + " analysed rows · " + page.bt.exclusions + " exclusions (counts only; results are in the corrected report)." }
                RowLayout {
                    spacing: 10
                    Btn { text: "Read the corrected report"; onClicked: { backend.navigate("Evidence"); backend.openDocument("validation_report_2026-10-21_corrected.md") } }
                    Btn { text: "Read the conclusions"; onClicked: { backend.navigate("Evidence"); backend.openDocument("CONCLUSIONS.md") } }
                }
            }
        }
    }
}
