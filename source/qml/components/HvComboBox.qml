import QtQuick
import QtQuick.Controls

ComboBox {
    id: root
    implicitHeight: 34
    leftPadding: 10
    rightPadding: 28
    font.family: Qt.platform.os === "osx" ? "SF Pro Text" : "Segoe UI"
    font.pixelSize: 13
    contentItem: Text {
        text: root.displayText
        color: "#e8eef3"
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        font: root.font
    }
    indicator: Canvas {
        x: root.width - width - 10
        y: (root.height-height)/2
        width: 10; height: 7
        onPaint: {
            var c=getContext("2d"); c.reset(); c.strokeStyle="#91a0ad"; c.lineWidth=1.5
            c.beginPath(); c.moveTo(1,1); c.lineTo(5,6); c.lineTo(9,1); c.stroke()
        }
    }
    background: Rectangle {
        color: root.hovered ? "#122431" : "#0a121a"
        radius: 6
        border.width: 1
        border.color: root.activeFocus ? "#20b7f5" : "#2b3c4a"
    }
    popup: Popup {
        y: root.height + 3
        width: root.width
        padding: 4
        background: Rectangle { color: "#101923"; radius: 7; border.width: 1; border.color: "#314452" }
        contentItem: ListView {
            clip: true
            implicitHeight: Math.min(contentHeight, 260)
            model: root.popup.visible ? root.delegateModel : null
            currentIndex: root.highlightedIndex
        }
    }
    delegate: ItemDelegate {
        leftPadding: 8
        rightPadding: 8
        width: root.width - 8
        height: 32
        contentItem: Text {
            text: modelData
            color: highlighted ? "white" : "#d4dde5"
            font: root.font
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle { color: highlighted ? "#153246" : "transparent"; radius: 5 }
        highlighted: root.highlightedIndex === index
    }
}
