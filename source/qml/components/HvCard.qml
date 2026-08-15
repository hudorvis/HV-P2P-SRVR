import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root
    property string title: ""
    property string accent: "#20b7f5"
    property alias contentItem: content.data
    color: "#0d1722"
    radius: 10
    border.width: 1
    border.color: "#263847"

    Rectangle {
        anchors.fill: parent
        anchors.margins: 1
        radius: parent.radius - 1
        color: "transparent"
        border.width: 1
        border.color: "#0a1119"
        opacity: 0.8
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 10
        RowLayout {
            Layout.fillWidth: true
            visible: root.title.length > 0
            spacing: 9
            Rectangle { width: 3; height: 17; radius: 2; color: root.accent }
            Text {
                text: root.title
                color: root.accent
                font.family: Qt.platform.os === "osx" ? "SF Pro Display" : "Segoe UI"
                font.pixelSize: 18
                font.weight: Font.DemiBold
            }
            Item { Layout.fillWidth: true }
        }
        Item {
            id: content
            Layout.fillWidth: true
            Layout.fillHeight: true
        }
    }
}
