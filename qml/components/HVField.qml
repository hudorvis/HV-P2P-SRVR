import QtQuick 2.15
import QtQuick.Controls 2.15

TextField {
    id: root
    property color accent: "#62d64d"
    // When bindModel is true, modelText is copied into the editor only while the
    // field is NOT focused. This is intentional: fast backend telemetry/config
    // notifications must never overwrite or cancel an operator's in-progress edit.
    property bool bindModel: false
    property string modelText: ""
    signal commit(string value)

    implicitHeight: 31
    selectByMouse: true
    color: readOnly ? "#c6cbca" : "#edf0ef"
    selectionColor: "#355c3b"
    selectedTextColor: "#ffffff"
    placeholderTextColor: "#70777a"
    font.family: "Helvetica Neue"
    font.pixelSize: 13
    leftPadding: 9
    rightPadding: 9

    background: Rectangle {
        radius: 4
        color: root.readOnly ? "#14191c" : "#151a1d"
        border.width: 1
        border.color: root.activeFocus ? root.accent : "#4e565a"
    }

    function syncFromModel() {
        if (bindModel && !activeFocus && text !== modelText)
            text = modelText
    }

    Component.onCompleted: syncFromModel()
    onModelTextChanged: syncFromModel()
    onActiveFocusChanged: {
        if (!activeFocus) {
            if (bindModel && !readOnly && text !== modelText)
                commit(text)
            syncFromModel()
        }
    }
    onAccepted: {
        if (!readOnly) commit(text)
        focus = false
    }
}
