import QtQuick

Item {
    id: root
    property bool checked: false
    signal toggled(bool checked)
    implicitWidth: 22; implicitHeight: 22
    Rectangle { anchors.centerIn:parent; width:17; height:17; radius:4; color:root.checked?"#0d6389":"#0a121a"; border.width:1; border.color:root.checked?"#27c4ff":"#3b4a56" }
    Text { anchors.centerIn:parent; text:root.checked?"✓":""; color:"white"; font.pixelSize:13; font.weight:Font.Bold }
    MouseArea { anchors.fill:parent; cursorShape:Qt.PointingHandCursor; onClicked:{root.checked=!root.checked;root.toggled(root.checked)} }
}
