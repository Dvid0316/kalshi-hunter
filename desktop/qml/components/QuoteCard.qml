import QtQuick
import QtQuick.Layouts
import ".."

// Executable YES and NO quotes side by side.
//   BUY  = lift the ask: what you PAY now.      SELL = hit the bid: what you RECEIVE now.
// Archived quotes are labelled as such and are never presented as executable.
Panel {
    id: card
    property var quote: null
    implicitHeight: body.implicitHeight + 2 * Theme.pad
    Accessible.role: Accessible.Table
    Accessible.name: quote ? ("Quotes. YES bid " + quote.yes.bid + ", ask " + quote.yes.ask + ". NO bid " + quote.no.bid + ", ask " + quote.no.ask + ". " + quote.freshness) : "No quote available"
    ColumnLayout {
        id: body
        anchors.fill: parent
        anchors.margins: Theme.pad
        spacing: 12
        RowLayout {
            Layout.fillWidth: true
            Txt { text: card.quote && card.quote.executable ? "Executable quotes" : "Archived quotes · not executable"; font.weight: Font.DemiBold; Layout.fillWidth: true }
            Tag { visible: !!card.quote; label: card.quote ? card.quote.freshness : ""; tint: Theme.warn }
        }
        Small { visible: !card.quote; text: "No quote snapshot exists for this market."; Layout.fillWidth: true }
        GridLayout {
            visible: !!card.quote
            Layout.fillWidth: true
            columns: 3
            columnSpacing: 14
            rowSpacing: 8
            Item { Layout.preferredWidth: 96 }
            Small { text: "YES"; font.weight: Font.DemiBold; color: Theme.accent; Layout.fillWidth: true; Layout.preferredWidth: 100 }
            Small { text: "NO"; font.weight: Font.DemiBold; color: Theme.accent2; Layout.fillWidth: true; Layout.preferredWidth: 100 }

            Column { Layout.preferredWidth: 96; Small { text: card.quote && card.quote.executable ? "BUY · you pay" : "BUY · ask at capture"; font.pixelSize: Theme.fsXs } Small { text: "ask" ; font.pixelSize: Theme.fsXs } }
            Column { Layout.fillWidth: true; Layout.preferredWidth: 100
                Mono { text: card.quote ? card.quote.yes.ask : ""; font.pixelSize: Theme.fsLg; font.weight: Font.DemiBold; color: Theme.accent }
                Small { text: card.quote ? "size " + card.quote.yes.ask_size : ""; font.pixelSize: Theme.fsXs } }
            Column { Layout.fillWidth: true; Layout.preferredWidth: 100
                Mono { text: card.quote ? card.quote.no.ask : ""; font.pixelSize: Theme.fsLg; font.weight: Font.DemiBold; color: Theme.accent2 }
                Small { text: card.quote ? "size " + card.quote.no.ask_size : ""; font.pixelSize: Theme.fsXs } }

            Column { Layout.preferredWidth: 96; Small { text: card.quote && card.quote.executable ? "SELL · you get" : "SELL · bid at capture"; font.pixelSize: Theme.fsXs } Small { text: "bid"; font.pixelSize: Theme.fsXs } }
            Column { Layout.fillWidth: true; Layout.preferredWidth: 100
                Mono { text: card.quote ? card.quote.yes.bid : ""; font.pixelSize: Theme.fsLg; font.weight: Font.DemiBold }
                Small { text: card.quote ? "size " + card.quote.yes.bid_size : ""; font.pixelSize: Theme.fsXs } }
            Column { Layout.fillWidth: true; Layout.preferredWidth: 100
                Mono { text: card.quote ? card.quote.no.bid : ""; font.pixelSize: Theme.fsLg; font.weight: Font.DemiBold }
                Small { text: card.quote ? "size " + card.quote.no.bid_size : ""; font.pixelSize: Theme.fsXs } }
        }
        Rectangle { visible: !!card.quote; Layout.fillWidth: true; height: 1; color: Theme.border }
        GridLayout {
            visible: !!card.quote
            Layout.fillWidth: true
            columns: 4
            columnSpacing: 12
            Column { Small { text: "Spread"; font.pixelSize: Theme.fsXs } Mono { text: card.quote ? card.quote.spread : "" } }
            Column { Small { text: "Last trade"; font.pixelSize: Theme.fsXs } Mono { text: card.quote ? card.quote.last : "" } }
            Column { Small { text: "24h volume"; font.pixelSize: Theme.fsXs } Mono { text: card.quote ? card.quote.volume_24h : "" } }
            Column { Small { text: "Open interest"; font.pixelSize: Theme.fsXs } Mono { text: card.quote ? card.quote.open_interest : "" } }
        }
        Small {
            visible: !!card.quote
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            font.pixelSize: Theme.fsXs
            text: card.quote ? ("Quote captured " + card.quote.asof + " (" + card.quote.age + " ago). " + (card.quote.executable ? "" : "Archived snapshot: not an executable price. Check Kalshi before acting.")) : ""
        }
    }
}
