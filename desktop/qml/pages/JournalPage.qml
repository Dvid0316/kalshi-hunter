import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

// Your trading journal, and your decisions next to Grok's recorded research (descriptive, never a scorecard).
Item {
    id: page
    property bool fill: true
    property int minHeight: 560
    property string view: "journal"
    readonly property var j: backend.journal
    readonly property var cmp: backend.comparison
    property int editId: 0
    readonly property bool narrow: width < 1060
    property string statusText: ""

    function loadEntry(e) {
        editId = e ? e.id : 0
        title.text = e ? e.title : ""
        ticker.text = e && e.ticker ? e.ticker : ""
        body.text = e ? e.body : ""
        tags.text = e ? e.tags : ""
        price.text = e && e.planned_price ? String(Math.round(parseFloat(e.planned_price) * 10000) / 100) : ""
        prob.text = e && e.my_prob ? String(Math.round(parseFloat(e.my_prob) * 10000) / 100) : ""
        side.select(e && e.planned_side ? e.planned_side : "")
        etype.select(e ? e.entry_type : "note")
        statusText = ""
    }
    Connections {
        target: backend
        function onActionDone(name, result) {
            if (name === "journal") { page.statusText = result.ok ? "Saved" : result.error; if (result.ok && result.id) page.editId = result.id }
            if (name === "journal_delete" && result.ok) page.loadEntry(null)
        }
        function onFocusSearch() { if (backend.ui.page === "Journal") jsearch.forceActiveFocus() }
    }
    Component.onCompleted: loadEntry(null)

    Panel {
        anchors.fill: parent
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 16
            spacing: 10
            RowLayout {
                Layout.fillWidth: true
                SegmentedControl { accessibleName: "Journal view"; current: page.view
                                   options: [{value: "journal", label: "Journal"}, {value: "compare", label: "Decisions vs research"}]
                                   onPicked: function (v) { page.view = v } }
                Item { Layout.fillWidth: true }
                Tag { visible: backend.ui.sample; label: "SAMPLE ENTRIES"; tint: Theme.sample }
            }

            // ---------------------------------------------------------------- journal
            GridLayout {
                visible: page.view === "journal"
                Layout.fillWidth: true
                Layout.fillHeight: true
                columns: page.narrow ? 1 : 2
                columnSpacing: Theme.gap
                rowSpacing: Theme.gap
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredWidth: 420
                    spacing: 8
                    RowLayout {
                        Layout.fillWidth: true
                        SearchField { id: jsearch; Layout.fillWidth: true; placeholderText: "Search notes, tags, tickers"; onSubmitted: function (v) { backend.searchJournal(v) } }
                        Btn { text: "New entry"; primary: true; onClicked: page.loadEntry(null) }
                    }
                    DataTable {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        accessibleName: "Journal entries"
                        rowHeight: 62
                        keyField: "id"
                        selectedKey: String(page.editId)
                        emptyText: "No journal entries yet. Write one on the right."
                        busy: backend.ui.loading.indexOf("journal") >= 0
                        rows: page.j.entries || []
                        columns: [{key: "title", title: "Entry", fill: true, sub: "when"}, {key: "entry_type", title: "Type", width: 84, tone: "muted", capitalize: true}]
                        onRowClicked: function (row) { page.loadEntry(row) }
                    }
                }
                ScrollView {
                    id: formScroll
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredWidth: 520
                    contentWidth: availableWidth
                    clip: true
                    ColumnLayout {
                        width: formScroll.availableWidth - 8
                        spacing: 10
                        Txt { text: page.editId ? "Edit entry #" + page.editId : "New entry"; font.pixelSize: Theme.fsLg; font.weight: Font.DemiBold }
                        component F: TextField {
                            property string accessibleName: placeholderText
                            Layout.fillWidth: true
                            placeholderTextColor: Theme.faint; color: Theme.ink; selectByMouse: true
                            Accessible.name: accessibleName
                            background: Rectangle { color: Theme.input; radius: Theme.radiusSm; border.color: parent && parent.activeFocus ? Theme.accent : Theme.borderStrong; border.width: parent && parent.activeFocus ? 2 : 1 }
                        }
                        F { id: title; placeholderText: "Title" }
                        GridLayout {
                            Layout.fillWidth: true
                            columns: 2
                            columnSpacing: 10
                            rowSpacing: 10
                            F { id: ticker; placeholderText: "Market ticker (optional)" }
                            Select { id: etype; accessibleName: "Entry type"; Layout.fillWidth: true; model: [{value: "note", label: "Note"}, {value: "pre_trade", label: "Before a trade"}, {value: "post_trade", label: "After a trade"}] }
                            Select { id: side; accessibleName: "Planned side"; Layout.fillWidth: true; model: [{value: "", label: "No planned side"}, {value: "yes", label: "Planned: YES"}, {value: "no", label: "Planned: NO"}] }
                            F { id: price; placeholderText: "Planned price, cents"; validator: DoubleValidator { bottom: 0; top: 100; decimals: 3 } }
                            F { id: prob; placeholderText: "My P(YES), percent"; validator: DoubleValidator { bottom: 0; top: 100; decimals: 2 } }
                            F { id: tags; placeholderText: "Tags, comma separated" }
                        }
                        TextArea {
                            id: body
                            Layout.fillWidth: true
                            Layout.preferredHeight: 180
                            placeholderText: "Your reasoning, what would change your mind, what you will do next…"
                            placeholderTextColor: Theme.faint
                            color: Theme.ink
                            wrapMode: TextEdit.Wrap
                            selectByMouse: true
                            font.pixelSize: Theme.fsMd - 1
                            Accessible.name: "Entry text"
                            background: Rectangle { color: Theme.input; radius: Theme.radiusSm; border.color: body.activeFocus ? Theme.accent : Theme.borderStrong; border.width: body.activeFocus ? 2 : 1 }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10
                            Btn { text: "Save entry"; primary: true; enabled: title.text.trim().length > 0
                                  onClicked: backend.saveJournal(page.editId, title.text, body.text, ticker.text.trim(), etype.currentValue || "note", tags.text, side.currentValue || "", price.text, prob.text) }
                            Btn { visible: page.editId > 0; text: "Delete"; danger: true; onClicked: backend.deleteJournal(page.editId) }
                            Small { text: page.statusText; color: Theme.accent; Layout.fillWidth: true }
                        }
                        Small { Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone; font.pixelSize: Theme.fsXs
                                text: "Every save keeps the previous wording (edit history), so you can judge your past reasoning honestly. Deleting hides an entry; it does not erase its history." }
                        Banner {
                            kind: "info"
                            text: {
                                var es = page.j.entries || []
                                for (var i = 0; i < es.length; i++) if (es[i].id === page.editId && es[i].research_note) return "Linked research: " + es[i].research_note
                                return ""
                            }
                        }
                    }
                }
            }

            // ---------------------------------------------------------------- comparison
            ColumnLayout {
                visible: page.view === "compare"
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 8
                Banner { kind: "warn"; text: page.cmp.note || "" }
                EmptyState { visible: page.cmp.empty === true; Layout.fillWidth: true; Layout.preferredHeight: 160; heading: "Nothing to compare yet"
                             description: "Record or import your trades. Markets where Grok recorded research and you also traded (or wrote a note) appear here." }
                DataTable {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    accessibleName: "Your decisions versus recorded research"
                    rowHeight: 62
                    keyField: "ticker"
                    emptyText: "No market has both recorded research and your activity."
                    busy: backend.ui.loading.indexOf("comparison") >= 0
                    rows: page.cmp.rows || []
                    columns: {
                        var c = [
                            {key: "ticker", title: "Market", fill: true, sub: "title"},
                            {key: "research_side", title: "Research side", width: 96, tone: "accent2"},
                            {key: "research_p", title: "Research P(YES)", width: 108, mono: true, align: "right"},
                            {key: "my_side", title: "Your side", width: 80, tone: "accent"},
                            {key: "relation", title: "Relation", width: 190}
                        ]
                        if (page.width > 1180) { c.push({key: "my_entry", title: "Your entry", width: 90, mono: true, align: "right"}); c.push({key: "lag", title: "Timing", width: 190}) }
                        c.push({key: "my_actual", title: "Your actual P&L", width: 120, mono: true, align: "right", tone: "signed"})
                        c.push({key: "my_estimates", title: "Your P(YES)", width: 90, mono: true, align: "right"})
                        return c
                    }
                }
            }
        }
    }
}
