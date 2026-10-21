import QtQuick
import ".."

// Primary text. Uses the application font (Inter -> Noto Sans -> DejaVu Sans).
Text {
    color: Theme.ink
    font.pixelSize: Theme.fsMd
    elide: Text.ElideRight
}
