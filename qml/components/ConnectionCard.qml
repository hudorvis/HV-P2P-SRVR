import QtQuick 2.15
import QtQuick.Layouts 1.15
Rectangle {
    id: root
    property string title: "CTRL"
    property string line1: "Connected"
    property string line2: "172.20.1.101"
    property bool active: false
    property string extra: ""
    color: "#171c20"; border.color: "#4a5054"; border.width: 1; radius: 5
    RowLayout {
        anchors.fill: parent; anchors.margins: 13; spacing: 12
        StatusDot { active: root.active; Layout.alignment: Qt.AlignTop; Layout.topMargin: 5 }
        ColumnLayout {
            spacing: 2; Layout.fillWidth: true
            Text { text: root.title; color: "#f0f2f1"; font.family: "Helvetica Neue"; font.pixelSize: 17 }
            RowLayout { spacing: 12
                Text { text: root.line1; color: "#d8dcda"; font.family: "Helvetica Neue"; font.pixelSize: 12 }
                Text { text: root.line2; color: "#d8dcda"; font.family: "Helvetica Neue"; font.pixelSize: 12 }
                Text { visible: root.extra.length>0; text: root.extra; color: "#d8dcda"; font.family: "Helvetica Neue"; font.pixelSize: 12 }
            }
        }
    }
}
