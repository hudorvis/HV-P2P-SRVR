import QtQuick 2.15
import QtQuick.Controls 2.15
import "../components"

Item {
    id: root
    property real scaleFactor: 1.0
    property color fg: "#f0f2f1"
    property color muted: "#aeb4b1"
    property color cyan: "#26d5ff"
    property color green: "#63d84e"
    property color amber: "#ffc400"
    property color red: "#ff5050"
    property string logView: "Live"
    property string severity: "All"
    property string searchText: ""
    property bool autoScroll: true
    function f(v) { return Math.max(1, v * scaleFactor) }
    function levelColor(level) {
        if (level === "FAULT") return root.red
        if (level === "WARN") return root.amber
        return root.cyan
    }
    function levelFill(level) {
        if (level === "FAULT") return "#331719"
        if (level === "WARN") return "#302817"
        return "#142b31"
    }

    Column {
        anchors.fill:parent; spacing:root.f(10)
        Item {
            width:parent.width;height:root.f(112)
            Row {
                anchors.fill:parent;spacing:root.f(10)
                Panel {
                    width:(parent.width-root.f(30))*0.255;height:parent.height
                    Column{anchors.fill:parent;anchors.margins:root.f(16);spacing:root.f(12)
                        Text{text:"▤  LOG VIEW";color:root.cyan;font.pixelSize:root.f(16);font.weight:Font.Medium}
                        Row{width:parent.width;height:root.f(45);spacing:root.f(2);Repeater{model:["Live","Network","Safety","Free-D"];HVTab{width:(parent.width-root.f(6))/4;height:parent.height;text:modelData;selected:root.logView===modelData;accent:root.cyan;onClicked:root.logView=modelData}}}
                    }
                }
                Panel {
                    width:(parent.width-root.f(30))*0.265;height:parent.height
                    Column{anchors.fill:parent;anchors.margins:root.f(16);spacing:root.f(12)
                        Text{text:"♢  SEVERITY";color:root.cyan;font.pixelSize:root.f(16);font.weight:Font.Medium}
                        Row{width:parent.width;height:root.f(45);spacing:root.f(2);Repeater{model:["All","Info","Warning","Fault"];HVTab{width:(parent.width-root.f(6))/4;height:parent.height;text:(modelData==="Info"?"●  ":modelData==="Warning"?"△  ":modelData==="Fault"?"◇  ":"")+modelData;selected:root.severity===modelData;accent:root.cyan;onClicked:root.severity=modelData}}}
                    }
                }
                Panel {
                    width:(parent.width-root.f(30))*0.235;height:parent.height
                    Column{anchors.fill:parent;anchors.margins:root.f(16);spacing:root.f(12)
                        Text{text:"⌕  SEARCH";color:root.cyan;font.pixelSize:root.f(16);font.weight:Font.Medium}
                        TextField{id:searchBox;width:parent.width;height:root.f(45);placeholderText:"⌕  Search log messages...";color:root.fg;placeholderTextColor:"#949b9d";font.family:"Helvetica Neue";font.pixelSize:root.f(13);leftPadding:root.f(14);rightPadding:root.f(42);onTextChanged:root.searchText=text;background:Rectangle{radius:root.f(4);color:"#111619";border.width:1;border.color:searchBox.activeFocus?root.cyan:"#4e565a"}Text{anchors.right:parent.right;anchors.rightMargin:root.f(12);anchors.verticalCenter:parent.verticalCenter;text:"⌘ K";color:"#9da3a5";font.pixelSize:root.f(11)}}
                    }
                }
                Panel {
                    width:(parent.width-root.f(30))*0.245;height:parent.height
                    Column{anchors.fill:parent;anchors.margins:root.f(16);spacing:root.f(12)
                        Text{text:"ϟ  ACTIONS";color:root.cyan;font.pixelSize:root.f(16);font.weight:Font.Medium}
                        Row{width:parent.width;height:root.f(45);spacing:root.f(18)
                            HVButton{width:(parent.width-root.f(18))/2;height:parent.height;text:"⇩  Save Log";onClicked:backend.saveLog()}
                            Button{id:clearButton;width:(parent.width-root.f(18))/2;height:parent.height;text:"▥  Clear Log";hoverEnabled:true;font.family:"Helvetica Neue";font.pixelSize:root.f(13);contentItem:Text{text:clearButton.text;color:root.red;font:clearButton.font;horizontalAlignment:Text.AlignHCenter;verticalAlignment:Text.AlignVCenter}background:Rectangle{radius:root.f(4);color:clearButton.hovered?"#25191a":"#171c20";border.width:1;border.color:"#4e565a"}onClicked:backend.clearLog()}
                        }
                    }
                }
            }
        }

        Item {
            width:parent.width;height:parent.height-root.f(122)
            Row {
                anchors.fill:parent;spacing:root.f(10)
                Panel {
                    width:(parent.width-root.f(10))*0.755;height:parent.height
                    Column {
                        anchors.fill:parent;anchors.margins:root.f(14);spacing:0
                        Item {
                            width:parent.width;height:root.f(38)
                            Text{anchors.left:parent.left;anchors.verticalCenter:parent.verticalCenter;text:"〽  LIVE LOG";color:root.cyan;font.pixelSize:root.f(16);font.weight:Font.Medium}
                            Row{anchors.right:parent.right;anchors.verticalCenter:parent.verticalCenter;spacing:root.f(18)
                                Row{height:root.f(25);spacing:root.f(7);StatusDot{width:root.f(10);height:root.f(10);radius:root.f(5);anchors.verticalCenter:parent.verticalCenter;active:true}Text{anchors.verticalCenter:parent.verticalCenter;text:"Streaming";color:root.fg;font.pixelSize:root.f(12)}}
                                Rectangle{width:1;height:root.f(24);color:"#3c4346"}
                                Text{text:String(backend.logCount)+" lines";color:root.fg;font.pixelSize:root.f(12);anchors.verticalCenter:parent.verticalCenter}
                                Rectangle{width:1;height:root.f(24);color:"#3c4346"}
                                Text{text:"Auto-scroll";color:root.fg;font.pixelSize:root.f(12);anchors.verticalCenter:parent.verticalCenter}
                                Rectangle{id:autoToggle;width:root.f(36);height:root.f(19);radius:height/2;color:root.autoScroll?"#29aee8":"#4e565a";anchors.verticalCenter:parent.verticalCenter;Rectangle{width:root.f(15);height:root.f(15);radius:height/2;y:root.f(2);x:root.autoScroll?parent.width-width-root.f(2):root.f(2);color:"#f2f4f3"}MouseArea{anchors.fill:parent;cursorShape:Qt.PointingHandCursor;onClicked:root.autoScroll=!root.autoScroll}}
                            }
                        }
                        Rectangle{width:parent.width;height:1;color:"#3b4246"}
                        Rectangle {
                            width:parent.width;height:root.f(34);color:"#151b1f"
                            Row{anchors.fill:parent;anchors.leftMargin:root.f(6);anchors.rightMargin:root.f(6)
                                Text{width:parent.width*0.205;anchors.verticalCenter:parent.verticalCenter;text:"TIME (LOCAL)";color:root.fg;font.pixelSize:root.f(11);font.bold:true}
                                Text{width:parent.width*0.09;anchors.verticalCenter:parent.verticalCenter;text:"LEVEL";color:root.fg;font.pixelSize:root.f(11);font.bold:true}
                                Text{width:parent.width*0.105;anchors.verticalCenter:parent.verticalCenter;text:"SOURCE";color:root.fg;font.pixelSize:root.f(11);font.bold:true}
                                Text{width:parent.width*0.60;anchors.verticalCenter:parent.verticalCenter;text:"MESSAGE";color:root.fg;font.pixelSize:root.f(11);font.bold:true}
                            }
                        }
                        ListView {
                            id:logList;width:parent.width;height:parent.height-root.f(73);clip:true
                            property int revision:backend.logRevision
                            model:{ var r=revision; return backend.filteredLogEntries(root.logView,root.severity,root.searchText) }
                            onCountChanged:if(root.autoScroll) positionViewAtEnd()
                            ScrollBar.vertical:ScrollBar{}
                            delegate:Rectangle {
                                width:logList.width;height:root.f(27);color:index%2===0?"#0c1114":"#0e1417"
                                Row{anchors.fill:parent;anchors.leftMargin:root.f(6);anchors.rightMargin:root.f(6)
                                    Text{width:parent.width*0.205;anchors.verticalCenter:parent.verticalCenter;text:modelData.time;color:root.fg;font.family:"Menlo";font.pixelSize:root.f(10)}
                                    Item{width:parent.width*0.09;height:parent.height;Rectangle{anchors.verticalCenter:parent.verticalCenter;anchors.left:parent.left;width:root.f(48);height:root.f(19);radius:root.f(7);color:root.levelFill(modelData.level);border.color:root.levelColor(modelData.level);border.width:1;Text{anchors.centerIn:parent;text:modelData.level;color:root.levelColor(modelData.level);font.pixelSize:root.f(9);font.bold:true}}}
                                    Text{width:parent.width*0.105;anchors.verticalCenter:parent.verticalCenter;text:modelData.source;color:modelData.source==="SYSTEM"?root.cyan:modelData.source==="FREE-D"?root.cyan:modelData.source==="W1P"?root.cyan:root.fg;font.family:"Menlo";font.pixelSize:root.f(10);font.bold:true}
                                    Text{width:parent.width*0.60;anchors.verticalCenter:parent.verticalCenter;text:modelData.message;color:modelData.level==="FAULT"?root.red:modelData.level==="WARN"?root.amber:root.fg;font.family:"Menlo";font.pixelSize:root.f(10);elide:Text.ElideRight}
                                }
                            }
                        }
                    }
                }

                Panel {
                    width:(parent.width-root.f(10))*0.245;height:parent.height
                    Column {
                        anchors.fill:parent;anchors.margins:root.f(14);spacing:0
                        Text{height:root.f(38);verticalAlignment:Text.AlignVCenter;text:"▣  SYSTEM SUMMARY";color:root.cyan;font.pixelSize:root.f(16);font.weight:Font.Medium}
                        Rectangle {
                            width:parent.width;height:parent.height-root.f(38);radius:root.f(4);color:"#151b1f";border.color:"#3b4246";border.width:1
                            Column{anchors.fill:parent;anchors.margins:root.f(12);spacing:0
                                Item{width:parent.width;height:root.f(48);Text{anchors.left:parent.left;anchors.verticalCenter:parent.verticalCenter;text:"Backend State";color:root.fg;font.pixelSize:root.f(12)}Rectangle{anchors.right:parent.right;anchors.verticalCenter:parent.verticalCenter;width:root.f(112);height:root.f(28);radius:root.f(4);color:backend.systemReady?"#14341a":"#3a1619";border.color:backend.systemReady?root.green:root.red;Text{anchors.centerIn:parent;text:backend.systemReady?"OPERATIONAL":"FAULT";color:backend.systemReady?root.green:root.red;font.pixelSize:root.f(11);font.bold:true}}}
                                Rectangle{width:parent.width;height:1;color:"#343b3e"}
                                Item{width:parent.width;height:root.f(50);Text{anchors.left:parent.left;anchors.verticalCenter:parent.verticalCenter;text:"CTRL";color:root.fg;font.pixelSize:root.f(12)}Row{anchors.right:parent.right;anchors.verticalCenter:parent.verticalCenter;spacing:root.f(9);StatusDot{width:root.f(11);height:root.f(11);radius:root.f(6);anchors.verticalCenter:parent.verticalCenter;active:backend.ctrlConnected}Text{text:backend.ctrlConnected?"Connected":"Disconnected";color:root.fg;font.pixelSize:root.f(12)}}}
                                Rectangle{width:parent.width;height:1;color:"#343b3e"}
                                Item{width:parent.width;height:root.f(50);Text{anchors.left:parent.left;anchors.verticalCenter:parent.verticalCenter;text:"W1P";color:root.fg;font.pixelSize:root.f(12)}Row{anchors.right:parent.right;anchors.verticalCenter:parent.verticalCenter;spacing:root.f(9);StatusDot{width:root.f(11);height:root.f(11);radius:root.f(6);anchors.verticalCenter:parent.verticalCenter;active:backend.w1pConnected}Text{text:backend.w1pConnected?"Connected":"Disconnected";color:root.fg;font.pixelSize:root.f(12)}}}
                                Rectangle{width:parent.width;height:1;color:"#343b3e"}
                                Item{width:parent.width;height:root.f(50);Text{anchors.left:parent.left;anchors.verticalCenter:parent.verticalCenter;text:"Free-D";color:root.fg;font.pixelSize:root.f(12)}Row{anchors.right:parent.right;anchors.verticalCenter:parent.verticalCenter;spacing:root.f(9);StatusDot{width:root.f(11);height:root.f(11);radius:root.f(6);anchors.verticalCenter:parent.verticalCenter;active:backend.freeDActive}Text{text:backend.freeDActive?"Connected":"Disconnected";color:root.fg;font.pixelSize:root.f(12)}}}
                                Rectangle{width:parent.width;height:1;color:"#343b3e"}
                                Item{width:parent.width;height:root.f(50);Text{anchors.left:parent.left;anchors.verticalCenter:parent.verticalCenter;text:"System Uptime";color:root.fg;font.pixelSize:root.f(12)}Text{anchors.right:parent.right;anchors.verticalCenter:parent.verticalCenter;text:backend.uptime;color:root.fg;font.family:"Menlo";font.pixelSize:root.f(12)}}
                            }
                        }
                    }
                }
            }
        }
    }
}
