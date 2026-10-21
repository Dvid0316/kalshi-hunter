import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

// Search, filter, sort and inspect every market in the archived snapshot.
Item {
    id: page
    readonly property bool narrow: width < 1080
    property bool fill: !narrow
    property int minHeight: 560
    implicitHeight: narrow ? 560 + 780 : 560
    readonly property var m: backend.markets
    readonly property bool busy: backend.ui.loading.indexOf("markets") >= 0
    readonly property var categoryModel: {
        var out = [{value: "any", label: "All categories"}]
        var cats = backend.categories
        for (var i = 0; i < cats.length; i++) out.push({value: cats[i].name, label: cats[i].name + " (" + Number(cats[i].count).toLocaleString(Qt.locale("en_US"), "f", 0) + ")"})
        return out
    }
    // Columns adapt to the width of the list panel itself, not the window.
    property real listWidth: 700
    readonly property var columns: {
        var lw = listWidth
        var c = [
            {key: "title", title: "Market", fill: true, sub: "subline", sortKey: "title"},
            {key: "status", title: "Status", width: 74, tone: "muted", capitalize: true, sortKey: "status"},
            {key: "bid", title: "YES bid", width: 72, mono: true, align: "right", sortKey: "bid"},
            {key: "ask", title: "YES ask", width: 72, mono: true, align: "right", sortKey: "ask"}
        ]
        if (lw >= 820) { c.push({key: "no_bid", title: "NO bid", width: 72, mono: true, align: "right"}); c.push({key: "no_ask", title: "NO ask", width: 72, mono: true, align: "right"}) }
        if (lw >= 690) c.push({key: "spread", title: "Spread", width: 66, mono: true, align: "right", sortKey: "spread"})
        c.push({key: "volume", title: "24h vol", width: 88, mono: true, align: "right", sortKey: "volume"})
        if (lw >= 980) c.push({key: "close", title: "Closes", width: 104, mono: true, align: "right", sortKey: "close"})
        return c
    }

    function syncControls() {
        scope.current = m.scope
        statusBox.select(m.status)
        categoryBox.select(m.category)
        quotesOnly.checked = !!m.quotes_only
        if (search.text !== m.search && !search.activeFocus) search.text = m.search
    }
    Connections { target: backend; function onMarketsChanged() { page.syncControls() } }
    Connections { target: backend; function onFocusSearch() { search.forceActiveFocus(); search.selectAll() } }
    Connections { target: backend; function onStepPageRequested(delta) { if (backend.ui.page === "Markets") backend.pageMarkets(delta) } }
    Component.onCompleted: { syncControls(); if (!backend.detail.ticker) backend.select(backend.ui.selectedTicker) }

    GridLayout {
        anchors.fill: parent
        columns: page.narrow ? 1 : 2
        columnSpacing: Theme.gap
        rowSpacing: Theme.gap
        Panel {
            Layout.fillWidth: true
            Layout.fillHeight: !page.narrow
            Layout.preferredHeight: page.narrow ? 560 : -1
            Layout.minimumWidth: 420
            onWidthChanged: page.listWidth = width
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 10
                SearchField {
                    id: search
                    objectName: "market_search"
                    Layout.fillWidth: true
                    placeholderText: "Search title, ticker or outcome — e.g. “senate”, “KXTRUMP”, “bitcoin above”  (Ctrl+K)"
                    onSubmitted: function (v) { backend.search(v) }
                }
                Flow {
                    Layout.fillWidth: true
                    spacing: 10
                    SegmentedControl { id: scope; accessibleName: "Scope"; options: [{value: "watchlist", label: "Forecast watchlist"}, {value: "all", label: "All markets"}]
                                       onPicked: function (v) { backend.filterMarkets("scope", v) } }
                    Select { id: statusBox; accessibleName: "Status filter"; implicitWidth: 140
                             model: [{value: "any", label: "Any status"}, {value: "active", label: "Active"}, {value: "closed", label: "Closed"}, {value: "settled", label: "Settled"}, {value: "inactive", label: "Inactive"}]
                             onPicked: function (v) { backend.filterMarkets("status", v) } }
                    Select { id: categoryBox; accessibleName: "Category filter"; implicitWidth: 200; model: page.categoryModel
                             onModelChanged: select(page.m.category)
                             onPicked: function (v) { backend.filterMarkets("category", v) } }
                    Check {
                        id: quotesOnly
                        text: "Two-sided quotes only"
                        Accessible.name: "Only markets with both a bid and an ask"
                        onToggled: backend.filterMarkets("quotes_only", checked ? "true" : "false")
                    }
                    Btn { text: "Reset"; implicitWidth: 70; implicitHeight: 30; onClicked: { search.text = ""; backend.resetMarketFilters() } }
                }
                Small {
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    elide: Text.ElideNone
                    font.pixelSize: Theme.fsXs
                    text: page.m.scope === "watchlist" && !page.m.search ? "Showing the " + page.m.total + " markets that have a recorded paper forecast. Switch to All markets to explore the full catalog."
                          : "Quotes are archived (see age per row). Rows marked “dropped” left the scan before the snapshot ended, so their price is older than the snapshot."
                }
                DataTable {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    accessibleName: "Markets"
                    rowHeight: 58
                    busy: page.busy
                    emptyText: "No markets match. Try fewer words or Reset."
                    rows: page.m.rows || []
                    sortKey: page.m.sort || ""
                    sortDesc: !!page.m.desc
                    selectedKey: backend.ui.selectedTicker
                    columns: page.columns
                    onSortRequested: function (key) { backend.sortMarkets(key) }
                    onRowClicked: function (row) { backend.select(row.ticker) }
                    onRowActivated: function (row) { backend.select(row.ticker) }
                }
                Pager {
                    Layout.fillWidth: true
                    page: page.m.page || 1
                    pages: page.m.pages || 1
                    total: page.m.total || 0
                    unit: "markets"
                    busy: page.busy
                    onPrevious: backend.pageMarkets(-1)
                    onNext: backend.pageMarkets(1)
                }
            }
        }
        Panel {
            Layout.preferredWidth: page.narrow ? -1 : Math.min(470, Math.max(400, page.width * 0.34))
            Layout.fillWidth: page.narrow
            Layout.fillHeight: !page.narrow
            Layout.preferredHeight: page.narrow ? 780 : -1
            MarketDetail { anchors.fill: parent; anchors.margins: 16 }
        }
    }
}
