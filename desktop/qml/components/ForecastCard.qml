import QtQuick
import QtQuick.Layouts
import ".."

// A recorded paper forecast against the market. Paper only; an experimental estimate, not a verified edge.
Rectangle {
    id: fc
    property var card: ({})
    property bool selected: false
    property bool showTitle: true
    signal clicked()
    Layout.fillWidth: true
    implicitHeight: body.implicitHeight + 2 * Theme.pad
    radius: 10
    color: selected ? Theme.panelSelected : Theme.panelAlt
    border.color: selected ? Theme.accent : Theme.border
    Accessible.role: Accessible.ListItem
    Accessible.name: (card.cohort_label || "") + " " + (card.ticker || "") + ", " + (card.side || "").toUpperCase() + ", P(YES) " + (card.probability || "") + ", " + (card.status || "")
    Accessible.selected: selected
    Accessible.onPressAction: fc.clicked()
    activeFocusOnTab: true
    Keys.onReturnPressed: fc.clicked()
    Keys.onSpacePressed: fc.clicked()
    Rectangle { anchors.fill: parent; radius: 10; color: "transparent"; border.color: fc.activeFocus ? Theme.accent : "transparent"; border.width: 2 }
    TapHandler { onTapped: fc.clicked() }
    ColumnLayout {
        id: body
        anchors.fill: parent
        anchors.margins: Theme.pad
        spacing: 10
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Txt { visible: fc.showTitle; Layout.fillWidth: true; text: fc.card.title || fc.card.ticker; font.weight: Font.DemiBold; font.pixelSize: Theme.fsMd - 1 }
                Mono { Layout.fillWidth: true; text: fc.card.ticker || ""; color: Theme.muted; font.pixelSize: Theme.fsXs + 1 }
            }
            Tag { label: "Paper: buy " + (fc.card.side || "").toUpperCase(); tint: Theme.accent }
            Tag { label: fc.card.status || ""; tint: Theme.muted }
        }
        ProbBand {
            Layout.fillWidth: true
            lo: fc.card.prob_lo !== undefined ? fc.card.prob_lo : 0
            hi: fc.card.prob_hi !== undefined ? fc.card.prob_hi : 0
            p: fc.card.prob_yes !== undefined ? fc.card.prob_yes : 0
            bid: fc.card.market_bid !== undefined ? fc.card.market_bid : -1
            ask: fc.card.market_ask !== undefined ? fc.card.market_ask : -1
            breakEven: fc.card.exec_implied_p !== undefined && fc.card.exec_implied_p !== null ? fc.card.exec_implied_p : -1
            showLegend: fc.selected
        }
        GridLayout {
            Layout.fillWidth: true
            columns: width > 520 ? 6 : 3
            columnSpacing: 12
            rowSpacing: 6
            Column { Small { text: "P(YES)"; font.pixelSize: Theme.fsXs } Mono { text: fc.card.probability || "—" } }
            Column { Small { text: "Band"; font.pixelSize: Theme.fsXs } Mono { text: fc.card.band || "—" } }
            Column { Small { text: "Paper fill (" + (fc.card.side || "").toUpperCase() + ")"; font.pixelSize: Theme.fsXs } Mono { text: fc.card.price || "—" } }
            Column { Small { text: "Qty"; font.pixelSize: Theme.fsXs } Mono { text: fc.card.qty || "—" } }
            Column { Small { text: "Fee"; font.pixelSize: Theme.fsXs } Mono { text: fc.card.fee_text || "—" } }
            Column { Small { text: "Paper P&L"; font.pixelSize: Theme.fsXs } Mono { text: fc.card.pnl_text || "Unavailable"; color: Theme.muted } }
        }
        Small { visible: fc.selected && !!fc.card.market_at_fill; Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone
                text: "Market at fill: " + (fc.card.market_at_fill || "") + "  ·  edge vs mid " + (fc.card.edge_vs_mid || "—") + "  ·  vs executable " + (fc.card.edge_vs_exec || "—") + "  ·  recorded " + (fc.card.when || "") }
    }
}
