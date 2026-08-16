import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import "components"

ApplicationWindow {
    id: window
    visible: true
    width: 1672; height: 941
    minimumWidth: 1280; minimumHeight: 720
    title: "HV P2P SRVR v" + appVersion
    color: "#0f1316"
    font.family: "Helvetica Neue"
    property color bg: "#0f1316"
    property color panel: "#171c20"
    property color panel2: "#1a1f23"
    property color border: "#4a4f52"
    property color fg: "#f0f2f1"
    property color muted: "#aeb4b1"
    property color green: "#63d84e"
    property color lime: "#72ed21"
    property color red: "#ef5757"
    property int page: 0
    property int shortcutTab: 0
    property real s: Math.min(width/1672, height/941)
    property real m: 14*s

    function f(v) { return Math.max(1, v*s) }

    // ---------- overall shell ----------
    Column {
        anchors.fill: parent
        spacing: f(8)
        topPadding: f(14); leftPadding: f(14); rightPadding: f(14); bottomPadding: f(10)

        // Header: logo/title + three connection cards + version
        Item {
            width: parent.width - parent.leftPadding - parent.rightPadding
            height: f(62)
            Row {
                anchors.fill: parent; spacing: f(10)
                Item {
                    width: f(360); height: parent.height
                    Rectangle { x: 4; y: 1; width: f(78); height: f(54); radius: f(10); color: "transparent"; border.color: green; border.width: 1
                        Text { anchors.centerIn: parent; text: "P2P°\nSRVR"; color: text; font.family: "Helvetica Neue"; font.pixelSize: f(19); horizontalAlignment: Text.AlignHCenter; lineHeight: .78 }
                    }
                    Text { x: f(101); anchors.verticalCenter: parent.verticalCenter; text: "HV P2P  |  SRVR"; color: text; font.family: "Helvetica Neue"; font.pixelSize: f(27); font.weight: Font.Medium }
                }
                ConnectionCard { width: (parent.width-f(360)-f(170)-f(30))/3; height: parent.height; title:"CTRL"; active:backend.ctrlConnected; line1: backend.ctrlConnected?"Connected":"Disconnected"; line2:"172.20.1.101" }
                ConnectionCard { width: (parent.width-f(360)-f(170)-f(30))/3; height: parent.height; title:"W1P"; active:backend.w1pConnected; line1: backend.w1pConnected?"Connected":"Disconnected"; line2:"172.20.1.102" }
                ConnectionCard { width: (parent.width-f(360)-f(170)-f(30))/3; height: parent.height; title:"Free-D"; active:backend.freeDActive; line1:backend.freeDActive?"Active":"Inactive"; line2:Number(backend.freeDFps).toFixed(3)+" fps" }
                Item { width:f(170); height:parent.height; Text { anchors.centerIn: parent; text:"v"+appVersion; color:"#c8cdcb"; font.pixelSize:f(13) } }
            }
        }

        // System banner
        Rectangle {
            width: parent.width - parent.leftPadding - parent.rightPadding; height:f(48); radius:f(5)
            color: backend.systemReady ? "#16331a" : "#3a1619"
            border.color: backend.systemReady ? "#34783b" : "#8b3b42"; border.width: 1
            Text { anchors.centerIn: parent; text:(backend.systemReady?"♢  ":"◇  ")+backend.bannerText; color:backend.systemReady?green:red; font.pixelSize:f(25); font.letterSpacing:f(1.4); font.weight:Font.Medium }
        }

        // Navigation - custom QML, no native macOS tabs
        Rectangle {
            width: parent.width - parent.leftPadding - parent.rightPadding; height:f(50); radius:f(5); color:panel; border.color:border
            Row { anchors.fill:parent
                Repeater { model:["▷  Run","⚙  Setup","⌖  Free-D","▤  Log"]
                    Item { width:parent.width/4; height:parent.height
                        Rectangle { anchors.fill:parent; color:ma.containsMouse?"#1d2327":"transparent" }
                        Rectangle { visible:window.page===index; anchors.left:parent.left; anchors.right:parent.right; anchors.bottom:parent.bottom; height:f(2); color:"#d6dad8" }
                        Rectangle { visible:index>0; width:1; height:parent.height-f(10); anchors.left:parent.left; anchors.verticalCenter:parent.verticalCenter; color:"#3c4246" }
                        Text { anchors.centerIn:parent; text:modelData; color:fg; font.pixelSize:f(17) }
                        MouseArea { id:ma; anchors.fill:parent; hoverEnabled:true; onClicked:window.page=index }
                    }
                }
            }
        }

        // Page content
        Item {
            width: parent.width - parent.leftPadding - parent.rightPadding
            height: parent.height - f(62+48+50+8*5+44) - parent.topPadding - parent.bottomPadding

            // RUN --------------------------------------------------------
            Item {
                anchors.fill:parent; visible:window.page===0
                Column { anchors.fill:parent; spacing:f(8)
                    Panel { width:parent.width; height:(parent.height-f(8)-f(252))*0.50; SpanDiagram { anchors.fill:parent; title:"Top View"; subtitle:"X (Tracking) / Z (Offset)"; currentPosition:backend.position; nearLimit:backend.nearLimit; farLimit:backend.farLimit; refPoint:backend.refPoint; presets:backend.presets; nearRamp:2; farRamp:2 } }
                    Panel { width:parent.width; height:(parent.height-f(8)-f(252))*0.50; SpanDiagram { anchors.fill:parent; title:"Side View"; subtitle:"X (Tracking) / Y (Sag)"; sideView:true; currentPosition:backend.position; nearLimit:backend.nearLimit; farLimit:backend.farLimit; refPoint:backend.refPoint; presets:backend.presets; nearRamp:2; farRamp:2 } }
                    Item {
                        width:parent.width; height:f(252)
                        property real gaps: f(8)*3
                        property real avail: width-gaps
                        Row { anchors.fill:parent; spacing:f(8)
                            // exact 20% / 25% / 25% / 30% fixed split
                            Panel {
                                width:parent.parent.avail*0.20; height:parent.height
                                Column { anchors.fill:parent; anchors.margins:f(20); spacing:f(10)
                                    Text { text:"⚙  DRIVE"; color:lime; font.pixelSize:f(19); font.weight:Font.Medium }
                                    Item { width:parent.width; height:f(45); Text { anchors.left:parent.left; anchors.verticalCenter:parent.verticalCenter; text:"Drive Mode"; color:fg; font.pixelSize:f(14) } Text { anchors.right:parent.right; anchors.verticalCenter:parent.verticalCenter; text:backend.driveModeName; color:fg; font.pixelSize:f(15) } Rectangle{anchors.bottom:parent.bottom;width:parent.width;height:1;color:"#31383b"} }
                                    Item { width:parent.width; height:f(45); Text { anchors.left:parent.left; anchors.verticalCenter:parent.verticalCenter; text:"Acceleration Mode"; color:fg; font.pixelSize:f(14) } Text { anchors.right:parent.right; anchors.verticalCenter:parent.verticalCenter; text:backend.accelerationMode; color:fg; font.pixelSize:f(15) } Rectangle{anchors.bottom:parent.bottom;width:parent.width;height:1;color:"#31383b"} }
                                    Item { width:parent.width; height:f(45); Text { anchors.left:parent.left; anchors.verticalCenter:parent.verticalCenter; text:"Battery Change Mode"; color:fg; font.pixelSize:f(14) } Text { anchors.right:parent.right; anchors.verticalCenter:parent.verticalCenter; text:backend.batteryChange?"On":"Off"; color:fg; font.pixelSize:f(15) } }
                                }
                            }
                            Panel {
                                width:parent.parent.avail*0.25; height:parent.height
                                Column { anchors.fill:parent; anchors.margins:f(20); spacing:f(14)
                                    Text { text:"◴  SPEED"; color:lime; font.pixelSize:f(19); font.weight:Font.Medium }
                                    Row { width:parent.width; height:f(150)
                                        Item { width:parent.width/2; height:parent.height
                                            Text { x:0; y:f(9); text:"CURRENT SPEED"; color:muted; font.pixelSize:f(12) }
                                            Text { x:0; y:f(48); text:Number(backend.currentSpeed).toFixed(1); color:fg; font.pixelSize:f(31) }
                                            Text { x:f(79); y:f(62); text:"m/s"; color:muted; font.pixelSize:f(14) }
                                            Text { x:0; y:f(112); text:Number(backend.currentSpeed*3.6).toFixed(1); color:lime; font.pixelSize:f(20) }
                                            Text { x:f(69); y:f(117); text:"km/h"; color:muted; font.pixelSize:f(13) }
                                        }
                                        Rectangle { width:1; height:parent.height-f(8); color:"#32383c" }
                                        Item { width:parent.width/2-1; height:parent.height
                                            Text { x:f(28); y:f(9); text:"MAX SPEED"; color:muted; font.pixelSize:f(12) }
                                            Text { x:f(28); y:f(48); text:Number(backend.maxSpeed).toFixed(1); color:fg; font.pixelSize:f(31) }
                                            Text { x:f(108); y:f(62); text:"m/s"; color:muted; font.pixelSize:f(14) }
                                            Text { x:f(28); y:f(112); text:Number(backend.maxSpeed*3.6).toFixed(1); color:lime; font.pixelSize:f(20) }
                                            Text { x:f(98); y:f(117); text:"km/h"; color:muted; font.pixelSize:f(13) }
                                        }
                                    }
                                }
                            }
                            Panel {
                                width:parent.parent.avail*0.25; height:parent.height
                                Column { anchors.fill:parent; anchors.margins:f(20); spacing:f(12)
                                    Text { text:"⌖  POSITION"; color:lime; font.pixelSize:f(19); font.weight:Font.Medium }
                                    Text { width:parent.width; text:"CURRENT POSITION"; color:muted; font.pixelSize:f(12); horizontalAlignment:Text.AlignHCenter }
                                    Row { anchors.horizontalCenter:parent.horizontalCenter; spacing:f(8); Text{text:Number(backend.position).toFixed(2);color:fg;font.pixelSize:f(31)} Text{text:"m";color:muted;font.pixelSize:f(14);anchors.baseline:parent.children[0].baseline} }
                                    Rectangle { width:parent.width; height:1; color:"#32383c" }
                                    Row { width:parent.width; height:f(82)
                                        Item { width:parent.width/2; height:parent.height; Text{anchors.top:parent.top;anchors.horizontalCenter:parent.horizontalCenter;text:"TO NEAR";color:muted;font.pixelSize:f(12)} Text{anchors.centerIn:parent;text:Number(backend.toNear).toFixed(2);color:lime;font.pixelSize:f(20)} Text{anchors.right:parent.right;anchors.verticalCenter:parent.verticalCenter;text:"m";color:muted;font.pixelSize:f(13)} }
                                        Rectangle { width:1; height:parent.height; color:"#32383c" }
                                        Item { width:parent.width/2-1; height:parent.height; Text{anchors.top:parent.top;anchors.horizontalCenter:parent.horizontalCenter;text:"TO FAR";color:muted;font.pixelSize:f(12)} Text{anchors.centerIn:parent;text:Number(backend.toFar).toFixed(2);color:lime;font.pixelSize:f(20)} Text{anchors.right:parent.right;anchors.verticalCenter:parent.verticalCenter;text:"m";color:muted;font.pixelSize:f(13)} }
                                    }
                                }
                            }
                            Panel {
                                width:parent.parent.avail*0.30; height:parent.height
                                Column { anchors.fill:parent; anchors.margins:f(12); spacing:f(3)
                                    Row { width:parent.width; height:f(35); spacing:f(4)
                                        Text { width:f(132); anchors.verticalCenter:parent.verticalCenter; text:"▱  SHORTCUTS"; color:lime; font.pixelSize:f(18); font.weight:Font.Medium }
                                        Repeater { model:["Preset 1-5","Preset 6-10","Limits","System"]
                                            HVTab { width:(parent.width-f(136))/4; height:parent.height; text:modelData; selected:window.shortcutTab===index; onClicked:window.shortcutTab=index }
                                        }
                                    }
                                    Rectangle { width:parent.width; height:1; color:"#343a3e" }
                                    // presets 1-5 / 6-10
                                    Column {
                                        visible:window.shortcutTab===0 || window.shortcutTab===1; width:parent.width; spacing:f(3)
                                        Repeater {
                                            model:5
                                            delegate: Row {
                                                width:parent.width; height:f(31); spacing:f(5)
                                                property int pi: index + (window.shortcutTab===0?0:5)
                                                property var p: backend.presets[pi]
                                                Text { width:f(22); anchors.verticalCenter:parent.verticalCenter; text:"P"+(parent.pi+1); color:fg; font.pixelSize:f(13) }
                                                HVField { width:parent.width-f(22+5+73+5+55+5+58+5+26); height:parent.height; text:parent.p?parent.p.name:""; onEditingFinished:backend.setPresetName(parent.pi,text) }
                                                HVField { width:f(73); height:parent.height; horizontalAlignment:TextInput.AlignHCenter; text:parent.p&&parent.p.set?Number(parent.p.position).toFixed(2):"0.00"; onEditingFinished:backend.setPresetPosition(parent.pi,parseFloat(text)||0) }
                                                HVButton { width:f(55); height:parent.height; text:"Save"; onClicked:backend.savePreset(parent.pi) }
                                                HVButton { width:f(58); height:parent.height; text:"Recall"; enabled:parent.p?parent.p.set:false; onClicked:backend.recallPreset(parent.pi) }
                                                HVButton { width:f(26); height:parent.height; text:parent.p&&parent.p.visible?"◉":"○"; onClicked:backend.togglePresetVisible(parent.pi) }
                                            }
                                        }
                                    }
                                    // limits
                                    Column {
                                        visible:window.shortcutTab===2; width:parent.width; spacing:f(2)
                                        Row { width:parent.width;height:f(31);spacing:f(5); Text{width:f(95);anchors.verticalCenter:parent.verticalCenter;text:"NEAR LIMIT";color:fg;font.pixelSize:f(13)} HVButton{width:(parent.width-f(110))/3;height:parent.height;text:"Save";onClicked:backend.saveLimit("Near")} HVButton{width:(parent.width-f(110))/3;height:parent.height;text:"Recall";onClicked:backend.recallLimit("Near")} HVButton{width:(parent.width-f(110))/3;height:parent.height;text:"Slip";onClicked:backend.slipLimit("Near")} }
                                        Row { width:parent.width;height:f(31);spacing:f(5); Text{width:f(95);anchors.verticalCenter:parent.verticalCenter;text:"Ramping";color:fg;font.pixelSize:f(13)} HVCombo{id:nearMode;width:parent.width-f(95+5+94);height:parent.height;model:["Distance","Percentage"]} HVField{id:nearVal;width:f(89);height:parent.height;text:"2.00";horizontalAlignment:TextInput.AlignHCenter;onEditingFinished:backend.setRamping("Near",nearMode.currentText,parseFloat(text)||0)} }
                                        Rectangle { width:parent.width; height:1; color:"#343a3e" }
                                        Row { width:parent.width;height:f(31);spacing:f(5); Text{width:f(95);anchors.verticalCenter:parent.verticalCenter;text:"FAR LIMIT";color:fg;font.pixelSize:f(13)} HVButton{width:(parent.width-f(110))/3;height:parent.height;text:"Save";onClicked:backend.saveLimit("Far")} HVButton{width:(parent.width-f(110))/3;height:parent.height;text:"Recall";onClicked:backend.recallLimit("Far")} HVButton{width:(parent.width-f(110))/3;height:parent.height;text:"Slip";onClicked:backend.slipLimit("Far")} }
                                        Row { width:parent.width;height:f(31);spacing:f(5); Text{width:f(95);anchors.verticalCenter:parent.verticalCenter;text:"Ramping";color:fg;font.pixelSize:f(13)} HVCombo{id:farMode;width:parent.width-f(95+5+94);height:parent.height;model:["Distance","Percentage"]} HVField{id:farVal;width:f(89);height:parent.height;text:"2.00";horizontalAlignment:TextInput.AlignHCenter;onEditingFinished:backend.setRamping("Far",farMode.currentText,parseFloat(text)||0)} }
                                        Rectangle { width:parent.width; height:1; color:"#343a3e" }
                                        Row { width:parent.width;height:f(31);spacing:f(5); Text{width:f(95);anchors.verticalCenter:parent.verticalCenter;text:"REF POINT";color:fg;font.pixelSize:f(13)} HVButton{width:(parent.width-f(110))/3;height:parent.height;text:"Save";onClicked:backend.saveLimit("Ref")} HVButton{width:(parent.width-f(110))/3;height:parent.height;text:"Recall";onClicked:backend.recallLimit("Ref")} HVButton{width:(parent.width-f(110))/3;height:parent.height;text:"Slip";onClicked:backend.slipLimit("Ref")} }
                                    }
                                    // system
                                    Column {
                                        visible:window.shortcutTab===3; width:parent.width; spacing:f(5)
                                        Row { width:parent.width;height:f(32); Text{width:f(150);anchors.verticalCenter:parent.verticalCenter;text:"Acceleration Mode";color:fg;font.pixelSize:f(13)} HVButton{width:f(80);height:parent.height;text:"Power";selected:backend.accelerationMode==="Power";onClicked:backend.setAccelerationMode("Power")} HVButton{width:f(80);height:parent.height;text:"Speed";selected:backend.accelerationMode==="Speed";onClicked:backend.setAccelerationMode("Speed")} }
                                        Row { width:parent.width;height:f(32); Text{width:f(150);anchors.verticalCenter:parent.verticalCenter;text:"Battery Change Mode";color:fg;font.pixelSize:f(13)} HVButton{width:f(80);height:parent.height;text:"Off";selected:!backend.batteryChange;onClicked:backend.setBatteryChange(false)} HVButton{width:f(80);height:parent.height;text:"On";selected:backend.batteryChange;onClicked:backend.setBatteryChange(true)} }
                                        Row { width:parent.width;height:f(32); spacing:f(4); Text{width:f(105);anchors.verticalCenter:parent.verticalCenter;text:"Drive Mode";color:fg;font.pixelSize:f(13)} HVButton{width:f(65);height:parent.height;text:"Mode 1";selected:backend.driveModeName===(backend.driveModeName);onClicked:backend.setDriveMode(0)} HVField{width:(parent.width-f(105+65+65+12))/2;height:parent.height;text:"Camera Move";onEditingFinished:backend.renameDriveMode(0,text)} HVButton{width:f(65);height:parent.height;text:"Mode 2";onClicked:backend.setDriveMode(1)} HVField{width:(parent.width-f(105+65+65+12))/2;height:parent.height;text:"Cable Move";onEditingFinished:backend.renameDriveMode(1,text)} }
                                        Row { width:parent.width;height:f(32); spacing:f(7); Text{width:f(150);anchors.verticalCenter:parent.verticalCenter;text:"Calibration Mode";color:fg;font.pixelSize:f(13)} HVButton{width:(parent.width-f(157))/2;height:parent.height;text:"Limit Calibration";onClicked:backend.openLimitCalibration()} HVButton{width:(parent.width-f(157))/2;height:parent.height;text:"Winch Calibration";onClicked:backend.openWinchCalibration()} }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // SETUP ------------------------------------------------------
            Item {
                anchors.fill:parent; visible:window.page===1
                GridLayout { anchors.fill:parent; columns:2; rowSpacing:f(8); columnSpacing:f(8)
                    Panel { Layout.fillWidth:true; Layout.fillHeight:true; Column{anchors.fill:parent;anchors.margins:f(20);spacing:f(14);Text{text:"CONTROLLER";color:lime;font.pixelSize:f(18);font.weight:Font.Medium} Text{text:"CTRL IP";color:muted;font.pixelSize:f(12)} HVField{width:parent.width;text:"172.20.1.101"} Text{text:"Direction";color:muted;font.pixelSize:f(12)} HVCombo{width:parent.width;model:["Normal","Inverted"]} Text{text:"Qt Quick interim Setup page — final Setup visual design has not yet been locked.";color:muted;font.pixelSize:f(13);wrapMode:Text.WordWrap;width:parent.width} } }
                    Panel { Layout.fillWidth:true; Layout.fillHeight:true; Column{anchors.fill:parent;anchors.margins:f(20);spacing:f(14);Text{text:"WINCH";color:lime;font.pixelSize:f(18);font.weight:Font.Medium} Text{text:"W1P IP";color:muted;font.pixelSize:f(12)} HVField{width:parent.width;text:"172.20.1.102"} Text{text:"Direction";color:muted;font.pixelSize:f(12)} HVCombo{width:parent.width;model:["Normal","Inverted"]} Text{text:"CMD Units Per M";color:muted;font.pixelSize:f(12)} HVField{width:parent.width;text:"21220.7"} } }
                    Panel { Layout.fillWidth:true; Layout.fillHeight:true; Column{anchors.fill:parent;anchors.margins:f(20);spacing:f(14);Text{text:"MOTION PROFILES";color:lime;font.pixelSize:f(18);font.weight:Font.Medium} Text{text:"Mode 1";color:muted} HVField{width:parent.width;text:"Mode 1"} Text{text:"Mode 2";color:muted} HVField{width:parent.width;text:"Mode 2"} Text{text:"Max Speed / Accel / Decel values remain in the Python control engine.";color:muted;font.pixelSize:f(13)} } }
                    Panel { Layout.fillWidth:true; Layout.fillHeight:true; Column{anchors.fill:parent;anchors.margins:f(20);spacing:f(14);Text{text:"ACTIONS / STATUS";color:lime;font.pixelSize:f(18);font.weight:Font.Medium} Text{text:"Functional interim page. The locked Run and Free-D pages use the final Qt Quick design system.";color:muted;font.pixelSize:f(13);wrapMode:Text.WordWrap;width:parent.width} } }
                }
            }

            // FREE-D -----------------------------------------------------
            Item {
                anchors.fill:parent; visible:window.page===2
                Column { anchors.fill:parent; spacing:f(8)
                    Item { width:parent.width; height:parent.height*f(.58)
                        Row { anchors.fill:parent; spacing:f(8)
                            property real cardWidth:(width-f(24))/4
                            Panel { width:parent.cardWidth;height:parent.height
                                Column { anchors.fill:parent;anchors.margins:f(12);spacing:f(7)
                                    Text{width:parent.width;text:"FREE-D INPUT";horizontalAlignment:Text.AlignHCenter;color:fg;font.pixelSize:f(18)}
                                    Row{width:parent.width;height:f(31);spacing:f(5);Text{width:f(45);anchors.verticalCenter:parent.verticalCenter;text:"Input:";color:fg;font.pixelSize:f(12)}HVButton{width:f(44);height:parent.height;text:"ON";selected:true}Text{width:f(68);anchors.verticalCenter:parent.verticalCenter;text:"IP Address:";color:fg;font.pixelSize:f(11)}HVField{width:parent.width-f(45+44+68+46+15);height:parent.height;text:"0.0.0.0"}Text{width:f(31);anchors.verticalCenter:parent.verticalCenter;text:"Port:";color:fg;font.pixelSize:f(11)}HVField{width:f(46);height:parent.height;text:"40001"}}
                                    Row{width:parent.width;height:f(23);Text{width:parent.width*.20;text:"Parameter";color:muted;font.pixelSize:f(11)}Text{width:parent.width*.21;text:"Raw";color:muted;font.pixelSize:f(11);horizontalAlignment:Text.AlignHCenter}Text{width:parent.width*.25;text:"Decoded";color:muted;font.pixelSize:f(11);horizontalAlignment:Text.AlignHCenter}Text{width:parent.width*.21;text:"Offset";color:muted;font.pixelSize:f(11);horizontalAlignment:Text.AlignHCenter}Text{width:parent.width*.13;text:"Invert";color:muted;font.pixelSize:f(11);horizontalAlignment:Text.AlignHCenter}}
                                    Repeater{model:["Cam ID","Pan","Tilt","Roll","Zoom","Focus","FPS"];delegate:Row{width:parent.width;height:f(29);property var fd:backend.freeDInput;Text{width:parent.width*.20;anchors.verticalCenter:parent.verticalCenter;text:modelData;color:fg;font.pixelSize:f(12)}Text{width:parent.width*.21;anchors.verticalCenter:parent.verticalCenter;text:modelData==="Cam ID"?fd.cam:modelData==="Pan"?fd.panRaw:modelData==="Tilt"?fd.tiltRaw:modelData==="Roll"?fd.rollRaw:modelData==="Zoom"?fd.zoomRaw:modelData==="Focus"?fd.focusRaw:Number(fd.fps).toFixed(3);color:fg;font.pixelSize:f(12);horizontalAlignment:Text.AlignHCenter}Text{width:parent.width*.25;anchors.verticalCenter:parent.verticalCenter;text:modelData==="Pan"?Number(fd.pan).toFixed(3)+"°":modelData==="Tilt"?Number(fd.tilt).toFixed(3)+"°":modelData==="Roll"?Number(fd.roll).toFixed(3)+"°":modelData==="Zoom"?Number(fd.zoom).toFixed(0):modelData==="Focus"?Number(fd.focus).toFixed(0):modelData==="FPS"?Number(fd.fps).toFixed(3):"1.0000";color:fg;font.pixelSize:f(12);horizontalAlignment:Text.AlignHCenter}HVField{width:parent.width*.21;height:parent.height;visible:["Pan","Tilt","Roll"].indexOf(modelData)>=0;text:"0.000";horizontalAlignment:TextInput.AlignHCenter}Text{width:parent.width*.13;anchors.verticalCenter:parent.verticalCenter;text:["Pan","Tilt","Roll","Zoom","Focus"].indexOf(modelData)>=0?"□":"";color:muted;font.pixelSize:f(18);horizontalAlignment:Text.AlignHCenter}}}
                                    Row{width:parent.width;Text{text:"Input Rate:  "+Number(backend.freeDFps).toFixed(3)+" fps";color:fg;font.pixelSize:f(12)}Item{width:f(30);height:1}Text{text:"Status:  "+(backend.freeDActive?"Locked":"Off");color:backend.freeDActive?green:muted;font.pixelSize:f(12)}}
                                }
                            }
                            Panel { width:parent.cardWidth;height:parent.height
                                Column{anchors.fill:parent;anchors.margins:f(12);spacing:f(7);Text{width:parent.width;text:"FREE-D OUTPUT";horizontalAlignment:Text.AlignHCenter;color:fg;font.pixelSize:f(18)}
                                    Row{width:parent.width;height:f(31);spacing:f(5);Text{width:f(50);anchors.verticalCenter:parent.verticalCenter;text:"Output:";color:fg;font.pixelSize:f(12)}HVButton{width:f(44);height:parent.height;text:"OFF"}Text{width:f(68);anchors.verticalCenter:parent.verticalCenter;text:"IP Address:";color:fg;font.pixelSize:f(11)}HVField{width:parent.width-f(50+44+68+46+15);height:parent.height;text:"172.20.1.120"}Text{width:f(31);anchors.verticalCenter:parent.verticalCenter;text:"Port:";color:fg;font.pixelSize:f(11)}HVField{width:f(46);height:parent.height;text:"40000"}}
                                    Row{width:parent.width;height:f(23);Text{width:parent.width*.20;text:"Parameter";color:muted;font.pixelSize:f(11)}Text{width:parent.width*.25;text:"Raw";color:muted;font.pixelSize:f(11);horizontalAlignment:Text.AlignHCenter}Text{width:parent.width*.28;text:"Decoded";color:muted;font.pixelSize:f(11);horizontalAlignment:Text.AlignHCenter}Text{width:parent.width*.20;text:"Offset";color:muted;font.pixelSize:f(11);horizontalAlignment:Text.AlignHCenter}}
                                    Repeater{model:["X","Y","Z","FPS"];delegate:Row{width:parent.width;height:f(31);property var fd:backend.freeDOutput;Text{width:parent.width*.20;anchors.verticalCenter:parent.verticalCenter;text:modelData;color:fg;font.pixelSize:f(12)}Text{width:parent.width*.25;anchors.verticalCenter:parent.verticalCenter;text:modelData==="FPS"?Number(fd.fps).toFixed(3):Number((modelData==="X"?fd.x:modelData==="Y"?fd.y:fd.z)*640).toFixed(0);color:fg;font.pixelSize:f(12);horizontalAlignment:Text.AlignHCenter}Text{width:parent.width*.28;anchors.verticalCenter:parent.verticalCenter;text:modelData==="FPS"?Number(fd.fps).toFixed(3):Number(modelData==="X"?fd.x:modelData==="Y"?fd.y:fd.z).toFixed(3)+" m";color:fg;font.pixelSize:f(12);horizontalAlignment:Text.AlignHCenter}HVField{width:parent.width*.20;height:parent.height;visible:modelData!=="FPS";text:"0.000";horizontalAlignment:TextInput.AlignHCenter}}}
                                    Text{text:"Output Rate:  "+Number(backend.freeDOutput.fps).toFixed(3)+" fps     Status:  "+(backend.freeDOutput.fps>0?"Streaming":"Stopped");color:fg;font.pixelSize:f(12)}
                                }
                            }
                            Panel { width:parent.cardWidth;height:parent.height
                                Column{anchors.fill:parent;anchors.margins:f(12);spacing:f(7);Text{width:parent.width;text:"GEOMETRY";horizontalAlignment:Text.AlignHCenter;color:fg;font.pixelSize:f(18)}Text{text:"Cable Geometry Points";color:fg;font.pixelSize:f(11)}
                                    Row{width:parent.width;height:f(22);Text{width:parent.width*.31;text:"Point";color:muted;font.pixelSize:f(11)}Text{width:parent.width*.23;text:"X (m)";color:muted;font.pixelSize:f(11);horizontalAlignment:Text.AlignHCenter}Text{width:parent.width*.23;text:"Y (m)";color:muted;font.pixelSize:f(11);horizontalAlignment:Text.AlignHCenter}Text{width:parent.width*.23;text:"Z (m)";color:muted;font.pixelSize:f(11);horizontalAlignment:Text.AlignHCenter}}
                                    Repeater{model:backend.geometryPoints;delegate:Row{width:parent.width;height:f(28);Text{width:parent.width*.31;anchors.verticalCenter:parent.verticalCenter;text:modelData.name;color:fg;font.pixelSize:f(12)}HVField{width:parent.width*.23;height:parent.height;text:Number(modelData.x).toFixed(3);horizontalAlignment:TextInput.AlignHCenter}HVField{width:parent.width*.23;height:parent.height;text:Number(modelData.y).toFixed(3);horizontalAlignment:TextInput.AlignHCenter}HVField{width:parent.width*.23;height:parent.height;enabled:modelData.z!==null;text:modelData.z===null?"—":Number(modelData.z).toFixed(3);horizontalAlignment:TextInput.AlignHCenter}}}
                                    Text{text:"Weights & Tension";color:fg;font.pixelSize:f(12);topPadding:f(5)}
                                    Row{width:parent.width;height:f(31);Text{width:f(105);anchors.verticalCenter:parent.verticalCenter;text:"Static Weight:";color:fg;font.pixelSize:f(12)}HVField{width:parent.width-f(105+86);height:parent.height;text:"25.00"}HVCombo{width:f(86);height:parent.height;model:["kg","lbs"]}}
                                    Row{width:parent.width;height:f(31);Text{width:f(105);anchors.verticalCenter:parent.verticalCenter;text:"Cable Weight:";color:fg;font.pixelSize:f(12)}HVField{width:parent.width-f(105+86);height:parent.height;text:"4.50"}HVCombo{width:f(86);height:parent.height;model:["kg/100m","lbs/100m"]}}
                                    Row{width:parent.width;height:f(31);Text{width:f(105);anchors.verticalCenter:parent.verticalCenter;text:"Cable Tension:";color:fg;font.pixelSize:f(12)}HVField{width:parent.width-f(105+86);height:parent.height;text:"100.00"}HVCombo{width:f(86);height:parent.height;model:["kg","lbs"]}}
                                    Row{width:parent.width;height:f(31);Text{width:f(105);anchors.verticalCenter:parent.verticalCenter;text:"Highline Mode:";color:fg;font.pixelSize:f(12)}HVCombo{width:parent.width-f(105);height:parent.height;model:["Single Highline","Dual Highline"]}}
                                }
                            }
                            Panel { width:parent.cardWidth;height:parent.height
                                Column{anchors.fill:parent;anchors.margins:f(12);spacing:f(8);Text{width:parent.width;text:"LENS CALIBRATION";horizontalAlignment:Text.AlignHCenter;color:fg;font.pixelSize:f(18)}
                                    Row{width:parent.width;height:f(31);spacing:f(6);Text{width:f(70);anchors.verticalCenter:parent.verticalCenter;text:"Data Type:";color:fg;font.pixelSize:f(12)}HVCombo{width:(parent.width-f(146))/2;height:parent.height;model:["i16","u16","i24","u24"];currentIndex:1}Text{width:f(68);anchors.verticalCenter:parent.verticalCenter;text:"Data Scale:";color:fg;font.pixelSize:f(12)}HVCombo{width:(parent.width-f(146))/2;height:parent.height;model:["Auto","Manual","Full Scale"]}}
                                    Row{width:parent.width;height:f(31);spacing:f(8);Text{width:f(70);anchors.verticalCenter:parent.verticalCenter;text:"Wide FOV:";color:fg;font.pixelSize:f(12)}HVField{width:f(86);height:parent.height;text:"82.0°"}Text{width:f(70);anchors.verticalCenter:parent.verticalCenter;text:"Tele FOV:";color:fg;font.pixelSize:f(12)}HVField{width:f(86);height:parent.height;text:"4.85°"}}
                                    Text{text:"LIVE LENS VALUES";color:fg;font.pixelSize:f(12)}
                                    Row{width:parent.width;height:f(31);Text{width:f(55);anchors.verticalCenter:parent.verticalCenter;text:"Zoom:";color:fg;font.pixelSize:f(12)}Text{anchors.verticalCenter:parent.verticalCenter;text:Number(backend.freeDInput.zoom).toFixed(0)+" ("+((Number(backend.freeDInput.zoom)/32767)*100).toFixed(3)+"%)";color:fg;font.pixelSize:f(12)}Item{width:f(35);height:1}Text{width:f(55);anchors.verticalCenter:parent.verticalCenter;text:"Focus:";color:fg;font.pixelSize:f(12)}Text{anchors.verticalCenter:parent.verticalCenter;text:Number(backend.freeDInput.focus).toFixed(0)+" ("+((Number(backend.freeDInput.focus)/32767)*100).toFixed(3)+"%)";color:fg;font.pixelSize:f(12)}}
                                    Rectangle{width:parent.width;height:1;color:"#343a3e"}
                                    Text{text:"ZOOM (Wide ↔ Tele)";color:fg;font.pixelSize:f(12)}
                                    Row{width:parent.width;height:f(31);spacing:f(6);Text{width:f(42);anchors.verticalCenter:parent.verticalCenter;text:"Wide";color:fg;font.pixelSize:f(12)}HVField{width:(parent.width-f(42+62+70+12))/2;height:parent.height;text:"0"}Text{width:f(62);anchors.verticalCenter:parent.verticalCenter;text:"0.00 %";color:fg;font.pixelSize:f(12);horizontalAlignment:Text.AlignHCenter}HVButton{width:f(70);height:parent.height;text:"Cal"}}
                                    Row{width:parent.width;height:f(31);spacing:f(6);Text{width:f(42);anchors.verticalCenter:parent.verticalCenter;text:"Tele";color:fg;font.pixelSize:f(12)}HVField{width:(parent.width-f(42+62+70+12))/2;height:parent.height;text:"32767"}Text{width:f(62);anchors.verticalCenter:parent.verticalCenter;text:"100.00 %";color:fg;font.pixelSize:f(12);horizontalAlignment:Text.AlignHCenter}HVButton{width:f(70);height:parent.height;text:"Cal"}}
                                    Text{text:"FOCUS (Near ↔ Far)";color:fg;font.pixelSize:f(12)}
                                    Row{width:parent.width;height:f(31);spacing:f(6);Text{width:f(42);anchors.verticalCenter:parent.verticalCenter;text:"Near";color:fg;font.pixelSize:f(12)}HVField{width:(parent.width-f(42+62+70+12))/2;height:parent.height;text:"0"}Text{width:f(62);anchors.verticalCenter:parent.verticalCenter;text:"0.00 %";color:fg;font.pixelSize:f(12);horizontalAlignment:Text.AlignHCenter}HVButton{width:f(70);height:parent.height;text:"Cal"}}
                                    Row{width:parent.width;height:f(31);spacing:f(6);Text{width:f(42);anchors.verticalCenter:parent.verticalCenter;text:"Far";color:fg;font.pixelSize:f(12)}HVField{width:(parent.width-f(42+62+70+12))/2;height:parent.height;text:"32767"}Text{width:f(62);anchors.verticalCenter:parent.verticalCenter;text:"100.00 %";color:fg;font.pixelSize:f(12);horizontalAlignment:Text.AlignHCenter}HVButton{width:f(70);height:parent.height;text:"Cal"}}
                                }
                            }
                        }
                    }
                    Item { width:parent.width; height:parent.height*(1-.58)-f(8); Row{anchors.fill:parent;spacing:f(8);Panel{width:(parent.width-f(8))/2;height:parent.height;SpanDiagram{anchors.fill:parent;title:"Top View";subtitle:"X (Tracking) / Z (Offset)";currentPosition:backend.position;nearLimit:backend.nearLimit;farLimit:backend.farLimit;refPoint:backend.refPoint;presets:[]}}Panel{width:(parent.width-f(8))/2;height:parent.height;SpanDiagram{anchors.fill:parent;title:"Side View";subtitle:"X (Tracking) / Y (Sag)";sideView:true;currentPosition:backend.position;nearLimit:backend.nearLimit;farLimit:backend.farLimit;refPoint:backend.refPoint;presets:[]}}} }
                }
            }

            // LOG --------------------------------------------------------
            Item {
                anchors.fill:parent; visible:window.page===3
                Panel { anchors.fill:parent
                    Column { anchors.fill:parent; anchors.margins:f(16); spacing:f(8)
                        Row { width:parent.width;height:f(32);Text{width:parent.width-f(190);anchors.verticalCenter:parent.verticalCenter;text:"LIVE LOG";color:lime;font.pixelSize:f(18);font.weight:Font.Medium}HVButton{width:f(90);height:parent.height;text:"Save Log"}Item{width:f(8);height:1}HVButton{width:f(90);height:parent.height;text:"Clear Log";onClicked:backend.clearLog()} }
                        Rectangle { width:parent.width;height:parent.height-f(40);color:"#070a0c";border.color:"#535a5e";border.width:1;radius:f(3)
                            ScrollView { anchors.fill:parent; anchors.margins:f(8); TextArea { readOnly:true; text:backend.logText; color:"#d9dcdb"; background:null; wrapMode:TextEdit.NoWrap; font.family:"Menlo"; font.pixelSize:f(11); selectByMouse:true } }
                        }
                    }
                }
            }
        }

        // footer
        Panel {
            width: parent.width - parent.leftPadding - parent.rightPadding; height:f(42)
            Text { anchors.left:parent.left; anchors.leftMargin:f(14); anchors.verticalCenter:parent.verticalCenter; text:"SRVR Time:   "+backend.srvrTime; color:"#d7dbd9"; font.pixelSize:f(12) }
            Text { anchors.right:parent.right; anchors.rightMargin:f(14); anchors.verticalCenter:parent.verticalCenter; text:"Uptime:   "+backend.uptime; color:"#d7dbd9"; font.pixelSize:f(12) }
            Row { visible:window.page===2; anchors.centerIn:parent; spacing:f(20); HVButton{width:f(145);height:f(30);text:"Apply"} HVButton{width:f(145);height:f(30);text:"Reset"} }
        }
    }

    // Locked calibration popup
    Rectangle {
        visible:backend.calibrationOpen
        anchors.fill:parent
        color:"#99070a0c"
        z:50
        MouseArea { anchors.fill:parent }
        Panel {
            width:f(720); height:f(455); anchors.centerIn:parent
            Column { anchors.fill:parent; anchors.margins:f(20); spacing:f(14)
                Row { width:parent.width;height:f(32);Text{width:parent.width-f(35);text:backend.calibrationType==="Winch"?"Winch Calibration":"Limit Calibration";color:fg;font.pixelSize:f(22)}Text{width:f(35);text:"×";color:fg;font.pixelSize:f(26);horizontalAlignment:Text.AlignHCenter;MouseArea{anchors.fill:parent;onClicked:backend.cancelCalibration()}} }
                Row { width:parent.width;height:f(68);spacing:0
                    Repeater { model:backend.calibrationType==="Winch"?["Set Zero","Set 20 m","Done"]:["Set Near","Set Far","Set Ref","Done"]
                        Item { width:parent.width/(backend.calibrationType==="Winch"?3:4);height:parent.height
                            Rectangle{width:f(30);height:f(30);radius:f(15);anchors.horizontalCenter:parent.horizontalCenter;y:0;color:index<=backend.calibrationStep?green:"#1b2024";border.color:index<=backend.calibrationStep?green:"#6b7275"}
                            Text{anchors.horizontalCenter:parent.horizontalCenter;y:f(7);text:index+1;color:index<=backend.calibrationStep?"#101410":fg;font.pixelSize:f(13)}
                            Rectangle{visible:index<(backend.calibrationType==="Winch"?2:3);x:parent.width/2+f(15);y:f(14);width:parent.width-f(30);height:1;color:index<backend.calibrationStep?green:"#62686b"}
                            Text{anchors.horizontalCenter:parent.horizontalCenter;y:f(39);text:modelData;color:fg;font.pixelSize:f(12)}
                        }
                    }
                }
                Rectangle{width:parent.width;height:1;color:"#3b4245"}
                Row { width:parent.width;height:f(190);spacing:f(24)
                    Item { width:parent.width*.42;height:parent.height
                        Canvas { anchors.fill:parent; onPaint:{var c=getContext("2d");c.reset();c.strokeStyle="#d8ddda";c.lineWidth=1;c.beginPath();c.moveTo(52,120);c.lineTo(65,48);c.lineTo(78,120);c.moveTo(45,120);c.lineTo(85,120);c.moveTo(52,90);c.lineTo(78,90);c.stroke();c.strokeRect(width-76,82,38,30);c.strokeRect(width-82,89,6,14);c.strokeRect(width-38,89,6,14);c.strokeStyle=green;c.setLineDash([5,4]);c.beginPath();c.moveTo(90,98);c.lineTo(width-90,98);c.stroke();} }
                        Text{anchors.left:parent.left;anchors.bottom:parent.bottom;text:backend.calibrationStep===0?"NEAR\nLIMIT":backend.calibrationStep===1?"FAR\nLIMIT":"REF\nPOINT";color:fg;font.pixelSize:f(14);horizontalAlignment:Text.AlignHCenter}
                        Text{anchors.right:parent.right;anchors.bottom:parent.bottom;text:"SKATE";color:fg;font.pixelSize:f(14)}
                    }
                    Rectangle{width:1;height:parent.height;color:"#3a4144"}
                    Column { width:parent.width*.53;height:parent.height;spacing:f(14);Text{text:backend.calibrationTitle;color:fg;font.pixelSize:f(22)}Text{width:parent.width;text:backend.calibrationStep===0?"Move the skate to the near limit position,\nthen press Save Near & Continue.":backend.calibrationStep===1?"Move the skate to the far limit position,\nthen continue.":backend.calibrationStep===2?"Move the skate to the reference position,\nthen continue.":"Calibration points have been saved.";color:fg;font.pixelSize:f(15);lineHeight:1.45}Rectangle{width:parent.width;height:f(64);radius:f(5);color:"#1b2024";border.color:"#3f4649";Text{anchors.centerIn:parent;width:parent.width-f(24);text:"ⓘ   Ensure the skate is stable at the selected position before saving.";color:muted;font.pixelSize:f(13);wrapMode:Text.WordWrap}} }
                }
                Item { width:parent.width;height:f(40);HVButton{anchors.left:parent.left;width:f(110);height:parent.height;text:"Cancel";onClicked:backend.cancelCalibration()}HVButton{anchors.right:next.left;anchors.rightMargin:f(12);id:back;width:f(110);height:parent.height;text:"Back";enabled:backend.calibrationStep>0;onClicked:backend.calibrationBack()}HVButton{id:next;anchors.right:parent.right;width:f(170);height:parent.height;text:backend.calibrationStep===0?"Save Near & Continue":backend.calibrationStep>=3?"Done":"Next";selected:true;onClicked:backend.calibrationNext()} }
            }
        }
    }
}
