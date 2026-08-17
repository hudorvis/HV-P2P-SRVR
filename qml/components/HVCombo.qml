pragma ComponentBehavior: Bound

import QtQuick 2.15
import QtQuick.Controls 2.15

ComboBox {
    id: root

    property color accent: "#62d64d"

    implicitHeight: 31
    font.family: "Helvetica Neue"
    font.pixelSize: 13
    leftPadding: 9
    rightPadding: 26

    contentItem: Text {
        leftPadding: 0
        rightPadding: 0
        text: root.displayText
        font: root.font
        color: "#edf0ef"
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    indicator: Canvas {
        x: root.width - width - 9
        y: root.topPadding + (root.availableHeight - height) / 2
        width: 10
        height: 7
        contextType: "2d"

        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            ctx.strokeStyle = "#b9bfbd"
            ctx.lineWidth = 1.4
            ctx.beginPath()
            ctx.moveTo(1, 1)
            ctx.lineTo(width / 2, height - 1)
            ctx.lineTo(width - 1, 1)
            ctx.stroke()
        }
    }

    background: Rectangle {
        radius: 4
        color: "#151a1d"
        border.width: 1
        border.color: root.activeFocus ? root.accent : "#4e565a"
    }

    popup: Popup {
        y: root.height + 2
        width: root.width
        implicitHeight: contentItem.implicitHeight + 4
        padding: 2

        background: Rectangle {
            color: "#171d20"
            border.color: "#596064"
            border.width: 1
            radius: 4
        }

        contentItem: ListView {
            clip: true
            implicitHeight: Math.min(contentHeight, 180)
            model: root.popup.visible ? root.delegateModel : null
            currentIndex: root.highlightedIndex
            ScrollIndicator.vertical: ScrollIndicator { }
        }
    }

    delegate: ItemDelegate {
        id: delegateItem
        required property int index
        required property var modelData

        width: root.width - 4
        height: 30
        highlighted: root.highlightedIndex === delegateItem.index

        contentItem: Text {
            text: String(delegateItem.modelData)
            color: "#eef0ef"
            font.family: "Helvetica Neue"
            font.pixelSize: 13
            verticalAlignment: Text.AlignVCenter
            leftPadding: 6
        }

        background: Rectangle {
            color: delegateItem.highlighted ? "#26402b" : "#171d20"
        }
    }
}
