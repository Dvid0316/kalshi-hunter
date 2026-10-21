import QtQuick
import QtQuick.Layouts
import ".."
import "../components"

// Shown until the first snapshot read completes.
Item {
    property bool fill: true
    property int minHeight: 360
    EmptyState {
        anchors.fill: parent
        anchors.margins: 4
        busy: true
        badge: "READ ONLY"
        heading: backend.ui.errors.overview ? "Unable to load the snapshot" : "Loading preserved research"
        description: backend.ui.errors.overview || "Reading the local, isolated snapshot on a background thread."
        Btn { visible: !!backend.ui.errors.overview; text: "Retry"; primary: true; onClicked: backend.retry("overview") }
    }
}
