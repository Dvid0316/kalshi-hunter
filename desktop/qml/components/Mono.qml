import QtQuick
import ".."

// Fixed-pitch numerals so prices and money line up in columns.
Text {
    color: Theme.ink
    font.family: Theme.mono
    font.pixelSize: Theme.fsSm + 1
    elide: Text.ElideRight
}
