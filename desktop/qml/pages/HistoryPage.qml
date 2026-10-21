import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

// Actual transactions and settlements (your ledger) plus, clearly separated, the paper entries recorded by research.
Item {
    id: page
    property bool fill: true
    property int minHeight: 540
    readonly property var h: backend.history
    readonly property var acct: backend.account_status
    property string view: "transactions"
    readonly property bool busy: backend.ui.loading.indexOf("history") >= 0
    readonly property var papers: ((backend.cards.research || []).concat(backend.cards.strategy || []))
    Connections { target: backend; function onStepPageRequested(d) { if (backend.ui.page === "History" && page.view !== "paper") backend.pageHistory(d) } }
    Connections { target: backend; function onFocusSearch() { if (backend.ui.page === "History") search.forceActiveFocus() } }

    Panel {
        anchors.fill: parent
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 16
            spacing: 10
            Flow {
                Layout.fillWidth: true
                spacing: 10
                SegmentedControl {
                    accessibleName: "History view"
                    current: page.view
                    options: [{value: "transactions", label: "Transactions (actual)"}, {value: "settlements", label: "Settlements (actual)"}, {value: "paper", label: "Paper entries (research)"}]
                    onPicked: function (v) { page.view = v; if (v !== "paper") backend.setHistoryKind(v) }
                }
                SearchField { id: search; visible: page.view !== "paper"; width: 300; placeholderText: "Search ticker, type, id…"; onSubmitted: function (v) { backend.searchHistory(v) } }
                Btn { visible: page.view !== "paper"; text: "Import file…"; onClicked: backend.openDialog("import") }
                Btn { visible: page.view !== "paper"; text: "Record a trade…"; onClicked: backend.openDialog("record") }
            }
            Banner {
                kind: page.view === "paper" ? "warn" : "info"
                text: page.view === "paper"
                      ? "These are paper entries recorded by Grok's research. They are hypothetical fills, not trades you made and not account activity."
                      : (page.acct.has_data ? "Cash effect = proceeds − cost − fee for fills; payout − fee for settlements. Deposits and withdrawals are listed but never counted as profit."
                                            : "No transactions yet. Import or record trades you executed on Kalshi; nothing is read from your account.")
            }
            EmptyState {
                visible: page.view !== "paper" && !page.acct.has_data
                Layout.fillWidth: true
                Layout.fillHeight: true
                badge: "NO ACCOUNT DATA"
                heading: "No transactions recorded"
                description: "Your history appears here after you import a file or record a trade. Searching, sorting and settlement review work offline."
                Btn { text: "Import from file…"; primary: true; onClicked: backend.openDialog("import") }
            }
            DataTable {
                visible: page.view === "transactions" && page.acct.has_data
                Layout.fillWidth: true
                Layout.fillHeight: true
                accessibleName: "Transactions"
                rowHeight: 52
                busy: page.busy
                emptyText: "No transactions match."
                keyField: "ref"
                rows: page.h.kind === "transactions" ? (page.h.rows || []) : []
                sortKey: page.h.sort || ""
                sortDesc: !!page.h.desc
                columns: [
                    {key: "when", title: "Time", width: 190, mono: true, sortKey: "ts"},
                    {key: "type", title: "Type", width: 100, tag: true, tone: "muted", sortKey: "type"},
                    {key: "ticker", title: "Market", fill: true, sub: "description", sortKey: "ticker"},
                    {key: "cash", title: "Cash effect", width: 110, mono: true, align: "right", tone: "signed", sortKey: "cash"},
                    {key: "fee", title: "Fee", width: 72, mono: true, align: "right", sortKey: "fee"},
                    {key: "source", title: "Source", width: 76, tone: "muted"}
                ]
                onSortRequested: function (k) { backend.sortHistory(k) }
            }
            DataTable {
                visible: page.view === "settlements" && page.acct.has_data
                Layout.fillWidth: true
                Layout.fillHeight: true
                accessibleName: "Settlements"
                rowHeight: 56
                busy: page.busy
                emptyText: "No settlements recorded."
                keyField: "ref"
                rows: page.h.kind === "settlements" ? (page.h.rows || []) : []
                sortKey: page.h.sort || ""
                sortDesc: !!page.h.desc
                columns: [
                    {key: "when", title: "Settled", width: 190, mono: true, sortKey: "ts"},
                    {key: "ticker", title: "Market", fill: true, sortKey: "ticker"},
                    {key: "result", title: "Result", width: 70, tag: true, tone: "accent"},
                    {key: "payout", title: "Payout", width: 90, mono: true, align: "right", sortKey: "payout"},
                    {key: "fee", title: "Fee", width: 70, mono: true, align: "right"},
                    {key: "realized", title: "Realized P&L", width: 112, mono: true, align: "right", tone: "signed", sortKey: "realized"}
                ]
                onSortRequested: function (k) { backend.sortHistory(k) }
            }
            DataTable {
                visible: page.view === "paper"
                Layout.fillWidth: true
                Layout.fillHeight: true
                accessibleName: "Paper entries"
                rowHeight: 56
                emptyText: "No paper entries recorded."
                keyField: "id"
                rows: page.papers
                columns: [
                    {key: "ticker", title: "Market", fill: true, sub: "cohort_label"},
                    {key: "side", title: "Side", width: 50, tone: "accent"},
                    {key: "probability", title: "P(YES)", width: 70, mono: true, align: "right"},
                    {key: "price", title: "Paper fill", width: 80, mono: true, align: "right"},
                    {key: "qty", title: "Qty", width: 44, mono: true, align: "right"},
                    {key: "fee_text", title: "Fee", width: 64, mono: true, align: "right"},
                    {key: "status", title: "Status", width: 110, tone: "muted"},
                    {key: "pnl_text", title: "Paper P&L", width: 96, mono: true, align: "right", tone: "muted"}
                ]
                onRowActivated: function (row) { backend.select(row.ticker); backend.navigate("Markets") }
            }
            Pager {
                visible: page.view !== "paper" && page.acct.has_data
                Layout.fillWidth: true
                page: page.h.page || 1
                pages: page.h.pages || 1
                total: page.h.total || 0
                unit: page.view === "settlements" ? "settlements" : "transactions"
                onPrevious: backend.pageHistory(-1)
                onNext: backend.pageHistory(1)
            }
        }
    }
}
