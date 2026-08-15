import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ApplicationWindow {
    id: win
    visible: true
    width: 1600
    height: 920
    minimumWidth: 1180
    minimumHeight: 760
    color: "#060d14"
    title: "HV P2P SRVR v26.08.15.05"
    flags: Qt.Window | Qt.FramelessWindowHint
    property int pageIndex: 0
    property var s: backend.snapshot
    property var conn: (s && s.connections) ? s.connections : ({})
    property var safety: (s && s.safety) ? s.safety : ({level:"warning",text:"STARTING"})
    property color accent: "#27c4ff"
    property color readyGreen: "#58d861"
    property color warningAmber: "#dca72a"
    property color faultRed: "#e44f58"
    function safetyColor(){return safety.level==="fault"?faultRed:(safety.level==="ready"?readyGreen:warningAmber)}
    function safetyBg(){return safety.level==="fault"?"#261015":(safety.level==="ready"?"#071b13":"#211a08")}

    Rectangle {
        anchors.fill:parent
        color:"#07101a"
        border.width:1
        border.color:"#263846"
        radius:10
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 9

        // Window / product header
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 62
            RowLayout {
                anchors.fill: parent
                spacing: 13
                Row {
                    visible: Qt.platform.os === "osx"
                    spacing: 8
                    Layout.alignment: Qt.AlignVCenter
                    Repeater {
                        model:["#ff605c","#ffbd44","#00ca4e"]
                        Rectangle {
                            width:13;height:13;radius:7;color:modelData;border.width:1;border.color:"#27333b"
                            MouseArea{anchors.fill:parent;onClicked:{if(index===0)win.close();else if(index===1)win.showMinimized();else win.visibility=win.visibility===Window.Maximized?Window.Windowed:Window.Maximized}}
                        }
                    }
                }
                Canvas {
                    width:42;height:42
                    onPaint:{var c=getContext("2d");c.reset();c.strokeStyle="#e7edf2";c.lineWidth=1.6;c.beginPath();c.arc(21,21,18,0,Math.PI*2);c.stroke();c.strokeStyle="#aab6bf";c.beginPath();c.moveTo(10,25);c.lineTo(18,18);c.lineTo(26,18);c.lineTo(32,13);c.stroke()}
                }
                Text {
                    text:"HV P2P  |  SRVR"
                    color:"#f1f5f8"
                    font.family:Qt.platform.os === "osx"?"SF Pro Display":"Segoe UI"
                    font.pixelSize:28
                    font.weight:Font.Medium
                    font.letterSpacing:0.5
                }
                Item{Layout.fillWidth:true}
                Text {
                    text:String((s&&s.version)||"v26.08.15.05")
                    color:"#8c9aa7"
                    font.pixelSize:14
                    Layout.alignment:Qt.AlignVCenter
                }
                Row {
                    visible:Qt.platform.os !== "osx"
                    spacing:2
                    Repeater {
                        model:["−","□","×"]
                        Rectangle {
                            width:42;height:34;color:mouse.containsMouse?(index===2?"#9e2830":"#14222d"):"transparent";radius:4
                            Text{anchors.centerIn:parent;text:modelData;color:"#cbd4dc";font.pixelSize:index===2?22:17}
                            MouseArea{id:mouse;anchors.fill:parent;hoverEnabled:true;onClicked:{if(index===0)win.showMinimized();else if(index===1)win.visibility=win.visibility===Window.Maximized?Window.Windowed:Window.Maximized;else win.close()}}
                        }
                    }
                }
            }
            MouseArea {
                anchors.fill:parent
                z:-1
                onPressed:win.startSystemMove()
                onDoubleClicked:win.visibility=win.visibility===Window.Maximized?Window.Windowed:Window.Maximized
            }
        }

        // Only the requested three top-level connection statuses.
        RowLayout {
            Layout.fillWidth:true
            Layout.preferredHeight:46
            spacing:10
            ConnectionCard{Layout.fillWidth:true;label:"CTRL";connected:!!conn.ctrl}
            ConnectionCard{Layout.fillWidth:true;label:"W1P";connected:!!conn.w1p}
            ConnectionCard{Layout.fillWidth:true;label:"Free-D";connected:!!conn.freeD}
        }

        Rectangle {
            Layout.fillWidth:true
            Layout.preferredHeight:56
            radius:7
            color:win.safetyBg()
            border.width:1
            border.color:win.safetyColor()
            Row {
                anchors.centerIn:parent
                spacing:14
                Text{text:safety.level==="fault"?"!":"◇";color:win.safetyColor();font.pixelSize:30;font.weight:Font.Bold}
                Text {
                    text:String(safety.text||"SYSTEM READY")
                    color:win.safetyColor()
                    font.family:Qt.platform.os === "osx"?"SF Pro Display":"Segoe UI"
                    font.pixelSize:28
                    font.weight:Font.DemiBold
                    font.letterSpacing:1.2
                }
            }
            MouseArea {
                anchors.fill:parent
                cursorShape:Qt.PointingHandCursor
                onClicked:backend.toggleEstop()
            }
        }

        RowLayout {
            Layout.fillWidth:true
            Layout.preferredHeight:48
            spacing:0
            NavTab{Layout.fillWidth:true;label:"Run";glyph:"▷";selected:win.pageIndex===0;onTriggered:win.pageIndex=0}
            NavTab{Layout.fillWidth:true;label:"Setup";glyph:"⚙";selected:win.pageIndex===1;onTriggered:win.pageIndex=1}
            NavTab{Layout.fillWidth:true;label:"Free-D";glyph:"⌘";selected:win.pageIndex===2;onTriggered:win.pageIndex=2}
            NavTab{Layout.fillWidth:true;label:"Log";glyph:"▤";selected:win.pageIndex===3;onTriggered:win.pageIndex=3}
        }

        StackLayout {
            Layout.fillWidth:true
            Layout.fillHeight:true
            currentIndex:win.pageIndex
            RunPage{snapshot:win.s;bridge:backend}
            SetupPage{snapshot:win.s;bridge:backend}
            FreeDPage{snapshot:win.s;bridge:backend}
            LogPage{snapshot:win.s;bridge:backend}
        }
    }

    Rectangle {
        visible:backend.backendError.length>0
        anchors.left:parent.left;anchors.right:parent.right;anchors.bottom:parent.bottom
        height:46;color:"#54191d";border.width:1;border.color:"#e85b63";z:1000
        Text{anchors.centerIn:parent;text:"SRVR backend: "+backend.backendError;color:"#ffd4d6";font.pixelSize:13}
    }
}
