import QtQuick
import ".."

// Interactive bid/ask history. Draws ONLY archived snapshots (no interpolation claims, no invented points).
//   points: [{t, bid, ask, no_bid, no_ask, tl, when}]   side: "yes" | "no"
// Hover or use Left/Right keys to read exact values at a snapshot.
Item {
    id: chart
    property var points: []
    property string side: "yes"
    property int hoverIndex: -1
    property int keyIndex: -1
    readonly property int shown: hoverIndex >= 0 ? hoverIndex : keyIndex
    readonly property string sideLabel: side === "yes" ? "YES" : "NO"
    activeFocusOnTab: true
    implicitHeight: 220
    onPointsChanged: { hoverIndex = -1; keyIndex = -1; canvas.requestPaint() }
    onSideChanged: canvas.requestPaint()
    onShownChanged: canvas.requestPaint()
    onWidthChanged: canvas.requestPaint()
    onHeightChanged: canvas.requestPaint()
    Accessible.role: Accessible.Chart
    Accessible.name: "Price history chart, " + sideLabel + " side"
    Accessible.description: {
        if (!points || points.length < 2) return "No two-sided quote history available."
        var p = points[points.length - 1]
        var b = side === "yes" ? p.bid : p.no_bid
        var a = side === "yes" ? p.ask : p.no_ask
        return points.length + " archived snapshots. Latest " + sideLabel + " bid " + (b * 100).toFixed(1) + " cents, ask " + (a * 100).toFixed(1) + " cents at " + p.when
    }
    Keys.onLeftPressed: { if (points.length) keyIndex = Math.max(0, (keyIndex < 0 ? points.length - 1 : keyIndex) - 1) }
    Keys.onRightPressed: { if (points.length) keyIndex = Math.min(points.length - 1, (keyIndex < 0 ? points.length - 1 : keyIndex) + 1) }
    Keys.onEscapePressed: keyIndex = -1

    function bidOf(p) { return side === "yes" ? p.bid : p.no_bid }
    function askOf(p) { return side === "yes" ? p.ask : p.no_ask }

    Rectangle { anchors.fill: parent; color: "transparent"; radius: 8; border.color: chart.activeFocus ? Theme.accent : "transparent"; border.width: 2 }

    Canvas {
        id: canvas
        anchors.fill: parent
        renderTarget: Canvas.Image
        onPaint: {
            var c = getContext("2d")
            c.reset()
            var pts = chart.points || []
            var left = 48, right = width - 14, top = 12, bottom = height - 30
            c.font = "11px sans-serif"
            if (pts.length < 2) {
                c.fillStyle = Theme.muted
                c.fillText("No quote history available for this market.", left, height / 2)
                return
            }
            var lo = 1, hi = 0
            for (var i = 0; i < pts.length; i++) {
                lo = Math.min(lo, chart.bidOf(pts[i])); hi = Math.max(hi, chart.askOf(pts[i]))
            }
            lo = Math.max(0, lo - 0.01); hi = Math.min(1, hi + 0.01)
            if (hi - lo < 0.03) { var mid = (hi + lo) / 2; lo = Math.max(0, mid - 0.015); hi = Math.min(1, mid + 0.015) }
            var t0 = pts[0].t, t1 = pts[pts.length - 1].t, span = Math.max(1, t1 - t0)
            function x(p) { return left + (p.t - t0) / span * (right - left) }
            function y(v) { return bottom - (v - lo) / (hi - lo) * (bottom - top) }
            // grid + y labels
            c.strokeStyle = "#26364a"; c.lineWidth = 1; c.fillStyle = "#9aadc4"
            for (var g = 0; g < 4; g++) {
                var v = lo + g * (hi - lo) / 3
                c.beginPath(); c.moveTo(left, y(v)); c.lineTo(right, y(v)); c.stroke()
                c.fillText((v * 100).toFixed(1) + "¢", 2, y(v) + 4)
            }
            // spread band
            c.beginPath(); c.moveTo(x(pts[0]), y(chart.askOf(pts[0])))
            for (i = 1; i < pts.length; i++) c.lineTo(x(pts[i]), y(chart.askOf(pts[i])))
            for (i = pts.length - 1; i >= 0; i--) c.lineTo(x(pts[i]), y(chart.bidOf(pts[i])))
            c.closePath(); c.fillStyle = "#173c46"; c.fill()
            // lines
            var colors = ["#55dcc8", "#8eaaff"]
            for (var k = 0; k < 2; k++) {
                c.beginPath(); c.strokeStyle = colors[k]; c.lineWidth = 2
                for (i = 0; i < pts.length; i++) {
                    var yy = y(k === 0 ? chart.askOf(pts[i]) : chart.bidOf(pts[i]))
                    if (i === 0) c.moveTo(x(pts[i]), yy); else c.lineTo(x(pts[i]), yy)
                }
                c.stroke()
                if (pts.length <= 60) {
                    c.fillStyle = colors[k]
                    for (i = 0; i < pts.length; i++) { c.beginPath(); c.arc(x(pts[i]), y(k === 0 ? chart.askOf(pts[i]) : chart.bidOf(pts[i])), 2.2, 0, 6.3); c.fill() }
                }
            }
            // time axis: first / middle / last real snapshot times
            c.fillStyle = "#9aadc4"
            var idxs = [0, Math.floor((pts.length - 1) / 2), pts.length - 1]
            for (var q = 0; q < idxs.length; q++) {
                var label = pts[idxs[q]].tl
                var tx = x(pts[idxs[q]])
                var tw = c.measureText(label).width
                c.fillText(label, Math.min(Math.max(left, tx - tw / 2), right - tw), height - 8)
            }
            // crosshair + tooltip
            var s = chart.shown
            if (s >= 0 && s < pts.length) {
                var p = pts[s], px = x(p)
                c.strokeStyle = "#e7eef7"; c.lineWidth = 1; c.setLineDash([3, 3])
                c.beginPath(); c.moveTo(px, top); c.lineTo(px, bottom); c.stroke(); c.setLineDash([])
                var lines = [p.when,
                             "Buy " + chart.sideLabel + " (ask)  " + (chart.askOf(p) * 100).toFixed(1) + "¢",
                             "Sell " + chart.sideLabel + " (bid)  " + (chart.bidOf(p) * 100).toFixed(1) + "¢",
                             "Spread  " + ((chart.askOf(p) - chart.bidOf(p)) * 100).toFixed(1) + "¢"]
                var bw = 0
                for (var m = 0; m < lines.length; m++) bw = Math.max(bw, c.measureText(lines[m]).width)
                bw += 18; var bh = lines.length * 16 + 10
                var bx = px + 12 + bw > right ? px - 12 - bw : px + 12
                var by = top + 4
                c.fillStyle = "#0b111a"; c.strokeStyle = "#34506b"
                c.fillRect(bx, by, bw, bh); c.strokeRect(bx, by, bw, bh)
                c.fillStyle = "#e7eef7"
                for (m = 0; m < lines.length; m++) c.fillText(lines[m], bx + 9, by + 16 + m * 16)
            }
        }
    }
    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        onPositionChanged: function (mouse) {
            var pts = chart.points
            if (!pts || pts.length < 2) { chart.hoverIndex = -1; return }
            var left = 48, right = width - 14
            var span = Math.max(1, pts[pts.length - 1].t - pts[0].t)
            var tt = pts[0].t + (mouse.x - left) / (right - left) * span
            var best = 0, bd = 1e18
            for (var i = 0; i < pts.length; i++) { var d = Math.abs(pts[i].t - tt); if (d < bd) { bd = d; best = i } }
            chart.hoverIndex = (mouse.x >= left - 6 && mouse.x <= right + 6) ? best : -1
        }
        onExited: chart.hoverIndex = -1
        onClicked: chart.forceActiveFocus()
    }
}
