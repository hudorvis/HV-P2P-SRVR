import QtQuick 2.15
import QtQuick.Controls 2.15
TextField {
    id: root
    property color accent: "#62d64d"
    implicitHeight: 31
    selectByMouse: true
    color: "#edf0ef"
    selectionColor: "#355c3b"
    selectedTextColor: "#ffffff"
    placeholderTextColor: "#70777a"
    font.family: "Helvetica Neue"
    font.pixelSize: 13
    leftPadding: 9
    rightPadding: 9
    background: Rectangle {
        radius: 4
        color: "#151a1d"
        border.width: 1
        border.color: root.activeFocus ? root.accent : "#4e565a"
    }
}
