import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

// Your own positions. Built only from trades you import or record; never from paper forecasts.
Item {
    id: page
    property bool fill: false
    implicitHeight: col.implicitHeight
    readonly property var acct: backend.account_status
    readonly property var pos: backend.positions
    readonly property var s: pos.summary || ({})
    readonly property bool hasData: !!acct.has_data
    readonly property bool busy: backend.ui.loading.indexOf("positions") >= 0
    property int selectedIndex: -1
    readonly property var selectedRow: (selectedIndex >= 0 && selectedIndex < (pos.rows || []).length) ? pos.rows[selectedIndex] : null
    Connections { target: backend; function onStepPageRequested(d) { if (backend.ui.page === "Positions") backend.pagePositions(d) } }
    Connections { target: backend; function onPositionsChanged() { page.selectedIndex = -1 } }
    Connections { target: backend; function onFocusSearch() { if (backend.ui.page === "Positions") search.forceActiveFocus() } }

    ColumnLayout {
        id: col
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: Theme.gap

        GridLayout {
            Layout.fillWidth: true
            columns: page.width > 1100 ? 5 : (page.width > 760 ? 3 : 2)
            columnSpacing: 12
            rowSpacing: 12
            Metric { Layout.fillWidth: true; label: "Realized P&L (verified markets)"; value: page.s.realized || "Unavailable"; note: page.s.realized_note || ""
                     valueColor: (page.s.realized || "").charAt(0) === "+" ? Theme.gain : ((page.s.realized || "").charAt(0) === "-" ? Theme.loss : Theme.muted) }
            Metric { Layout.fillWidth: true; label: "Fees paid"; value: page.s.fees || "Unavailable"; note: "All recorded fees"; valueColor: page.hasData ? Theme.ink : Theme.muted }
            Metric { Layout.fillWidth: true; label: "Open cost basis"; value: page.s.open_cost || "Unavailable"; note: (page.s.open_count || 0) + " open position(s), incl. entry fees"; valueColor: page.hasData ? Theme.ink : Theme.muted }
            Metric { Layout.fillWidth: true; label: "Unrealized P&L"; value: page.s.unrealized || "Unavailable"; note: page.s.unrealized_note || ""; valueColor: Theme.muted }
            Metric { Layout.fillWidth: true; label: "Net deposits"; value: page.s.net_deposits || "Unavailable"; note: page.s.net_deposits_note || ""; valueColor: page.hasData && page.s.net_deposits !== "Unavailable" ? Theme.ink : Theme.muted }
        }

        EmptyState {
            visible: !page.hasData
            Layout.fillWidth: true
            badge: "NO ACCOUNT DATA"
            heading: "Your positions will appear here"
            description: "Nothing has been imported or recorded. Kalshi account access is not connected, no credentials are stored, and paper forecasts are never shown as holdings.\n\nBring in trades you executed yourself, from a CSV/JSON file or by recording one at a time."
            Btn { text: "Import from file…"; primary: true; onClicked: backend.openDialog("import") }
            Btn { text: "Record an executed trade…"; onClicked: backend.openDialog("record") }
        }

        Panel {
            visible: !page.hasData
            Layout.fillWidth: true
            implicitHeight: authCol.implicitHeight + 36
            ColumnLayout {
                id: authCol
                anchors.fill: parent
                anchors.margins: 18
                spacing: 6
                RowLayout { Layout.fillWidth: true; Txt { text: "Kalshi account connection"; font.weight: Font.DemiBold; Layout.fillWidth: true }
                            Tag { label: (backend.ui.authorization.mode || "Not connected"); tint: Theme.muted } }
                Small { Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone; text: backend.ui.authorization.detail || "" }
                Small { Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone; color: Theme.faint
                        text: "A read-only live connection (positions, fills, settlements) is designed in docs/ACCOUNT_DATA_CONTRACT.md but is not built or enabled. It needs your explicit go-ahead before any credential is requested." }
            }
        }

        Panel {
            visible: page.hasData
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(520, Math.min(900, 300 + (page.pos.rows || []).length * 60))
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 10
                Flow {
                    Layout.fillWidth: true
                    spacing: 10
                    SegmentedControl { accessibleName: "Position state"; current: page.pos.tab || "open"
                                       options: [{value: "open", label: "Open (" + (page.s.open_count || 0) + ")"}, {value: "closed", label: "Closed (" + (page.s.closed_count || 0) + ")"}]
                                       onPicked: function (v) { backend.setPositionsTab(v) } }
                    SearchField { id: search; width: 280; placeholderText: "Filter by ticker or title"; onSubmitted: function (v) { backend.searchPositions(v) } }
                    Btn { text: "Import file…"; onClicked: backend.openDialog("import") }
                    Btn { text: "Record a trade…"; onClicked: backend.openDialog("record") }
                    Tag { visible: (page.s.incomplete || 0) > 0; label: page.s.incomplete + " NEED REVIEW"; tint: Theme.warn; anchors.verticalCenter: undefined }
                }
                Small { Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone; font.pixelSize: Theme.fsXs
                        text: (page.pos.tab === "closed"
                               ? "Realized P&L is net of every fee. Settled markets use the exchange's recorded payout. “INCOMPLETE” means fills are missing or contradict the settlement, so no P&L is shown rather than a guess."
                               : "Average cost includes entry fees. Unrealized P&L stays Unavailable until a fresh executable exit quote exists; archived quotes are never used to mark positions.") }
                DataTable {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    accessibleName: page.pos.tab === "closed" ? "Closed positions" : "Open positions"
                    rowHeight: 58
                    busy: page.busy
                    emptyText: page.pos.tab === "closed" ? "No closed positions." : "No open positions."
                    rows: page.pos.rows || []
                    sortKey: page.pos.sort || ""
                    sortDesc: !!page.pos.desc
                    selectedKey: page.selectedRow ? page.selectedRow.ticker : ""
                    columns: page.pos.tab === "closed" ? [
                        {key: "ticker", title: "Market", fill: true, sub: "title", sortKey: "ticker"},
                        {key: "outcome", title: "Outcome", width: 100, tag: true, tone: "muted"},
                        {key: "qty", title: "Qty", width: 50, mono: true, align: "right", sortKey: "qty"},
                        {key: "avg_entry", title: "Avg entry", width: 80, mono: true, align: "right", sortKey: "avg_entry"},
                        {key: "avg_exit", title: "Avg exit", width: 80, mono: true, align: "right", sortKey: "avg_exit"},
                        {key: "fees", title: "Fees", width: 70, mono: true, align: "right", sortKey: "fees"},
                        {key: "realized", title: "Realized", width: 92, mono: true, align: "right", tone: "signed", sortKey: "realized"},
                        {key: "closed", title: "Closed", width: 96, mono: true, align: "right", sortKey: "closed_ts"}
                    ] : [
                        {key: "ticker", title: "Market", fill: true, sub: "title", sortKey: "ticker"},
                        {key: "side", title: "Side", width: 56, tone: "accent"},
                        {key: "qty", title: "Qty", width: 50, mono: true, align: "right", sortKey: "qty"},
                        {key: "avg_entry", title: "Avg cost", width: 80, mono: true, align: "right", sortKey: "avg_entry"},
                        {key: "cost_basis", title: "Cost basis", width: 90, mono: true, align: "right", sortKey: "cost_basis"},
                        {key: "realized", title: "Realized", width: 84, mono: true, align: "right", tone: "signed", sortKey: "realized"},
                        {key: "unrealized", title: "Unrealized", width: 90, mono: true, align: "right", tone: "muted"},
                        {key: "opened", title: "Opened", width: 96, mono: true, align: "right", sortKey: "opened"}
                    ]
                    onSortRequested: function (k) { backend.sortPositions(k) }
                    onRowClicked: function (row, i) { page.selectedIndex = i }
                }
                Banner {
                    kind: page.selectedRow && page.selectedRow.incomplete ? "warn" : "info"
                    text: page.selectedRow ? (page.selectedRow.ticker + (page.selectedRow.reference ? " · " + page.selectedRow.reference : "")
                                              + ((page.selectedRow.flags || []).length ? "\n" + page.selectedRow.flags.join("\n") : "")
                                              + (page.selectedRow.record_pnl ? "\nPer the exchange's settlement record (excludes fill fees): " + page.selectedRow.record_pnl : "")) : ""
                    actionText: page.selectedRow ? "Open market" : ""
                    onActionClicked: { backend.select(page.selectedRow.ticker); backend.navigate("Markets") }
                }
                Pager {
                    Layout.fillWidth: true
                    page: page.pos.page || 1
                    pages: page.pos.pages || 1
                    total: page.pos.total || 0
                    unit: "positions"
                    onPrevious: backend.pagePositions(-1)
                    onNext: backend.pagePositions(1)
                }
            }
        }

        Panel {
            visible: page.hasData
            Layout.fillWidth: true
            implicitHeight: dqCol.implicitHeight + 36
            ColumnLayout {
                id: dqCol
                anchors.fill: parent
                anchors.margins: 18
                spacing: 6
                RowLayout {
                    Layout.fillWidth: true
                    Txt { text: "Data quality"; font.weight: Font.DemiBold; Layout.fillWidth: true }
                    Tag { label: backend.quality.ok === false ? "ISSUES FOUND" : "NO BLOCKING ISSUES"; tint: backend.quality.ok === false ? Theme.warn : Theme.accent }
                }
                Repeater {
                    model: (backend.quality.items || []).slice(0, 8)
                    delegate: Text { required property var modelData; Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: Theme.fsSm
                                     color: modelData.level === "error" ? Theme.danger : (modelData.level === "warn" ? Theme.warn : Theme.muted); text: "• " + modelData.message }
                }
                Small { visible: (backend.quality.items || []).length === 0; text: "No duplicates, conflicts, rejected rows or inconsistent histories."; Layout.fillWidth: true }
            }
        }
    }
}
