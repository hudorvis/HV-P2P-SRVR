import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../components"

Item {
    id: root
    property real scaleFactor: 1.0
    property color fg: "#f0f2f1"
    property color muted: "#aeb4b1"
    property color cyan: "#58d5f5"
    property color green: "#63d84e"
    property color line: "#3b4246"
    function f(v) { return Math.max(1, v * scaleFactor) }
    function idx(list, value) {
        for (var i=0; i<list.length; ++i) if (String(list[i]) === String(value)) return i
        return 0
    }

    property var auxChoices: [
        "None", "Drive Mode", "Acceleration Mode", "Battery Change Mode",
        "Near Limit Save", "Near Limit Recall", "Near Limit Slip",
        "Far Limit Save", "Far Limit Recall", "Far Limit Slip",
        "Ref Point Save", "Ref Point Recall", "Ref Point Slip",
        "Preset 1 Recall", "Preset 2 Recall", "Preset 3 Recall", "Preset 4 Recall", "Preset 5 Recall",
        "Preset 6 Recall", "Preset 7 Recall", "Preset 8 Recall", "Preset 9 Recall", "Preset 10 Recall",
        "Preset 1 Slip", "Preset 2 Slip", "Preset 3 Slip", "Preset 4 Slip", "Preset 5 Slip",
        "Preset 6 Slip", "Preset 7 Slip", "Preset 8 Slip", "Preset 9 Slip", "Preset 10 Slip"
    ]

    Column {
        anchors.fill: parent
        spacing: root.f(8)

        Item {
            width: parent.width
            height: (parent.height-root.f(8))*0.61
            Row {
                anchors.fill: parent
                spacing: root.f(8)
                property real gap: root.f(24)
                property real usable: width-gap

                // CTRL
                Panel {
                    width: parent.usable*0.205
                    height: parent.height
                    Column {
                        anchors.fill: parent; anchors.margins: root.f(17); spacing: root.f(8)
                        Text { text:"⌘  CTRL"; color:root.cyan; font.pixelSize:root.f(17); font.weight:Font.Medium }
                        Row { width:parent.width; height:root.f(31); Text{width:root.f(145);anchors.verticalCenter:parent.verticalCenter;text:"CTRL IP";color:root.fg;font.pixelSize:root.f(12)} HVField{width:parent.width-root.f(145);height:parent.height;bindModel:true;modelText:backend.ctrlIp;horizontalAlignment:TextInput.AlignHCenter;onCommit:function(v){backend.setNetwork("CTRL",v)}} }
                        Row { width:parent.width; height:root.f(25); Text{width:root.f(145);anchors.verticalCenter:parent.verticalCenter;text:"CTRL-TS Link";color:root.fg;font.pixelSize:root.f(12)} StatusDot{width:root.f(11);height:root.f(11);radius:root.f(6);anchors.verticalCenter:parent.verticalCenter;active:backend.ctrlTsConnected} Text{anchors.verticalCenter:parent.verticalCenter;leftPadding:root.f(8);text:backend.ctrlTsConnected?"Connected":"Disconnected";color:root.fg;font.pixelSize:root.f(12)} }
                        Row { width:parent.width; height:root.f(25); Text{width:root.f(145);anchors.verticalCenter:parent.verticalCenter;text:"ADS1115 Link";color:root.fg;font.pixelSize:root.f(12)} StatusDot{width:root.f(11);height:root.f(11);radius:root.f(6);anchors.verticalCenter:parent.verticalCenter;active:backend.ads1115Connected} Text{anchors.verticalCenter:parent.verticalCenter;leftPadding:root.f(8);text:backend.ads1115Connected?"Connected":"Fault";color:root.fg;font.pixelSize:root.f(12)} }
                        Row { width:parent.width; height:root.f(31); Text{width:root.f(145);anchors.verticalCenter:parent.verticalCenter;text:"Direction";color:root.fg;font.pixelSize:root.f(12)} HVCombo{width:parent.width-root.f(145);height:parent.height;model:["Normal","Inverted"];currentIndex:backend.ctrlInverted?1:0;onActivated:function(){backend.setDirection("CTRL",currentIndex===1)}} }
                        Rectangle { width:parent.width; height:1; color:root.line }
                        Text { text:"JOYSTICK CALIBRATION"; color:root.cyan; font.pixelSize:root.f(12) }
                        Item {
                            width:parent.width; height:root.f(38)
                            Text { anchors.left:parent.left; anchors.verticalCenter:parent.verticalCenter; text:"LEFT"; color:root.fg; font.pixelSize:root.f(11) }
                            Text { anchors.right:parent.right; anchors.verticalCenter:parent.verticalCenter; text:"RIGHT"; color:root.fg; font.pixelSize:root.f(11) }
                            Rectangle { id:joyTrack; anchors.horizontalCenter:parent.horizontalCenter; anchors.verticalCenter:parent.verticalCenter; width:parent.width-root.f(105); height:1; color:"#697074" }
                            Rectangle { anchors.verticalCenter:parent.verticalCenter; x:joyTrack.x + (joyTrack.width-width)*Math.max(0,Math.min(1,(backend.joystickValue+1)/2)); width:root.f(13); height:root.f(13); radius:root.f(7); color:"#3ab7ec"; border.color:"#50646c"; border.width:root.f(5) }
                        }
                        Row { width:parent.width;height:root.f(25);Text{width:parent.width-root.f(60);anchors.verticalCenter:parent.verticalCenter;text:"Current Value";color:root.fg;font.pixelSize:root.f(11)}Text{width:root.f(60);anchors.verticalCenter:parent.verticalCenter;text:Number(backend.joystickValue).toFixed(2);horizontalAlignment:Text.AlignHCenter;color:root.fg;font.pixelSize:root.f(12)} }
                        Row {
                            width:parent.width; height:root.f(31); spacing:root.f(4)
                            Text{width:root.f(100);anchors.verticalCenter:parent.verticalCenter;text:"Deadband";color:root.fg;font.pixelSize:root.f(11)}
                            HVButton{width:root.f(35);height:parent.height;text:"−";onClicked:backend.setJoystickDeadband(Math.max(0,backend.joystickDeadband-0.5))}
                            HVField{width:parent.width-root.f(100+35+35+12);height:parent.height;bindModel:true;modelText:Number(backend.joystickDeadband).toFixed(1)+" %";horizontalAlignment:TextInput.AlignHCenter;onCommit:function(v){var n=parseFloat(v);if(!isNaN(n))backend.setJoystickDeadband(n)}}
                            HVButton{width:root.f(35);height:parent.height;text:"+";onClicked:backend.setJoystickDeadband(Math.min(25,backend.joystickDeadband+0.5))}
                        }
                    }
                }

                // W1P
                Panel {
                    width: parent.usable*0.175
                    height: parent.height
                    Column {
                        anchors.fill: parent; anchors.margins: root.f(17); spacing: root.f(9)
                        Text { text:"♨  W1P"; color:root.cyan; font.pixelSize:root.f(17); font.weight:Font.Medium }
                        Row { width:parent.width; height:root.f(31); Text{width:root.f(108);anchors.verticalCenter:parent.verticalCenter;text:"W1P IP";color:root.fg;font.pixelSize:root.f(12)} HVField{width:parent.width-root.f(108);height:parent.height;bindModel:true;modelText:backend.w1pIp;horizontalAlignment:TextInput.AlignHCenter;onCommit:function(v){backend.setNetwork("W1P",v)}} }
                        Row { width:parent.width; height:root.f(25); Text{width:root.f(108);anchors.verticalCenter:parent.verticalCenter;text:"W1P-TS Link";color:root.fg;font.pixelSize:root.f(12)} StatusDot{width:root.f(11);height:root.f(11);radius:root.f(6);anchors.verticalCenter:parent.verticalCenter;active:backend.w1pTsConnected} Text{anchors.verticalCenter:parent.verticalCenter;leftPadding:root.f(8);text:backend.w1pTsConnected?"Connected":"Disconnected";color:root.fg;font.pixelSize:root.f(12)} }
                        Row { width:parent.width; height:root.f(25); Text{width:root.f(108);anchors.verticalCenter:parent.verticalCenter;text:"RS485 Link";color:root.fg;font.pixelSize:root.f(12)} StatusDot{width:root.f(11);height:root.f(11);radius:root.f(6);anchors.verticalCenter:parent.verticalCenter;active:backend.rs485Connected} Text{anchors.verticalCenter:parent.verticalCenter;leftPadding:root.f(8);text:backend.rs485Connected?"Connected":"Disconnected";color:root.fg;font.pixelSize:root.f(12)} }
                        Row { width:parent.width; height:root.f(31); Text{width:root.f(108);anchors.verticalCenter:parent.verticalCenter;text:"Direction";color:root.fg;font.pixelSize:root.f(12)} HVCombo{width:parent.width-root.f(108);height:parent.height;model:["Normal","Inverted"];currentIndex:backend.w1pInverted?1:0;onActivated:function(){backend.setDirection("W1P",currentIndex===1)}} }
                        Rectangle { width:parent.width; height:1; color:root.line }
                        Row { width:parent.width; height:root.f(31); Text{width:root.f(108);anchors.verticalCenter:parent.verticalCenter;text:"CMD Units Per M";color:root.fg;font.pixelSize:root.f(11)} HVField{width:parent.width-root.f(152);height:parent.height;bindModel:true;modelText:Number(backend.unitsPerM).toFixed(2);horizontalAlignment:TextInput.AlignHCenter;onCommit:function(v){var n=parseFloat(v);if(!isNaN(n))backend.setUnitsPerM(n)}} Text{width:root.f(44);anchors.verticalCenter:parent.verticalCenter;text:"u/m";horizontalAlignment:Text.AlignHCenter;color:root.fg;font.pixelSize:root.f(11)} }
                        Row { width:parent.width; height:root.f(31); Text{width:root.f(108);anchors.verticalCenter:parent.verticalCenter;text:"Position Source";color:root.fg;font.pixelSize:root.f(11)} HVCombo{width:parent.width-root.f(108);height:parent.height;model:["Encoder"];currentIndex:0;onActivated:function(){backend.setPositionSource(currentText)}} }
                    }
                }

                // MOTION PROFILES
                Panel {
                    width: parent.usable*0.405
                    height: parent.height
                    Column {
                        anchors.fill: parent; anchors.margins: root.f(15); spacing: root.f(7)
                        Text { text:"〽  MOTION PROFILES"; color:root.cyan; font.pixelSize:root.f(17); font.weight:Font.Medium }
                        Row {
                            width:parent.width; height:root.f(246)
                            Item {
                                width:(parent.width-root.f(18))/2; height:parent.height
                                Column {
                                    anchors.fill:parent; spacing:root.f(4)
                                    Text { width:parent.width; text:"MODE 1"; horizontalAlignment:Text.AlignHCenter; color:root.cyan; font.pixelSize:root.f(11) }
                                    Row { width:parent.width;height:root.f(31);Text{width:root.f(118);anchors.verticalCenter:parent.verticalCenter;text:"Name";color:root.fg;font.pixelSize:root.f(11)}HVField{width:parent.width-root.f(118);height:parent.height;bindModel:true;modelText:backend.driveMode1Name;horizontalAlignment:TextInput.AlignHCenter;onCommit:function(v){backend.renameDriveMode(0,v)}} }
                                    Repeater {
                                        model:[
                                            {label:"Max Speed",key:"max_speed_mps",unit:"m/s"},
                                            {label:"Goto Speed",key:"goto_speed_mps",unit:"m/s"},
                                            {label:"Acceleration",key:"accel_mps2",unit:"m/s²"},
                                            {label:"Deceleration",key:"decel_mps2",unit:"m/s²"},
                                            {label:"Crossover",key:"crossover_mps2",unit:"m/s"},
                                            {label:"Stop Deceleration",key:"stop_decel_mps2",unit:"m/s²"}
                                        ]
                                        delegate:Row {
                                            width:parent.width;height:root.f(31)
                                            property var dm: backend.driveModes[0]
                                            Text{width:root.f(118);anchors.verticalCenter:parent.verticalCenter;text:modelData.label;color:root.fg;font.pixelSize:root.f(11)}
                                            HVField{width:parent.width-root.f(166);height:parent.height;bindModel:true;modelText:parent.dm?Number(parent.dm[modelData.key]).toFixed(1):"0.0";horizontalAlignment:TextInput.AlignHCenter;onCommit:function(v){var n=parseFloat(v);if(!isNaN(n))backend.setDriveModeValue(0,modelData.key,n)}}
                                            Text{width:root.f(48);anchors.verticalCenter:parent.verticalCenter;text:modelData.unit;horizontalAlignment:Text.AlignHCenter;color:root.fg;font.pixelSize:root.f(11)}
                                        }
                                    }
                                }
                            }
                            Rectangle { width:1;height:parent.height;color:root.line }
                            Item {
                                width:(parent.width-root.f(18))/2; height:parent.height
                                Column {
                                    anchors.fill:parent; anchors.leftMargin:root.f(17); spacing:root.f(4)
                                    Text { width:parent.width; text:"MODE 2"; horizontalAlignment:Text.AlignHCenter; color:root.cyan; font.pixelSize:root.f(11) }
                                    Row { width:parent.width;height:root.f(31);Text{width:root.f(118);anchors.verticalCenter:parent.verticalCenter;text:"Name";color:root.fg;font.pixelSize:root.f(11)}HVField{width:parent.width-root.f(118);height:parent.height;bindModel:true;modelText:backend.driveMode2Name;horizontalAlignment:TextInput.AlignHCenter;onCommit:function(v){backend.renameDriveMode(1,v)}} }
                                    Repeater {
                                        model:[
                                            {label:"Max Speed",key:"max_speed_mps",unit:"m/s"},
                                            {label:"Goto Speed",key:"goto_speed_mps",unit:"m/s"},
                                            {label:"Acceleration",key:"accel_mps2",unit:"m/s²"},
                                            {label:"Deceleration",key:"decel_mps2",unit:"m/s²"},
                                            {label:"Crossover",key:"crossover_mps2",unit:"m/s"},
                                            {label:"Stop Deceleration",key:"stop_decel_mps2",unit:"m/s²"}
                                        ]
                                        delegate:Row {
                                            width:parent.width;height:root.f(31)
                                            property var dm: backend.driveModes[1]
                                            Text{width:root.f(118);anchors.verticalCenter:parent.verticalCenter;text:modelData.label;color:root.fg;font.pixelSize:root.f(11)}
                                            HVField{width:parent.width-root.f(166);height:parent.height;bindModel:true;modelText:parent.dm?Number(parent.dm[modelData.key]).toFixed(1):"0.0";horizontalAlignment:TextInput.AlignHCenter;onCommit:function(v){var n=parseFloat(v);if(!isNaN(n))backend.setDriveModeValue(1,modelData.key,n)}}
                                            Text{width:root.f(48);anchors.verticalCenter:parent.verticalCenter;text:modelData.unit;horizontalAlignment:Text.AlignHCenter;color:root.fg;font.pixelSize:root.f(11)}
                                        }
                                    }
                                }
                            }
                        }
                        Rectangle { width:parent.width; height:1; color:root.line }
                        Text { text:"DRIVE BEHAVIOUR"; color:root.cyan; font.pixelSize:root.f(12) }
                        Row {
                            width:parent.width;height:root.f(31);spacing:root.f(28)
                            Row { width:(parent.width-root.f(28))/2;height:parent.height;Text{width:root.f(126);anchors.verticalCenter:parent.verticalCenter;text:"Acceleration Mode";color:root.fg;font.pixelSize:root.f(11)}HVCombo{width:parent.width-root.f(126);height:parent.height;model:["Power","Speed"];currentIndex:root.idx(model,backend.accelerationMode);onActivated:function(){backend.setAccelerationMode(currentText)}} }
                            Row { width:(parent.width-root.f(28))/2;height:parent.height;Text{width:root.f(126);anchors.verticalCenter:parent.verticalCenter;text:"Battery Change Mode";color:root.fg;font.pixelSize:root.f(11)}HVCombo{width:parent.width-root.f(126);height:parent.height;model:["Off","On"];currentIndex:backend.batteryChange?1:0;onActivated:function(){backend.setBatteryChange(currentIndex===1)}} }
                        }
                    }
                }

                // ACTIONS
                Panel {
                    width: parent.usable*0.215
                    height: parent.height
                    Column {
                        anchors.fill:parent; anchors.margins:root.f(18); spacing:root.f(58)
                        Text { text:"ϟ  ACTIONS"; color:root.fg; font.pixelSize:root.f(17); font.weight:Font.Medium }
                        HVButton { anchors.horizontalCenter:parent.horizontalCenter; width:parent.width-root.f(48); height:root.f(50); text:"⇩   SAVE CONFIG"; accent:root.cyan; onClicked:backend.saveConfig() }
                        HVButton { anchors.horizontalCenter:parent.horizontalCenter; width:parent.width-root.f(48); height:root.f(50); text:"⇧   LOAD CONFIG"; accent:root.cyan; onClicked:backend.loadConfig() }
                    }
                }
            }
        }

        Item {
            width:parent.width
            height:(parent.height-root.f(8))*0.39
            Row {
                anchors.fill:parent; spacing:root.f(8)
                property real gap:root.f(16)
                property real usable:width-gap

                Panel {
                    width:parent.usable*0.205;height:parent.height
                    Column {
                        anchors.fill:parent;anchors.margins:root.f(17);spacing:root.f(6)
                        Text{text:"♧  CTRL-TS AUX ASSIGN";color:root.cyan;font.pixelSize:root.f(16);font.weight:Font.Medium}
                        Repeater {
                            model:5
                            delegate:Row {
                                width:parent.width;height:root.f(31)
                                Text{width:root.f(62);anchors.verticalCenter:parent.verticalCenter;text:"AUX "+(index+1);color:root.fg;font.pixelSize:root.f(11)}
                                HVCombo{width:parent.width-root.f(62);height:parent.height;model:root.auxChoices;currentIndex:root.idx(model,backend.ctrlAuxAssignments[index]);onActivated:function(){backend.setAuxAssignment("CTRL",index,currentText)}}
                            }
                        }
                    }
                }

                Panel {
                    width:parent.usable*0.175;height:parent.height
                    Column {
                        anchors.fill:parent;anchors.margins:root.f(17);spacing:root.f(6)
                        Text{text:"♧  W1P-TS AUX ASSIGN";color:root.cyan;font.pixelSize:root.f(16);font.weight:Font.Medium}
                        Repeater {
                            model:5
                            delegate:Row {
                                width:parent.width;height:root.f(31)
                                Text{width:root.f(56);anchors.verticalCenter:parent.verticalCenter;text:"AUX "+(index+1);color:root.fg;font.pixelSize:root.f(11)}
                                HVCombo{width:parent.width-root.f(56);height:parent.height;model:root.auxChoices;currentIndex:root.idx(model,backend.w1pAuxAssignments[index]);onActivated:function(){backend.setAuxAssignment("W1P",index,currentText)}}
                            }
                        }
                    }
                }

                Panel {
                    width:parent.usable*0.62;height:parent.height
                    Row {
                        anchors.fill:parent;anchors.margins:root.f(17);spacing:root.f(16)
                        Column {
                            width:root.f(230);height:parent.height;spacing:root.f(12)
                            Text{text:"⌾  CALIBRATION";color:root.cyan;font.pixelSize:root.f(16);font.weight:Font.Medium}
                            HVButton{width:parent.width;height:root.f(42);text:"LIMIT CALIBRATION";accent:root.cyan;onClicked:backend.openLimitCalibration()}
                            HVButton{width:parent.width;height:root.f(42);text:"WINCH CALIBRATION";accent:root.cyan;onClicked:backend.openWinchCalibration()}
                            HVButton{width:parent.width;height:root.f(42);text:"JOYSTICK CALIBRATION";accent:root.cyan;onClicked:backend.openJoystickCalibration()}
                        }
                        Rectangle{width:1;height:parent.height-root.f(22);anchors.verticalCenter:parent.verticalCenter;color:root.line}
                        Repeater {
                            model:[{key:"near",title:"NEAR"},{key:"ref",title:"REFERENCE"},{key:"far",title:"FAR"}]
                            delegate:Item {
                                id:calPoint
                                width:(parent.width-root.f(230+18+32))/3;height:parent.height
                                property var summary:backend.calibrationSummary[modelData.key]
                                Column {
                                    anchors.fill:parent;spacing:root.f(13)
                                    Text{width:parent.width;text:modelData.title;horizontalAlignment:Text.AlignHCenter;color:root.cyan;font.pixelSize:root.f(11)}
                                    Row{width:parent.width;height:root.f(25);Text{width:root.f(82);anchors.verticalCenter:parent.verticalCenter;text:"Status";color:root.fg;font.pixelSize:root.f(11)}StatusDot{width:root.f(11);height:root.f(11);radius:root.f(6);anchors.verticalCenter:parent.verticalCenter;active:calPoint.summary?calPoint.summary.set:false}Text{anchors.verticalCenter:parent.verticalCenter;leftPadding:root.f(8);text:calPoint.summary&&calPoint.summary.set?"SET":"NOT SET";color:root.fg;font.pixelSize:root.f(11)}}
                                    Row{width:parent.width;height:root.f(25);Text{width:root.f(82);anchors.verticalCenter:parent.verticalCenter;text:"Position";color:root.fg;font.pixelSize:root.f(11)}Text{anchors.verticalCenter:parent.verticalCenter;text:calPoint.summary?Number(calPoint.summary.position).toFixed(2)+" m":"—";color:root.fg;font.pixelSize:root.f(12)}}
                                    Row{width:parent.width;height:root.f(25);Text{width:root.f(82);anchors.verticalCenter:parent.verticalCenter;text:"Raw";color:root.fg;font.pixelSize:root.f(11)}Text{anchors.verticalCenter:parent.verticalCenter;text:calPoint.summary?String(calPoint.summary.raw):"—";color:root.fg;font.pixelSize:root.f(12)}}
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
