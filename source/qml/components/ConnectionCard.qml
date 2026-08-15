import QtQuick

Rectangle {
    id: root
    property string label: "CTRL"
    property bool connected: false
    radius: 7
    color: "#0f1923"
    border.width: 1
    border.color: "#2b3b48"
    implicitHeight: 46
    Row {
        anchors.centerIn: parent
        spacing: 10
        Rectangle {
            width: 13; height: 13; radius: 7
            color: root.connected ? "#51d35e" : "#596672"
            border.width: 1
            border.color: root.connected ? "#73ef7e" : "#6f7b85"
        }
        Text {
            text: root.label
            color: "#edf2f6"
            font.family: Qt.platform.os === "osx" ? "SF Pro Text" : "Segoe UI"
            font.pixelSize: 17
            font.weight: Font.Medium
        }
    }
}
