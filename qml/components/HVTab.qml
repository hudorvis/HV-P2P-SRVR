import QtQuick 2.15
import QtQuick.Controls 2.15
Button {
    id: root
    property bool selected: false
    property color accent: "#62d64d"
    implicitHeight: 34
    padding: 0
    hoverEnabled: true
    font.family: "Helvetica Neue"
    font.pixelSize: 13
    contentItem: Text {
        text: root.text
        color: root.selected ? root.accent : "#e5e8e7"
        font: root.font
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
    background: Item {
        Rectangle { anchors.fill: parent; color: root.hovered && !root.selected ? "#1c2226" : "transparent" }
        Rectangle { visible: root.selected; height: 2; anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; color: root.accent }
    }
}
