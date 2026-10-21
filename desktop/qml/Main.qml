import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."
import "components"

// Kalshi Hunter — offline research desktop + personal ledger. Application shell.
ApplicationWindow {
    id: root
    width: 1440
    height: 960
    minimumWidth: 900
    minimumHeight: 620
    visible: true
    color: Theme.bg
    title: "Kalshi Hunter" + (ui.sample ? "  ·  SAMPLE DATA" : "") + "  ·  " + ui.page

    readonly property var ui: backend.ui
    readonly property var ov: backend.overview
    readonly property bool compact: width < 1180               // sidebar collapses to icons
    readonly property int sidebarWidth: compact ? 68 : 214
    readonly property int margin: width < 1000 ? 18 : 28
    readonly property string page: ui.page
    property bool focusOnTextInput: activeFocusItem !== null && activeFocusItem !== undefined && activeFocusItem.hasOwnProperty("cursorPosition")

    readonly property var pageFiles: ({
        "Overview": "OverviewPage", "Markets": "MarketsPage", "Research": "ForecastPage", "Strategy": "ForecastPage",
        "Alerts": "AlertsPage", "Positions": "PositionsPage", "History": "HistoryPage", "Journal": "JournalPage",
        "Accuracy": "AccuracyPage", "Evidence": "EvidencePage"
    })
    readonly property var glyphs: ({
        "Overview": "◈", "Markets": "▤", "Research": "◉", "Strategy": "◇", "Alerts": "△",
        "Positions": "▣", "History": "↗", "Journal": "✎", "Accuracy": "◎", "Evidence": "≡"
    })
    readonly property var subtitles: ({
        "Overview": "A clear view of your preserved research universe and its freshness.",
        "Markets": "Search, filter and sort every market in the snapshot. Quotes are archived, not live.",
        "Research": "Track A · Researched paper forecasts. Experimental estimates, never pooled with strategies.",
        "Strategy": "Track B · The frozen flb_v1 paper strategy. A separate evaluation cohort.",
        "Alerts": "Qualified opportunities appear here. Screened candidates are shown separately and are not alerts.",
        "Positions": "Your own open and closed positions, from trades you import or record. Never inferred from paper forecasts.",
        "History": "Your actual transactions and settlements, plus the paper entries recorded by research.",
        "Journal": "Your trading notes, and your decisions side by side with Grok's recorded research.",
        "Accuracy": "Forecast quality needs resolved outcomes, not confident estimates.",
        "Evidence": "Provenance, integrity, documents and diagnostics."
    })
    readonly property var pageHints: ({
        "Overview": "Ctrl+1", "Markets": "Ctrl+2", "Research": "Ctrl+3", "Strategy": "Ctrl+4", "Alerts": "Ctrl+5",
        "Positions": "Ctrl+6", "History": "Ctrl+7", "Journal": "Ctrl+8", "Accuracy": "Ctrl+9", "Evidence": "Ctrl+0"
    })

    // ------------------------------------------------------------------ shortcuts
    Repeater {
        model: ui.pages
        delegate: Item {
            required property string modelData
            required property int index
            Shortcut { sequence: "Ctrl+" + ((index + 1) % 10); onActivated: backend.navigate(modelData) }
        }
    }
    Shortcut { sequence: "Ctrl+K"; onActivated: backend.requestSearchFocus() }
    Shortcut { sequence: "/"; enabled: !root.focusOnTextInput; onActivated: backend.requestSearchFocus() }
    Shortcut { sequences: ["F5", "Ctrl+R"]; onActivated: backend.refresh() }
    Shortcut { sequences: ["F1", "Shift+?"]; enabled: !root.focusOnTextInput || true; onActivated: shortcutsDialog.open() }
    Shortcut { sequence: "Ctrl+,"; onActivated: settingsDialog.open() }
    Shortcut { sequence: "Alt+Left"; onActivated: backend.stepPage(-1) }
    Shortcut { sequence: "Alt+Right"; onActivated: backend.stepPage(1) }
    Shortcut { sequence: "Ctrl+Q"; onActivated: Qt.quit() }

    Connections {
        target: backend
        function onToast(message, kind) { toast.show(message, kind) }
        function onDialogRequested(name) {
            if (name === "shortcuts") shortcutsDialog.open()
            else if (name === "settings") settingsDialog.open()
            else if (name === "import") importDialog.open()
            else if (name === "record") recordDialog.open()
        }
    }

    // ------------------------------------------------------------------ sidebar
    Rectangle {
        id: sidebar
        width: root.sidebarWidth
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        color: Theme.sidebar
        border.color: "#203045"
        Accessible.role: Accessible.PageTabList
        Accessible.name: "Main navigation"
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: root.compact ? 8 : 16
            spacing: 4
            Row {
                spacing: 10
                Layout.preferredHeight: 64
                Layout.alignment: root.compact ? Qt.AlignHCenter : Qt.AlignLeft
                Rectangle {
                    width: 34; height: 34; radius: 9; color: "#174b4a"; anchors.verticalCenter: parent.verticalCenter
                    Text { anchors.centerIn: parent; text: "K"; font.pixelSize: 22; font.weight: Font.Bold; color: Theme.accent }
                }
                Column {
                    visible: !root.compact
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 3
                    Txt { text: "KALSHI"; font.pixelSize: 17; font.weight: Font.Bold; font.letterSpacing: 2 }
                    Small { text: "HUNTER"; font.pixelSize: 10; font.letterSpacing: 3 }
                }
            }
            Repeater {
                model: ui.pages
                delegate: NavButton {
                    required property string modelData
                    Layout.fillWidth: true
                    page: modelData
                    glyph: root.glyphs[modelData]
                    current: root.page === modelData
                    compact: root.compact
                    hint: root.pageHints[modelData]
                    onClicked: backend.navigate(modelData)
                }
            }
            Item { Layout.fillHeight: true }
            Tag { visible: !root.compact; label: ui.sample ? "SAMPLE ACCOUNT" : "OFFLINE SNAPSHOT"; tint: ui.sample ? Theme.sample : Theme.accent }
            Small { visible: !root.compact; text: ui.sample ? "Hypothetical figures" : "No account connected"; font.pixelSize: 11 }
            Small { visible: !root.compact; text: "Research & paper only"; font.pixelSize: 11 }
            Btn { visible: !root.compact; text: "Shortcuts  F1"; implicitHeight: 28; Layout.fillWidth: true; onClicked: shortcutsDialog.open() }
            Btn { visible: !root.compact; text: "Settings"; implicitHeight: 28; Layout.fillWidth: true; onClicked: settingsDialog.open() }
            Small { visible: !root.compact; text: "v" + appVersion; font.pixelSize: 10; color: Theme.faint }
        }
    }

    // ------------------------------------------------------------------ main column
    ColumnLayout {
        anchors.left: sidebar.right
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.margins: root.margin
        anchors.topMargin: 18
        anchors.bottomMargin: 10
        spacing: 12

        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            Small { text: "WORKSPACE  /  " + root.page.toUpperCase(); font.letterSpacing: 1.2; Layout.fillWidth: true }
            Tag { label: "ARCHIVED SNAPSHOT"; tint: Theme.warn }
            Tag { label: ui.connection.label; tint: Theme.muted }
            Tag { label: ui.sample ? "SAMPLE ACCOUNT" : "ACCOUNT DISCONNECTED"; tint: ui.sample ? Theme.sample : Theme.muted }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 16
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 6
                Txt { text: root.page === "Overview" ? "Research overview" : root.page; font.pixelSize: Theme.fsXxl; font.weight: Font.DemiBold
                      Accessible.role: Accessible.Heading; Accessible.name: text }
                Small { text: root.subtitles[root.page] || ""; Layout.fillWidth: true; font.pixelSize: Theme.fsSm + 1; wrapMode: Text.WordWrap; elide: Text.ElideNone }
            }
            ColumnLayout {
                visible: root.width > 1040
                spacing: 4
                Small { text: "SNAPSHOT AS OF"; font.pixelSize: 10; font.letterSpacing: 1; Layout.alignment: Qt.AlignRight }
                Txt { text: ov.asof || "Loading…"; font.pixelSize: Theme.fsSm + 1; Layout.alignment: Qt.AlignRight }
                Small { text: ov.freshness ? ov.freshness.age + " old · not live" : ""; font.pixelSize: Theme.fsXs; color: Theme.warn; Layout.alignment: Qt.AlignRight }
            }
        }
        Banner {
            kind: "sample"
            text: ui.sample ? "SAMPLE DATA · These trades, settlements and journal entries are invented for demonstration. They are not your account and no figure here is real." : ""
        }
        Banner {
            kind: "warn"
            text: "Historical backtests are inconclusive. No trading advantage has been demonstrated. All quotes are archived, not live. You place every trade yourself."
        }
        Repeater {
            model: Object.keys(ui.errors)
            delegate: Banner {
                required property string modelData
                kind: "error"
                text: "Could not load " + modelData + ": " + ui.errors[modelData]
                actionText: "Retry"
                onActionClicked: backend.retry(modelData)
            }
        }

        ScrollView {
            id: scroller
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth
            clip: true
            ScrollBar.vertical.policy: ScrollBar.AsNeeded
            Loader {
                id: pageLoader
                width: scroller.availableWidth
                readonly property bool fillPage: item && item.fill === true
                height: item ? Math.max(fillPage ? Math.max(scroller.availableHeight, item.minHeight || 520) : item.implicitHeight, scroller.availableHeight) : scroller.availableHeight
                source: ui.ready ? "pages/" + root.pageFiles[root.page] + ".qml" : "pages/LoadingPage.qml"
                asynchronous: false
                onStatusChanged: if (status === Loader.Error) console.warn("Page failed to load: " + source)
            }
        }

        // status ribbon
        RowLayout {
            Layout.fillWidth: true
            spacing: 14
            Accessible.role: Accessible.StatusBar
            Accessible.name: "Status"
            Small {
                Layout.fillWidth: true
                font.pixelSize: 10
                font.letterSpacing: 0.5
                color: Theme.faint
                text: "READ-ONLY SNAPSHOT  •  NO SCANNER STARTED  •  LOCAL DATA ONLY  •  PAPER ≠ ACTUAL ACCOUNT  •  " + ui.connection.label
            }
            BusyDots { visible: ui.loading.length > 0 }
            Small { visible: ui.loading.length > 0; text: "Loading " + ui.loading.join(", "); font.pixelSize: 10 }
        }
    }

    Toast { id: toast; anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 46 }
    ShortcutsDialog { id: shortcutsDialog }
    SettingsDialog { id: settingsDialog }
    ImportDialog { id: importDialog }
    RecordDialog { id: recordDialog }
}
