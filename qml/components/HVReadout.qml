import QtQuick 2.15
Rectangle {
    id: root
    property string text: ""
    property color textColor: "#edf0ef"
    property int horizontalAlignment: Text.AlignHCenter
    property bool disabled: false
    implicitHeight: 29
    radius: 3
    color: disabled ? "#131719" : "#151a1d"
    border.width: 1
    border.color: disabled ? "#333a3d" : "#4e565a"
    Text {
        anchors.fill: parent
        anchors.leftMargin: 7
        anchors.rightMargin: 7
        text: root.text
        color: root.disabled ? "#72797b" : root.textColor
        font.family: "Helvetica Neue"
        font.pixelSize: 12
        horizontalAlignment: root.horizontalAlignment
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
}
