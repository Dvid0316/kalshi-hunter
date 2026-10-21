import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Sortable, keyboard-navigable table.
//   columns: [{key, title, width, fill, align, mono, tone, sortKey, sub, tag}]
//     key      field shown      sub      optional second line field (smaller, muted)
//     width    fixed pixels     fill     true => takes the remaining space
//     tone     "signed" | "accent" | "accent2" | "muted"      tag: field rendered as a chip
//     sortKey  when set, the header is clickable and emits sortRequested(sortKey)
//   Up/Down move the highlight, Enter activates, mouse click selects.
ColumnLayout {
    id: table
    property var columns: []
    property var rows: []
    property string sortKey: ""
    property bool sortDesc: false
    property string keyField: "ticker"
    property string selectedKey: ""
    property int rowHeight: 56
    property bool autoHeight: false          // true: grow to fit rows (inside a scrolling page)
    property bool busy: false
    property string emptyText: "Nothing to show."
    property string accessibleName: "Table"
    property alias view: list
    signal sortRequested(string key)
    signal rowClicked(var row, int index)
    signal rowActivated(var row, int index)
    spacing: 0
    Accessible.role: Accessible.Table
    Accessible.name: accessibleName

    // ---- header
    Item {
        Layout.fillWidth: true
        Layout.preferredHeight: 34
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 12
            anchors.rightMargin: 12
            spacing: 10
            Repeater {
                model: table.columns
                delegate: Item {
                    id: head
                    required property var modelData
                    objectName: modelData.sortKey ? "sort_" + modelData.sortKey : ""
                    Layout.preferredWidth: modelData.fill ? 40 : (modelData.width || 80)
                    Layout.fillWidth: !!modelData.fill
                    Layout.fillHeight: true
                    readonly property bool active: !!modelData.sortKey && table.sortKey === modelData.sortKey
                    activeFocusOnTab: !!modelData.sortKey
                    Accessible.role: Accessible.Button
                    Accessible.name: modelData.title + (modelData.sortKey ? (active ? (table.sortDesc ? ", sorted descending" : ", sorted ascending") : ", sortable") : "")
                    Accessible.onPressAction: if (modelData.sortKey) table.sortRequested(modelData.sortKey)
                    Keys.onReturnPressed: if (modelData.sortKey) table.sortRequested(modelData.sortKey)
                    Keys.onSpacePressed: if (modelData.sortKey) table.sortRequested(modelData.sortKey)
                    Rectangle { anchors.fill: parent; radius: 4; color: "transparent"; border.color: head.activeFocus ? Theme.accent : "transparent"; border.width: 2 }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.left: modelData.align === "right" ? undefined : parent.left
                        anchors.right: modelData.align === "right" ? parent.right : undefined
                        width: Math.min(implicitWidth, parent.width)
                        text: modelData.title.toUpperCase() + (head.active ? (table.sortDesc ? "  ▼" : "  ▲") : "")
                        color: head.active ? Theme.accent : Theme.muted
                        font.pixelSize: Theme.fsXs
                        font.weight: Font.DemiBold
                        font.letterSpacing: 0.6
                        elide: Text.ElideRight
                    }
                    MouseArea {
                        anchors.fill: parent
                        enabled: !!modelData.sortKey
                        hoverEnabled: true
                        cursorShape: modelData.sortKey ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: table.sortRequested(modelData.sortKey)
                    }
                }
            }
        }
    }
    Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.border }

    // ---- body
    ListView {
        id: list
        Layout.fillWidth: true
        Layout.fillHeight: !table.autoHeight
        Layout.preferredHeight: table.autoHeight ? Math.max(1, table.rows.length) * (table.rowHeight + 4) : -1
        interactive: !table.autoHeight
        clip: true
        spacing: 4
        model: table.rows
        keyNavigationEnabled: true
        focus: false
        activeFocusOnTab: true
        highlightFollowsCurrentItem: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { policy: table.autoHeight ? ScrollBar.AlwaysOff : ScrollBar.AsNeeded }
        Keys.onReturnPressed: if (currentIndex >= 0 && currentIndex < table.rows.length) table.rowActivated(table.rows[currentIndex], currentIndex)
        onActiveFocusChanged: if (activeFocus && currentIndex < 0 && table.rows.length > 0) currentIndex = 0
        Accessible.role: Accessible.List
        Accessible.name: table.accessibleName + " rows"

        delegate: Rectangle {
            id: rowItem
            required property var modelData
            required property int index
            objectName: "row_" + index
            width: ListView.view.width
            height: table.rowHeight
            radius: 8
            readonly property bool selected: table.selectedKey !== "" && String(modelData[table.keyField]) === table.selectedKey
            color: selected ? Theme.panelSelected : (hover.hovered ? Theme.panelHover : (index % 2 === 0 ? Theme.panelAlt : Theme.panel))
            border.color: (list.activeFocus && list.currentIndex === index) ? Theme.accent : "transparent"
            border.width: 2
            Accessible.role: Accessible.ListItem
            Accessible.name: {
                var parts = []
                for (var i = 0; i < table.columns.length; i++) {
                    var c = table.columns[i]
                    var v = modelData[c.key]
                    if (v !== undefined && v !== null && String(v).length) parts.push(c.title + " " + v)
                }
                return parts.join(", ")
            }
            Accessible.selected: selected
            Accessible.onPressAction: table.rowActivated(modelData, index)
            HoverHandler { id: hover }
            TapHandler {
                onTapped: { list.currentIndex = index; table.rowClicked(modelData, index) }
                onDoubleTapped: table.rowActivated(modelData, index)
            }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 10
                Repeater {
                    model: table.columns
                    delegate: Item {
                        id: cell
                        required property var modelData
                        readonly property var row: rowItem.modelData
                        readonly property var value: row[modelData.key]
                        Layout.preferredWidth: modelData.fill ? 40 : (modelData.width || 80)
                        Layout.fillWidth: !!modelData.fill
                        Layout.fillHeight: true
                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width
                            spacing: 3
                            Loader {
                                width: parent.width
                                sourceComponent: cell.modelData.tag ? chip : (cell.modelData.mono ? monoText : plainText)
                            }
                            Small {
                                visible: !!cell.modelData.sub && String(cell.row[cell.modelData.sub] || "").length > 0
                                text: cell.modelData.sub ? String(cell.row[cell.modelData.sub] || "") : ""
                                width: parent.width
                                font.pixelSize: Theme.fsXs
                                horizontalAlignment: cell.modelData.align === "right" ? Text.AlignRight : Text.AlignLeft
                            }
                        }
                        Component { id: plainText
                            Txt {
                                width: parent ? parent.width : 0
                                text: cell.value === undefined || cell.value === null ? "" : String(cell.value)
                                color: Theme.toneColor(cell.modelData.tone, cell.value)
                                font.pixelSize: Theme.fsSm + 1
                                font.capitalization: cell.modelData.capitalize ? Font.Capitalize : Font.MixedCase
                                horizontalAlignment: cell.modelData.align === "right" ? Text.AlignRight : Text.AlignLeft
                            }
                        }
                        Component { id: monoText
                            Mono {
                                width: parent ? parent.width : 0
                                text: cell.value === undefined || cell.value === null ? "" : String(cell.value)
                                color: Theme.toneColor(cell.modelData.tone, cell.value)
                                horizontalAlignment: cell.modelData.align === "right" ? Text.AlignRight : Text.AlignLeft
                            }
                        }
                        Component { id: chip
                            Tag {
                                label: cell.value === undefined || cell.value === null ? "" : String(cell.value)
                                visible: label.length > 0
                                tint: Theme.toneColor(cell.modelData.tone, cell.value)
                            }
                        }
                    }
                }
            }
        }
        // empty / busy overlay
        Column {
            anchors.centerIn: parent
            visible: table.rows.length === 0
            spacing: 12
            BusyDots { visible: table.busy; anchors.horizontalCenter: parent.horizontalCenter }
            Small { text: table.busy ? "Loading…" : table.emptyText; anchors.horizontalCenter: parent.horizontalCenter }
        }
    }
}
