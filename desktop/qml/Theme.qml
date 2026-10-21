pragma Singleton
import QtQuick

// Design tokens for Kalshi Hunter. Dark navy + teal language inherited from the original build.
// Contrast of every text/background pair used in the UI is verified by tests/test_qml_theme.py (WCAG AA, 4.5:1).
QtObject {
    // surfaces
    readonly property color bg: "#0b111a"
    readonly property color sidebar: "#0f1824"
    readonly property color panel: "#121d2a"
    readonly property color panelAlt: "#152333"
    readonly property color panelHover: "#1b2c3f"
    readonly property color panelSelected: "#203b49"
    readonly property color input: "#0d1723"
    readonly property color border: "#233145"
    readonly property color borderStrong: "#34506b"
    // text
    readonly property color ink: "#e7eef7"
    readonly property color muted: "#9aadc4"
    readonly property color faint: "#90a5bd"
    // accents
    readonly property color accent: "#55dcc8"
    readonly property color accentBg: "#173c46"
    readonly property color accent2: "#8eaaff"
    readonly property color gain: "#6fd6a0"
    readonly property color loss: "#f18a89"
    readonly property color warn: "#e0cb94"
    readonly property color warnBg: "#25251f"
    readonly property color warnBorder: "#4a452c"
    readonly property color danger: "#f6a09f"
    readonly property color dangerBg: "#2a1a1f"
    readonly property color dangerBorder: "#5a2f38"
    readonly property color sampleBg: "#2b2113"
    readonly property color sampleBorder: "#6b5322"
    readonly property color sample: "#f0c36a"

    // type scale (pixels)
    readonly property int fsXs: 11
    readonly property int fsSm: 12
    readonly property int fsMd: 14
    readonly property int fsLg: 17
    readonly property int fsXl: 22
    readonly property int fsXxl: 30
    readonly property string mono: "Noto Sans Mono"

    // shape
    readonly property int radius: 12
    readonly property int radiusSm: 7
    readonly property int gap: 16
    readonly property int pad: 18

    // layout breakpoints (content width in px)
    readonly property int wide: 1240
    readonly property int medium: 980

    function toneColor(tone, value) {
        if (tone === "signed") {
            var v = String(value)
            if (v.charAt(0) === "+") return gain
            if (v.charAt(0) === "-") return loss
            return ink
        }
        if (tone === "accent") return accent
        if (tone === "accent2") return accent2
        if (tone === "muted") return muted
        return ink
    }
}
