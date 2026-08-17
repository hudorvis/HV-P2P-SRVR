import QtQuick 2.15
Item {
    id: root
    property bool checked: false
    property bool interactive: true
    signal toggled(bool checked)
    implicitWidth: 30
    implicitHeight: 28

    // Full cell border matches the table treatment used by the locked Free-D
    // design; the actual checkbox remains centred inside it.
    Rectangle {
        anchors.fill: parent
        radius: 3
        color: root.interactive ? "#151a1d" : "#131719"
        border.width: 1
        border.color: root.interactive ? "#4e565a" : "#333a3d"
    }
    Rectangle {
        width: 15; height: 15; radius: 2
        anchors.centerIn: parent
        color: root.checked ? "#1e3524" : "#151a1d"
        border.width: 1
        border.color: root.checked ? "#62d64d" : root.interactive ? "#7a8386" : "#3f4649"
        Text { anchors.centerIn: parent; text: root.checked ? "✓" : ""; color: "#72ed21"; font.pixelSize: 11; font.bold: true }
    }
    MouseArea { anchors.fill: parent; enabled: root.interactive; cursorShape: Qt.PointingHandCursor; onClicked: root.toggled(!root.checked) }
}
