import QtQuick

Rectangle {
    id: root
    property string text: "Button"
    property string accent: "#20b7f5"
    property bool selected: false
    property bool danger: false
    property bool confirmRequired: false
    property bool armed: false
    signal triggered()
    implicitHeight: 38
    implicitWidth: 96
    radius: 7
    border.width: 1
    border.color: danger ? "#823b42" : (selected || mouse.containsMouse ? accent : "#344553")
    color: danger ? (mouse.containsMouse ? "#4b1e25" : "#281419")
                  : (selected ? "#0f2d3d" : (mouse.containsMouse ? "#152634" : "#111c27"))

    Text {
        anchors.centerIn: parent
        text: root.armed ? "Confirm?" : root.text
        color: root.danger ? "#ff8787" : (root.selected ? root.accent : "#e8eef3")
        font.family: Qt.platform.os === "osx" ? "SF Pro Text" : "Segoe UI"
        font.pixelSize: 14
        font.weight: Font.Medium
    }

    Timer {
        id: armTimer
        interval: 10000
        repeat: false
        onTriggered: root.armed = false
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: {
            if (!root.confirmRequired) {
                root.triggered()
                return
            }
            if (root.armed) {
                root.armed = false
                armTimer.stop()
                root.triggered()
            } else {
                root.armed = true
                armTimer.restart()
            }
        }
    }
}
