import QtQuick
import QtQuick.Controls

TextField {
    id: root
    implicitHeight: 34
    color: "#e8eef3"
    selectionColor: "#1b89ba"
    selectedTextColor: "white"
    placeholderTextColor: "#657483"
    leftPadding: 10
    rightPadding: 10
    font.family: Qt.platform.os === "osx" ? "SF Pro Text" : "Segoe UI"
    font.pixelSize: 13
    background: Rectangle {
        color: root.activeFocus ? "#101f2a" : "#0a121a"
        radius: 6
        border.width: 1
        border.color: root.activeFocus ? "#20b7f5" : "#2b3c4a"
    }
}
