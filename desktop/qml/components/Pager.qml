import QtQuick
import QtQuick.Layouts
import ".."

// Page navigation: "Page 3 of 120 · 5,996 results" with Previous / Next.
RowLayout {
    id: pager
    property int page: 1
    property int pages: 1
    property int total: 0
    property string unit: "results"
    property bool busy: false
    signal previous()
    signal next()
    spacing: 10
    Small {
        Layout.fillWidth: true
        text: pager.total === 0 ? "No " + pager.unit : "Page " + pager.page.toLocaleString(Qt.locale("en_US"), "f", 0) + " of " + pager.pages.toLocaleString(Qt.locale("en_US"), "f", 0)
              + "  ·  " + pager.total.toLocaleString(Qt.locale("en_US"), "f", 0) + " " + pager.unit
        Accessible.role: Accessible.StaticText
        Accessible.name: text
    }
    BusyDots { visible: pager.busy }
    Btn { text: "Previous"; implicitWidth: 88; enabled: pager.page > 1; onClicked: pager.previous(); Accessible.description: "Previous page (Alt+Left)" }
    Btn { text: "Next"; implicitWidth: 72; enabled: pager.page < pager.pages; onClicked: pager.next(); Accessible.description: "Next page (Alt+Right)" }
}
