import QtQuick
import ".."

// Three pulsing dots: shown while a read is in flight. Motion is gentle and optional (no information is carried by it).
Row {
    spacing: 6
    Repeater {
        model: 3
        delegate: Rectangle {
            required property int index
            width: 8; height: 8; radius: 4
            color: Theme.accent
            SequentialAnimation on opacity {
                loops: Animation.Infinite
                PauseAnimation { duration: index * 160 }
                NumberAnimation { to: 0.25; duration: 420 }
                NumberAnimation { to: 1.0; duration: 420 }
                PauseAnimation { duration: (2 - index) * 160 }
            }
        }
    }
}
