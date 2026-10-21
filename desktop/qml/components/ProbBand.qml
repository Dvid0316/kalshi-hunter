import QtQuick
import QtQuick.Layouts
import ".."

// A forecast against the market on one 0-100% scale (probability that the market resolves YES).
//   lo/hi/p        researcher's uncertainty band and point estimate (0..1)
//   bid/ask        market YES bid/ask at the time (0..1, or -1 when unknown)
//   breakEven      YES-probability at which the paper fill breaks even after spread and fees (0..1, or -1)
// Always presented as an experimental estimate, never as a verified edge.
ColumnLayout {
    id: band
    property real lo: 0
    property real hi: 0
    property real p: 0
    property real bid: -1
    property real ask: -1
    property real breakEven: -1
    property bool showLegend: true
    spacing: 6
    Accessible.role: Accessible.StaticText
    Accessible.name: "Forecast " + Math.round(p * 100) + " percent, band " + Math.round(lo * 100) + " to " + Math.round(hi * 100) +
                     (bid >= 0 && ask >= 0 ? ", market YES " + Math.round(bid * 100) + " to " + Math.round(ask * 100) + " percent" : "")
    Item {
        Layout.fillWidth: true
        Layout.preferredHeight: 38
        Rectangle { id: track; anchors.verticalCenter: parent.verticalCenter; width: parent.width; height: 14; radius: 7; color: "#1e3044" }
        // quarter ticks
        Repeater { model: 5
            delegate: Rectangle { required property int index; x: index * (track.width - 1) / 4; y: track.y - 4; width: 1; height: 22; color: "#34506b" } }
        // market bid/ask bracket
        Rectangle { visible: band.bid >= 0 && band.ask >= 0; x: track.width * band.bid; y: track.y - 5
            width: Math.max(3, track.width * (band.ask - band.bid)); height: 24; radius: 3; color: "transparent"; border.color: Theme.accent2; border.width: 2 }
        // researcher band
        Rectangle { visible: band.hi > band.lo; x: track.width * band.lo; y: track.y; width: Math.max(2, track.width * (band.hi - band.lo)); height: 14; radius: 5; color: "#2a7d78" }
        // estimate
        Rectangle { x: track.width * band.p - 6; y: track.y + 1; width: 12; height: 12; radius: 6; color: Theme.accent; border.color: "#06231f"; border.width: 2 }
        // break-even tick
        Rectangle { visible: band.breakEven >= 0; x: track.width * band.breakEven - 1; y: track.y - 8; width: 3; height: 30; color: Theme.warn }
    }
    RowLayout {
        Layout.fillWidth: true
        Small { text: "0%"; Layout.fillWidth: true; font.pixelSize: Theme.fsXs }
        Small { text: "50%"; font.pixelSize: Theme.fsXs }
        Small { text: "100%"; Layout.fillWidth: true; horizontalAlignment: Text.AlignRight; font.pixelSize: Theme.fsXs }
    }
    Flow {
        visible: band.showLegend
        Layout.fillWidth: true
        spacing: 16
        Row { spacing: 6; Rectangle { width: 10; height: 10; radius: 5; color: Theme.accent; anchors.verticalCenter: parent.verticalCenter } Small { text: "Estimate"; font.pixelSize: Theme.fsXs } }
        Row { spacing: 6; Rectangle { width: 14; height: 8; radius: 3; color: "#2a7d78"; anchors.verticalCenter: parent.verticalCenter } Small { text: "Uncertainty band"; font.pixelSize: Theme.fsXs } }
        Row { visible: band.bid >= 0; spacing: 6; Rectangle { width: 14; height: 10; radius: 2; color: "transparent"; border.color: Theme.accent2; border.width: 2; anchors.verticalCenter: parent.verticalCenter } Small { text: "Market YES bid–ask"; font.pixelSize: Theme.fsXs } }
        Row { visible: band.breakEven >= 0; spacing: 6; Rectangle { width: 3; height: 12; color: Theme.warn; anchors.verticalCenter: parent.verticalCenter } Small { text: "Break-even after spread & fees"; font.pixelSize: Theme.fsXs } }
    }
}
