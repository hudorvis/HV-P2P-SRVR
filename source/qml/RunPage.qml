import QtQuick
import QtQuick.Layouts
import "components"

Item {
    id: root
    property var snapshot: ({})
    property var bridge
    property var runData: (snapshot && snapshot.run) ? snapshot.run : ({})
    function n(v,d) { var x=Number(v); return isNaN(x)?d:x }
    function f(v,dec) { return n(v,0).toFixed(dec===undefined?2:dec) }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        CableView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredHeight: 230
            snapshot: root.snapshot
            sideView: false
        }
        CableView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredHeight: 230
            snapshot: root.snapshot
            sideView: true
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 205
            spacing: 10

            HvCard {
                Layout.fillHeight: true
                Layout.fillWidth: true
                Layout.preferredWidth: 320
                title: "◉  DRIVE"
                accent: "#54db51"
                contentItem: ColumnLayout {
                    anchors.fill: parent
                    spacing: 8
                    Repeater {
                        model: [
                            {label:"Drive Mode", value:String(root.runData.driveMode || "Mode 1"), color:"#60df59", action:"mode"},
                            {label:"Acceleration Mode", value:String(root.runData.accelMode || "Speed"), color:"#60df59", action:"accel"},
                            {label:"Battery Change Mode", value:root.runData.batteryChange ? "On" : "Off", color:"#60df59", action:"battery"}
                        ]
                        delegate: Rectangle {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            radius: 7
                            color: rowMouse.containsMouse ? "#132431" : "#0b141d"
                            border.width: 1
                            border.color: "#263744"
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 11; anchors.rightMargin: 11
                                Text { text: modelData.label; color: "#dbe3e9"; font.pixelSize: 14; font.family: Qt.platform.os === "osx" ? "SF Pro Text" : "Segoe UI" }
                                Item { Layout.fillWidth: true }
                                Text { text: modelData.value; color: modelData.color; font.pixelSize: 15; font.weight: Font.DemiBold; font.family: Qt.platform.os === "osx" ? "SF Pro Text" : "Segoe UI" }
                            }
                            MouseArea {
                                id: rowMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (modelData.action === "mode") root.bridge.setDriveMode(root.n(root.runData.driveModeIndex,0) === 0 ? 1 : 0)
                                    else if (modelData.action === "accel") root.bridge.toggleAccelMode()
                                    else root.bridge.setBatteryChange(!root.runData.batteryChange)
                                }
                            }
                        }
                    }
                }
            }

            HvCard {
                Layout.fillHeight: true
                Layout.fillWidth: true
                Layout.preferredWidth: 320
                title: "◔  SPEED"
                accent: "#27c4ff"
                contentItem: RowLayout {
                    anchors.fill: parent
                    spacing: 0
                    Item {
                        Layout.fillWidth: true; Layout.fillHeight: true
                        Column {
                            anchors.centerIn: parent; spacing: 8
                            Text { anchors.horizontalCenter: parent.horizontalCenter; text: "CURRENT SPEED"; color: "#9aa8b4"; font.pixelSize: 12; font.family: Qt.platform.os === "osx" ? "SF Pro Text" : "Segoe UI" }
                            Row { anchors.horizontalCenter: parent.horizontalCenter; spacing: 7
                                Text { text: root.f(root.runData.speed,1); color: "#f1f5f8"; font.pixelSize: 36; font.weight: Font.Light; font.family: Qt.platform.os === "osx" ? "SF Pro Display" : "Segoe UI" }
                                Text { anchors.baseline: parent.children[0].baseline; text: "m/s"; color: "#c3ccd4"; font.pixelSize: 15 }
                            }
                            Text { anchors.horizontalCenter: parent.horizontalCenter; text: root.f(root.n(root.runData.speed,0)*3.6,1) + " km/h"; color: "#25c2ff"; font.pixelSize: 15 }
                        }
                    }
                    Rectangle { Layout.fillHeight: true; width: 1; color: "#263744"; Layout.topMargin: 16; Layout.bottomMargin: 16 }
                    Item {
                        Layout.fillWidth: true; Layout.fillHeight: true
                        Column {
                            anchors.centerIn: parent; spacing: 8
                            Text { anchors.horizontalCenter: parent.horizontalCenter; text: "MAX SPEED"; color: "#9aa8b4"; font.pixelSize: 12 }
                            Row { anchors.horizontalCenter: parent.horizontalCenter; spacing: 7
                                Text { text: root.f(root.runData.maxSpeed,1); color: "#f1f5f8"; font.pixelSize: 36; font.weight: Font.Light; font.family: Qt.platform.os === "osx" ? "SF Pro Display" : "Segoe UI" }
                                Text { anchors.baseline: parent.children[0].baseline; text: "m/s"; color: "#c3ccd4"; font.pixelSize: 15 }
                            }
                            Text { anchors.horizontalCenter: parent.horizontalCenter; text: root.f(root.n(root.runData.maxSpeed,0)*3.6,1) + " km/h"; color: "#25c2ff"; font.pixelSize: 15 }
                        }
                    }
                }
            }

            HvCard {
                Layout.fillHeight: true
                Layout.fillWidth: true
                Layout.preferredWidth: 290
                title: "⌖  POSITION"
                accent: "#27c4ff"
                contentItem: ColumnLayout {
                    anchors.fill: parent
                    spacing: 4
                    Text { text: "CURRENT POSITION"; color: "#9aa8b4"; font.pixelSize: 12 }
                    Row { Layout.alignment: Qt.AlignHCenter; spacing: 7
                        Text { text: root.f(root.runData.position,2); color: "#f1f5f8"; font.pixelSize: 34; font.weight: Font.Light; font.family: Qt.platform.os === "osx" ? "SF Pro Display" : "Segoe UI" }
                        Text { anchors.baseline: parent.children[0].baseline; text: "m"; color: "#c3ccd4"; font.pixelSize: 15 }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: "#263744"; Layout.topMargin: 3; Layout.bottomMargin: 3 }
                    RowLayout {
                        Layout.fillWidth: true
                        Column { Layout.fillWidth: true; Text { text:"TO NEAR"; color:"#9aa8b4"; font.pixelSize:11 } Text { text:root.f(root.runData.toNear,2)+" m"; color:"#25c2ff"; font.pixelSize:19 } }
                        Rectangle { width:1; height:48; color:"#263744" }
                        Column { Layout.fillWidth: true; Text { text:"TO FAR"; color:"#9aa8b4"; font.pixelSize:11 } Text { text:root.f(root.runData.toFar,2)+" m"; color:"#25c2ff"; font.pixelSize:19 } }
                    }
                }
            }

            HvCard {
                Layout.fillHeight: true
                Layout.fillWidth: true
                Layout.preferredWidth: 390
                title: "ϟ  QUICK ACTIONS"
                accent: "#ffbd16"
                contentItem: ColumnLayout {
                    anchors.fill: parent
                    spacing: 8
                    GridLayout {
                        Layout.fillWidth: true
                        columns: 6
                        columnSpacing: 7; rowSpacing: 7
                        Repeater {
                            model: 6
                            HvButton {
                                Layout.fillWidth: true
                                implicitHeight: 38
                                text: {
                                    var ps=root.runData.presets || []
                                    return index<ps.length ? String(ps[index].name || ("P"+(index+1))) : ("P"+(index+1))
                                }
                                confirmRequired: true
                                onTriggered: root.bridge.gotoPreset(index)
                            }
                        }
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        columns: 5
                        columnSpacing: 7; rowSpacing: 7
                        HvButton { Layout.fillWidth: true; text:"REF"; accent:"#20b7f5"; selected:true; confirmRequired:true; onTriggered: root.bridge.gotoLimit("ref") }
                        HvButton { Layout.fillWidth: true; text:"NEAR"; accent:"#20b7f5"; selected:true; confirmRequired:true; onTriggered: root.bridge.gotoLimit("near") }
                        HvButton { Layout.fillWidth: true; text:"FAR"; accent:"#20b7f5"; selected:true; confirmRequired:true; onTriggered: root.bridge.gotoLimit("far") }
                        Repeater {
                            model: 2
                            HvButton {
                                Layout.fillWidth: true
                                text: {
                                    var a=root.runData.auxLabels || []
                                    return index<a.length ? String(a[index]||("AUX"+(index+1))) : ("AUX"+(index+1))
                                }
                                confirmRequired: true
                                onTriggered: root.bridge.runAux(index)
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 7
                        Repeater {
                            model: 2
                            HvButton {
                                Layout.preferredWidth: 82
                                text: {
                                    var a=root.runData.auxLabels || []
                                    var i=index+2
                                    return i<a.length ? String(a[i]||("AUX"+(i+1))) : ("AUX"+(i+1))
                                }
                                confirmRequired: true
                                onTriggered: root.bridge.runAux(index+2)
                            }
                        }
                        Item { Layout.fillWidth:true }
                        HvButton { Layout.preferredWidth:110; text:"CANCEL"; danger:true; confirmRequired:false; onTriggered:root.bridge.cancelMotion() }
                    }
                }
            }
        }
    }
}
