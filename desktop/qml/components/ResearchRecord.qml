import QtQuick
import QtQuick.Layouts
import ".."

// One preserved research record: method, uncertainty, counter-evidence, auditor notes, sources, second-hand figures.
Rectangle {
    id: rec
    property var record: ({})
    Layout.fillWidth: true
    implicitHeight: col.implicitHeight + 2 * Theme.pad
    radius: 10
    color: Theme.panelAlt
    border.color: record.is_correction ? Theme.warnBorder : Theme.border
    Accessible.role: Accessible.Grouping
    Accessible.name: "Research record " + record.id + (record.is_correction ? " (correction)" : "")
    ColumnLayout {
        id: col
        anchors.fill: parent
        anchors.margins: Theme.pad
        spacing: 9
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Txt { text: "Research record #" + rec.record.id; font.weight: Font.DemiBold; font.pixelSize: Theme.fsMd - 1 }
            Tag { visible: !!rec.record.is_correction; label: "Correction" + (rec.record.corrects ? " of #" + rec.record.corrects : ""); tint: Theme.warn }
            Item { Layout.fillWidth: true }
            Small { text: rec.record.when || "" }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 16
            Column { Small { text: "P(YES)"; font.pixelSize: Theme.fsXs } Mono { text: rec.record.probability || "—"; font.pixelSize: Theme.fsMd } }
            Column { Small { text: "Researcher's band"; font.pixelSize: Theme.fsXs } Mono { text: rec.record.band || "—"; font.pixelSize: Theme.fsMd } }
            Column { Small { text: "Author"; font.pixelSize: Theme.fsXs } Small { text: rec.record.author || "—"; color: Theme.ink } }
        }
        Small { text: "METHOD"; font.pixelSize: Theme.fsXs; font.letterSpacing: 1 }
        Text { Layout.fillWidth: true; text: rec.record.method || ""; color: Theme.ink; wrapMode: Text.WordWrap; font.pixelSize: Theme.fsSm + 1; lineHeight: 1.3 }
        Small { visible: !!rec.record.counter_evidence; text: "COUNTER-EVIDENCE"; font.pixelSize: Theme.fsXs; font.letterSpacing: 1 }
        Text { visible: !!rec.record.counter_evidence; Layout.fillWidth: true; text: rec.record.counter_evidence || ""; color: Theme.muted; wrapMode: Text.WordWrap; font.pixelSize: Theme.fsSm + 1; lineHeight: 1.3 }
        Small { visible: !!rec.record.auditor; text: "AUDITOR NOTES"; font.pixelSize: Theme.fsXs; font.letterSpacing: 1 }
        Text { visible: !!rec.record.auditor; Layout.fillWidth: true; text: rec.record.auditor || ""; color: Theme.warn; wrapMode: Text.WordWrap; font.pixelSize: Theme.fsSm + 1; lineHeight: 1.3 }
        Small { visible: (rec.record.secondhand_list || []).length > 0; text: "SECOND-HAND FIGURES"; font.pixelSize: Theme.fsXs; font.letterSpacing: 1 }
        Repeater {
            model: rec.record.secondhand_list || []
            delegate: Text { required property var modelData; Layout.fillWidth: true; color: Theme.muted; wrapMode: Text.WordWrap; font.pixelSize: Theme.fsSm
                             text: (modelData.figure || "") + (modelData.via_url ? "  via " + modelData.via_url : "") + (modelData.original_source ? "  (original: " + modelData.original_source + ")" : "") }
        }
        Small { text: "SOURCES (" + (rec.record.source_list || []).length + ")"; font.pixelSize: Theme.fsXs; font.letterSpacing: 1 }
        SourceList { Layout.fillWidth: true; urls: rec.record.source_list || [] }
    }
}
