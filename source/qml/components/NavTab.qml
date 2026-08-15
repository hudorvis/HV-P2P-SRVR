import QtQuick

Rectangle {
    id: root
    property string label: "Run"
    property string glyph: "▷"
    property bool selected: false
    signal triggered()
    color: mouse.containsMouse || selected ? "#10202c" : "#0d161f"
    border.width: 1
    border.color: "#263846"
    implicitHeight: 48
    Row {
        anchors.centerIn: parent
        spacing: 12
        Text {
            text: root.glyph
            color: root.selected ? "#20b7f5" : "#aab5bf"
            font.family: Qt.platform.os === "osx" ? "SF Pro Display" : "Segoe UI Symbol"
            font.pixelSize: 26
        }
        Text {
            text: root.label
            color: root.selected ? "#f3f7fa" : "#d2dae1"
            font.family: Qt.platform.os === "osx" ? "SF Pro Text" : "Segoe UI"
            font.pixelSize: 18
            font.weight: Font.Medium
        }
    }
    Rectangle {
        visible: root.selected
        height: 3
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        color: "#20b7f5"
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.triggered()
    }
}
