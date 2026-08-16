import QtQuick 2.15
import QtQuick.Controls 2.15
Button {
    id: root
    property bool selected: false
    property color accent: "#62d64d"
    implicitHeight: 32
    implicitWidth: 78
    hoverEnabled: true
    font.family: "Helvetica Neue"
    font.pixelSize: 14
    contentItem: Text {
        text: root.text
        color: root.enabled ? (root.selected ? "#f5f7f6" : "#ecefee") : "#697074"
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        font: root.font
        elide: Text.ElideRight
    }
    background: Rectangle {
        radius: 4
        color: !root.enabled ? "#15191c" : root.down ? "#263129" : root.selected ? "#1e3524" : root.hovered ? "#22282c" : "#1a2024"
        border.width: 1
        border.color: root.selected ? root.accent : "#596064"
    }
}
