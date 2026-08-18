import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import "components"
import "pages"

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
    property color blue: "#26d5ff"
    property color lime: "#72ed21"
    property color red: "#ef5757"
    property int page: 0
    property int shortcutTab: 0
    property real s: Math.min(width/1672, height/941)

    function f(v) { return Math.max(1, v*s) }
    function changePage(i) {
        // Force any active HVField to commit BEFORE its page is hidden.
        editCommitSink.forceActiveFocus()
        if (i === 1 && page !== 1)
            backend.beginSetupEdit()
        if (i === 2 && page !== 2)
            backend.beginFreeDEdit()
        page = i
    }
    function changeShortcutTab(i) {
        // This is deliberately ordered: focus loss commits the old tab's field
        // before shortcutTab changes, preventing cross-tab preset writes.
        editCommitSink.forceActiveFocus()
        shortcutTab = i
    }
    function indexOfValue(list, value) {
        for (var i=0; i<list.length; ++i) if (String(list[i]) === String(value)) return i
        return 0
    }

    Item { id: editCommitSink; width: 0; height: 0; x: -10; y: -10 }

    Column {
        anchors.fill: parent
        spacing: f(8)
        topPadding: f(14); leftPadding: f(14); rightPadding: f(14); bottomPadding: f(10)

        // -------------------- LOCKED SHARED SHELL --------------------
        Item {
            width: parent.width-parent.leftPadding-parent.rightPadding
            height: f(62)
            Row {
                anchors.fill: parent; spacing: f(10)
                Item {
                    width:f(360); height:parent.height
                    Rectangle {
                        x:f(4); y:f(1); width:f(78); height:f(54); radius:f(10)
                        color:"transparent"; border.color:green; border.width:1
                        Text { anchors.centerIn:parent; text:"P2P°\nSRVR"; color:fg; font.pixelSize:f(19); horizontalAlignment:Text.AlignHCenter; lineHeight:.78 }
                    }
                    Text { x:f(101); anchors.verticalCenter:parent.verticalCenter; text:"HV P2P  |  SRVR"; color:fg; font.pixelSize:f(27); font.weight:Font.Medium }
                }
                ConnectionCard { width:(parent.width-f(360)-f(170)-f(40))/3; height:parent.height; title:"CTRL"; active:backend.ctrlConnected; line1:backend.ctrlConnected?"Connected":"Disconnected"; line2:backend.ctrlIp }
                ConnectionCard { width:(parent.width-f(360)-f(170)-f(40))/3; height:parent.height; title:"W1P"; active:backend.w1pConnected; line1:backend.w1pConnected?"Connected":"Disconnected"; line2:backend.w1pIp }
                ConnectionCard { width:(parent.width-f(360)-f(170)-f(40))/3; height:parent.height; title:"Free-D"; active:backend.freeDActive; line1:backend.freeDActive?"Active":"Inactive"; line2:Number(backend.freeDFps).toFixed(3)+" fps" }
                Item { width:f(170); height:parent.height; Text { anchors.centerIn:parent; text:"v"+appVersion; color:"#c8cdcb"; font.pixelSize:f(13) } }
            }
        }

        Rectangle {
            width:parent.width-parent.leftPadding-parent.rightPadding; height:f(48); radius:f(5)
            color:backend.systemReady?"#16331a":"#3a1619"; border.color:backend.systemReady?"#34783b":"#8b3b42"; border.width:1
            Text { anchors.centerIn:parent; text:(backend.systemReady?"♢  ":"◇  ")+backend.bannerText; color:backend.systemReady?green:red; font.pixelSize:f(25); font.letterSpacing:f(1.4); font.weight:Font.Medium }
            MouseArea { anchors.fill:parent; cursorShape:Qt.PointingHandCursor; onClicked:backend.toggleSrvrEStop() }
        }

        Rectangle {
            width:parent.width-parent.leftPadding-parent.rightPadding; height:f(50); radius:f(5); color:panel; border.color:border
            Row {
                anchors.fill:parent
                Repeater {
                    model:["▷  Run","⚙  Setup","⌖  Free-D","▤  Log"]
                    Item {
                        width:parent.width/4; height:parent.height
                        Rectangle { anchors.fill:parent; color:navMouse.containsMouse?"#1d2327":"transparent" }
                        Rectangle { visible:window.page===index; anchors.left:parent.left; anchors.right:parent.right; anchors.bottom:parent.bottom; height:f(2); color:"#d6dad8" }
                        Rectangle { visible:index>0; width:1; height:parent.height-f(10); anchors.left:parent.left; anchors.verticalCenter:parent.verticalCenter; color:"#3c4246" }
                        Text { anchors.centerIn:parent; text:modelData; color:fg; font.pixelSize:f(17) }
                        MouseArea { id:navMouse; anchors.fill:parent; hoverEnabled:true; cursorShape:Qt.PointingHandCursor; onClicked:window.changePage(index) }
                    }
                }
            }
        }

        Item {
            width:parent.width-parent.leftPadding-parent.rightPadding
            height:parent.height-f(62+48+50+8*5+44)-parent.topPadding-parent.bottomPadding

            // -------------------- RUN --------------------
            Item {
                anchors.fill:parent; visible:window.page===0
                Column {
                    anchors.fill:parent; spacing:f(8)
                    // Run and Free-D now use the exact same calculated cable profile.
                    // Run overlays Presets/REF/Skate; Free-D overlays P1..P5 geometry.
                    Panel { width:parent.width; height:(parent.height-f(16)-f(252))*0.50; SpanDiagram { anchors.fill:parent; title:"Top View"; subtitle:"X (Tracking) / Z (Offset)"; cableProfile:backend.cableProfile; currentPosition:backend.position-backend.nearLimit; nearLimit:0; farLimit:backend.farLimit-backend.nearLimit; refPoint:backend.refPoint-backend.nearLimit; presets:backend.presets; showPresets:true; showGeometryPoints:false; showSkate:true; showReference:true; nearRamp:backend.nearRampDistance; farRamp:backend.farRampDistance } }
                    Panel { width:parent.width; height:(parent.height-f(16)-f(252))*0.50; SpanDiagram { anchors.fill:parent; title:"Side View"; subtitle:"X (Tracking) / Y (Sag)"; sideView:true; cableProfile:backend.cableProfile; currentPosition:backend.position-backend.nearLimit; nearLimit:0; farLimit:backend.farLimit-backend.nearLimit; refPoint:backend.refPoint-backend.nearLimit; presets:backend.presets; showPresets:true; showGeometryPoints:false; showSkate:true; showReference:true; nearRamp:backend.nearRampDistance; farRamp:backend.farRampDistance } }

                    Item {
                        width:parent.width; height:f(252)
                        property real gaps:f(8)*3
                        property real avail:width-gaps
                        Row {
                            anchors.fill:parent; spacing:f(8)

                            // Fixed mathematical split: Drive 20 / Speed 25 / Position 25 / Shortcuts 30.
                            Panel {
                                width:parent.parent.avail*0.20; height:parent.height
                                Column {
                                    anchors.fill:parent; anchors.margins:f(20); spacing:f(10)
                                    Text { text:"⚙  DRIVE"; color:blue; font.pixelSize:f(19); font.weight:Font.Medium }
                                    Item { width:parent.width; height:f(45); Text{anchors.left:parent.left;anchors.verticalCenter:parent.verticalCenter;text:"Drive Mode";color:fg;font.pixelSize:f(14)} Text{anchors.right:parent.right;anchors.verticalCenter:parent.verticalCenter;text:backend.driveModeName;color:fg;font.pixelSize:f(15)} Rectangle{anchors.bottom:parent.bottom;width:parent.width;height:1;color:"#31383b"} }
                                    Item { width:parent.width; height:f(45); Text{anchors.left:parent.left;anchors.verticalCenter:parent.verticalCenter;text:"Acceleration Mode";color:fg;font.pixelSize:f(14)} Text{anchors.right:parent.right;anchors.verticalCenter:parent.verticalCenter;text:backend.accelerationMode;color:fg;font.pixelSize:f(15)} Rectangle{anchors.bottom:parent.bottom;width:parent.width;height:1;color:"#31383b"} }
                                    Item { width:parent.width; height:f(45); Text{anchors.left:parent.left;anchors.verticalCenter:parent.verticalCenter;text:"Battery Change Mode";color:fg;font.pixelSize:f(14)} Text{anchors.right:parent.right;anchors.verticalCenter:parent.verticalCenter;text:backend.batteryChange?"On":"Off";color:fg;font.pixelSize:f(15)} }
                                }
                            }

                            Panel {
                                width:parent.parent.avail*0.25; height:parent.height
                                Column {
                                    anchors.fill:parent; anchors.margins:f(20); spacing:f(14)
                                    Text { text:"◴  SPEED"; color:blue; font.pixelSize:f(19); font.weight:Font.Medium }
                                    Row {
                                        width:parent.width; height:f(150)
                                        Item { width:parent.width/2; height:parent.height; Text{x:0;y:f(9);text:"CURRENT SPEED";color:muted;font.pixelSize:f(12)} Text{x:0;y:f(48);text:Number(backend.currentSpeed).toFixed(1);color:fg;font.pixelSize:f(31)} Text{x:f(79);y:f(62);text:"m/s";color:muted;font.pixelSize:f(14)} Text{x:0;y:f(112);text:Number(backend.currentSpeed*3.6).toFixed(1);color:lime;font.pixelSize:f(20)} Text{x:f(69);y:f(117);text:"km/h";color:muted;font.pixelSize:f(13)} }
                                        Rectangle { width:1; height:parent.height-f(8); color:"#32383c" }
                                        Item { width:parent.width/2-1; height:parent.height; Text{x:f(28);y:f(9);text:"MAX SPEED";color:muted;font.pixelSize:f(12)} Text{x:f(28);y:f(48);text:Number(backend.maxSpeed).toFixed(1);color:fg;font.pixelSize:f(31)} Text{x:f(108);y:f(62);text:"m/s";color:muted;font.pixelSize:f(14)} Text{x:f(28);y:f(112);text:Number(backend.maxSpeed*3.6).toFixed(1);color:lime;font.pixelSize:f(20)} Text{x:f(98);y:f(117);text:"km/h";color:muted;font.pixelSize:f(13)} }
                                    }
                                }
                            }

                            Panel {
                                width:parent.parent.avail*0.25; height:parent.height
                                Column {
                                    anchors.fill:parent; anchors.margins:f(20); spacing:f(12)
                                    Text { text:"⌖  POSITION"; color:blue; font.pixelSize:f(19); font.weight:Font.Medium }
                                    Text { width:parent.width; text:"CURRENT POSITION"; color:muted; font.pixelSize:f(12); horizontalAlignment:Text.AlignHCenter }
                                    Row { anchors.horizontalCenter:parent.horizontalCenter; spacing:f(8); Text{text:Number(backend.position).toFixed(2);color:fg;font.pixelSize:f(31)} Text{text:"m";color:muted;font.pixelSize:f(14);anchors.baseline:parent.children[0].baseline} }
                                    Rectangle { width:parent.width; height:1; color:"#32383c" }
                                    Row { width:parent.width; height:f(82); Item{width:parent.width/2;height:parent.height;Text{anchors.top:parent.top;anchors.horizontalCenter:parent.horizontalCenter;text:"TO NEAR";color:muted;font.pixelSize:f(12)}Text{anchors.centerIn:parent;text:Number(backend.toNear).toFixed(2);color:lime;font.pixelSize:f(20)}Text{anchors.right:parent.right;anchors.verticalCenter:parent.verticalCenter;text:"m";color:muted;font.pixelSize:f(13)}} Rectangle{width:1;height:parent.height;color:"#32383c"} Item{width:parent.width/2-1;height:parent.height;Text{anchors.top:parent.top;anchors.horizontalCenter:parent.horizontalCenter;text:"TO FAR";color:muted;font.pixelSize:f(12)}Text{anchors.centerIn:parent;text:Number(backend.toFar).toFixed(2);color:lime;font.pixelSize:f(20)}Text{anchors.right:parent.right;anchors.verticalCenter:parent.verticalCenter;text:"m";color:muted;font.pixelSize:f(13)}} }
                                }
                            }

                            Panel {
                                width:parent.parent.avail*0.30; height:parent.height
                                Column {
                                    anchors.fill:parent; anchors.margins:f(10); spacing:f(3)
                                    Item {
                                        width:parent.width; height:f(27)
                                        Text { anchors.left:parent.left; anchors.verticalCenter:parent.verticalCenter; text:"▱  SHORTCUTS"; color:blue; font.pixelSize:f(18); font.weight:Font.Medium }
                                    }
                                    Row {
                                        width:parent.width; height:f(27); spacing:f(4)
                                        Repeater { model:["Preset 1-5","Preset 6-10","Limits","System"]; HVTab { width:(parent.width-f(12))/4; height:parent.height; text:modelData; selected:window.shortcutTab===index; accent:blue; onClicked:window.changeShortcutTab(index) } }
                                    }
                                    Rectangle { width:parent.width; height:1; color:"#343a3e" }

                                    // IMPORTANT: Preset 1-5 and 6-10 are separate delegates with
                                    // FIXED indices.  In v08 the index depended on shortcutTab, so
                                    // changing tabs while a field lost focus could commit P6 into P1.
                                    Column {
                                        visible:window.shortcutTab===0; width:parent.width; spacing:f(3)
                                        Repeater {
                                            model:5
                                            delegate:Row {
                                                width:parent.width; height:f(31); spacing:f(5)
                                                property int pi:index
                                                property var p:backend.presets[pi]
                                                Text { width:f(22); anchors.verticalCenter:parent.verticalCenter; text:"P"+(parent.pi+1); color:fg; font.pixelSize:f(13) }
                                                HVField { objectName:"presetName"+(parent.pi+1); width:parent.width-f(22+5+73+5+55+5+58+5+26); height:parent.height; bindModel:true; modelText:parent.p?String(parent.p.name):""; onCommit:function(v){backend.setPresetName(parent.pi,v)} }
                                                HVField { objectName:"presetPosition"+(parent.pi+1); width:f(73); height:parent.height; bindModel:true; modelText:parent.p&&parent.p.set?Number(parent.p.position).toFixed(2):"0.00"; horizontalAlignment:TextInput.AlignHCenter; onCommit:function(v){var n=parseFloat(v);if(!isNaN(n))backend.setPresetPosition(parent.pi,n)} }
                                                HVButton { width:f(55); height:parent.height; text:"Save"; onClicked:backend.savePreset(parent.pi) }
                                                HVButton { width:f(58); height:parent.height; text:"Recall"; enabled:parent.p?parent.p.set:false; onClicked:backend.recallPreset(parent.pi) }
                                                HVButton { width:f(26); height:parent.height; text:parent.p&&parent.p.visible?"◉":"○"; onClicked:backend.togglePresetVisible(parent.pi) }
                                            }
                                        }
                                    }
                                    Column {
                                        visible:window.shortcutTab===1; width:parent.width; spacing:f(3)
                                        Repeater {
                                            model:5
                                            delegate:Row {
                                                width:parent.width; height:f(31); spacing:f(5)
                                                property int pi:index+5
                                                property var p:backend.presets[pi]
                                                Text { width:f(22); anchors.verticalCenter:parent.verticalCenter; text:"P"+(parent.pi+1); color:fg; font.pixelSize:f(13) }
                                                HVField { objectName:"presetName"+(parent.pi+1); width:parent.width-f(22+5+73+5+55+5+58+5+26); height:parent.height; bindModel:true; modelText:parent.p?String(parent.p.name):""; onCommit:function(v){backend.setPresetName(parent.pi,v)} }
                                                HVField { objectName:"presetPosition"+(parent.pi+1); width:f(73); height:parent.height; bindModel:true; modelText:parent.p&&parent.p.set?Number(parent.p.position).toFixed(2):"0.00"; horizontalAlignment:TextInput.AlignHCenter; onCommit:function(v){var n=parseFloat(v);if(!isNaN(n))backend.setPresetPosition(parent.pi,n)} }
                                                HVButton { width:f(55); height:parent.height; text:"Save"; onClicked:backend.savePreset(parent.pi) }
                                                HVButton { width:f(58); height:parent.height; text:"Recall"; enabled:parent.p?parent.p.set:false; onClicked:backend.recallPreset(parent.pi) }
                                                HVButton { width:f(26); height:parent.height; text:parent.p&&parent.p.visible?"◉":"○"; onClicked:backend.togglePresetVisible(parent.pi) }
                                            }
                                        }
                                    }

                                    Column {
                                        visible:window.shortcutTab===2; width:parent.width; spacing:f(2)
                                        Row { width:parent.width;height:f(31);spacing:f(5); Text{width:f(95);anchors.verticalCenter:parent.verticalCenter;text:"NEAR LIMIT";color:fg;font.pixelSize:f(13)} HVButton{width:(parent.width-f(110))/3;height:parent.height;text:"Save";onClicked:backend.saveLimit("Near")} HVButton{width:(parent.width-f(110))/3;height:parent.height;text:"Recall";onClicked:backend.recallLimit("Near")} HVButton{width:(parent.width-f(110))/3;height:parent.height;text:"Slip";onClicked:backend.slipLimit("Near")} }
                                        Row { width:parent.width;height:f(31);spacing:f(5); Text{width:f(95);anchors.verticalCenter:parent.verticalCenter;text:"Ramping";color:fg;font.pixelSize:f(13)} HVCombo{id:nearMode;width:parent.width-f(95+5+94);height:parent.height;model:["Distance","Percentage"];currentIndex:backend.nearRampMode==="Percentage"?1:0;onActivated:function(){backend.changeRampingMode("Near",currentText)}} HVField{width:f(89);height:parent.height;bindModel:true;modelText:Number(backend.nearRampValue).toFixed(2)+(backend.nearRampMode==="Percentage"?" %":" m");horizontalAlignment:TextInput.AlignHCenter;onCommit:function(v){var n=parseFloat(v);if(!isNaN(n))backend.setRamping("Near",nearMode.currentText,n)}} }
                                        Rectangle { width:parent.width; height:1; color:"#343a3e" }
                                        Row { width:parent.width;height:f(31);spacing:f(5); Text{width:f(95);anchors.verticalCenter:parent.verticalCenter;text:"FAR LIMIT";color:fg;font.pixelSize:f(13)} HVButton{width:(parent.width-f(110))/3;height:parent.height;text:"Save";onClicked:backend.saveLimit("Far")} HVButton{width:(parent.width-f(110))/3;height:parent.height;text:"Recall";onClicked:backend.recallLimit("Far")} HVButton{width:(parent.width-f(110))/3;height:parent.height;text:"Slip";onClicked:backend.slipLimit("Far")} }
                                        Row { width:parent.width;height:f(31);spacing:f(5); Text{width:f(95);anchors.verticalCenter:parent.verticalCenter;text:"Ramping";color:fg;font.pixelSize:f(13)} HVCombo{id:farMode;width:parent.width-f(95+5+94);height:parent.height;model:["Distance","Percentage"];currentIndex:backend.farRampMode==="Percentage"?1:0;onActivated:function(){backend.changeRampingMode("Far",currentText)}} HVField{width:f(89);height:parent.height;bindModel:true;modelText:Number(backend.farRampValue).toFixed(2)+(backend.farRampMode==="Percentage"?" %":" m");horizontalAlignment:TextInput.AlignHCenter;onCommit:function(v){var n=parseFloat(v);if(!isNaN(n))backend.setRamping("Far",farMode.currentText,n)}} }
                                        Rectangle { width:parent.width; height:1; color:"#343a3e" }
                                        Row { width:parent.width;height:f(31);spacing:f(5); Text{width:f(95);anchors.verticalCenter:parent.verticalCenter;text:"REF POINT";color:fg;font.pixelSize:f(13)} HVButton{width:(parent.width-f(110))/3;height:parent.height;text:"Save";onClicked:backend.saveLimit("Ref")} HVButton{width:(parent.width-f(110))/3;height:parent.height;text:"Recall";onClicked:backend.recallLimit("Ref")} HVButton{width:(parent.width-f(110))/3;height:parent.height;text:"Slip";onClicked:backend.slipLimit("Ref")} }
                                    }

                                    Column {
                                        visible:window.shortcutTab===3; width:parent.width; spacing:f(5)
                                        Row { width:parent.width;height:f(32);Text{width:f(150);anchors.verticalCenter:parent.verticalCenter;text:"Acceleration Mode";color:fg;font.pixelSize:f(13)}HVButton{width:f(80);height:parent.height;text:"Power";selected:backend.accelerationMode==="Power";onClicked:backend.setAccelerationMode("Power")}HVButton{width:f(80);height:parent.height;text:"Speed";selected:backend.accelerationMode==="Speed";onClicked:backend.setAccelerationMode("Speed")} }
                                        Row { width:parent.width;height:f(32);Text{width:f(150);anchors.verticalCenter:parent.verticalCenter;text:"Battery Change Mode";color:fg;font.pixelSize:f(13)}HVButton{width:f(80);height:parent.height;text:"Off";selected:!backend.batteryChange;onClicked:backend.setBatteryChange(false)}HVButton{width:f(80);height:parent.height;text:"On";selected:backend.batteryChange;onClicked:backend.setBatteryChange(true)} }
                                        Row {
                                            width: parent.width
                                            height: f(32)
                                            spacing: f(4)
                                            Text { width:f(150); anchors.verticalCenter:parent.verticalCenter; text:"Drive Mode"; color:fg; font.pixelSize:f(13) }
                                            HVButton { width:f(54); height:parent.height; text:"Mode 1"; font.pixelSize:f(11); selected:backend.activeDriveMode===0; onClicked:backend.setDriveMode(0) }
                                            HVField { width:(parent.width-f(150+54+54+16))/2; height:parent.height; bindModel:true; modelText:backend.driveMode1Name; font.pixelSize:f(11); leftPadding:f(4); rightPadding:f(4); onCommit:function(v){backend.renameDriveMode(0,v)} }
                                            HVButton { width:f(54); height:parent.height; text:"Mode 2"; font.pixelSize:f(11); selected:backend.activeDriveMode===1; onClicked:backend.setDriveMode(1) }
                                            HVField { width:(parent.width-f(150+54+54+16))/2; height:parent.height; bindModel:true; modelText:backend.driveMode2Name; font.pixelSize:f(11); leftPadding:f(4); rightPadding:f(4); onCommit:function(v){backend.renameDriveMode(1,v)} }
                                        }
                                        Row { width:parent.width;height:f(32);spacing:f(7);Text{width:f(150);anchors.verticalCenter:parent.verticalCenter;text:"Calibration Mode";color:fg;font.pixelSize:f(13)}HVButton{width:(parent.width-f(157))/2;height:parent.height;text:"Limit Calibration";onClicked:backend.openLimitCalibration()}HVButton{width:(parent.width-f(157))/2;height:parent.height;text:"Winch Calibration";onClicked:backend.openWinchCalibration()} }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // -------------------- SETUP --------------------
            Item {
                anchors.fill:parent; visible:window.page===1
                SetupPage {
                    anchors.fill:parent
                    scaleFactor:window.s
                    fg:window.fg
                    muted:window.muted
                    green:window.green
                    cyan:window.blue
                }
            }

            // -------------------- FREE-D --------------------
            Item {
                id: freeDPage
                anchors.fill:parent; visible:window.page===2
                property var fdDraft: backend.freeDDraft
                Column {
                    anchors.fill:parent; spacing:f(8)
                    Item {
                        width:parent.width; height:parent.height*0.66
                        Row {
                            anchors.fill:parent; spacing:f(8)
                            property real cardWidth:(width-f(24))/4

                            // FREE-D INPUT
                            Panel {
                                width:parent.cardWidth; height:parent.height
                                Column {
                                    anchors.fill:parent; anchors.margins:f(12); spacing:f(6)
                                    Text { width:parent.width; text:"FREE-D INPUT"; horizontalAlignment:Text.AlignHCenter; color:blue; font.pixelSize:f(18) }
                                    Row {
                                        width:parent.width; height:f(31); spacing:f(5)
                                        Text{width:f(44);anchors.verticalCenter:parent.verticalCenter;text:"Input:";color:fg;font.pixelSize:f(12)}
                                        HVButton{width:f(46);height:parent.height;text:freeDPage.fdDraft.input_enabled?"ON":"OFF";selected:freeDPage.fdDraft.input_enabled;onClicked:backend.setFreeDEnabled("Input",!freeDPage.fdDraft.input_enabled)}
                                        Text{width:f(66);anchors.verticalCenter:parent.verticalCenter;text:"IP Address:";color:fg;font.pixelSize:f(11)}
                                        HVField{width:parent.width-f(44+46+66+31+54+25);height:parent.height;bindModel:true;modelText:freeDPage.fdDraft.input_bind_ip;font.pixelSize:f(12);onCommit:function(v){backend.setFreeDNetwork("Input","IP",v)}}
                                        Text{width:f(31);anchors.verticalCenter:parent.verticalCenter;text:"Port:";color:fg;font.pixelSize:f(11)}
                                        HVField{width:f(54);height:parent.height;bindModel:true;modelText:String(freeDPage.fdDraft.input_port);font.pixelSize:f(12);horizontalAlignment:TextInput.AlignHCenter;onCommit:function(v){backend.setFreeDNetwork("Input","Port",v)}}
                                    }
                                    Row { width:parent.width;height:f(22);spacing:0;HVReadout{width:parent.width*.22;height:parent.height;text:"Parameter";textColor:muted;horizontalAlignment:Text.AlignLeft}HVReadout{width:parent.width*.18;height:parent.height;text:"Raw";textColor:muted}HVReadout{width:parent.width*.25;height:parent.height;text:"Decoded";textColor:muted}HVReadout{width:parent.width*.21;height:parent.height;text:"Offset";textColor:muted}HVReadout{width:parent.width*.14;height:parent.height;text:"Invert";textColor:muted} }
                                    Repeater {
                                        model:["Cam ID","Pan","Tilt","Roll","Zoom","Focus","FPS"]
                                        delegate:Row {
                                            width:parent.width; height:f(29); spacing:0
                                            property var fd:backend.freeDInputPreview
                                            property bool hasOffset:["Pan","Tilt","Roll"].indexOf(modelData)>=0
                                            property bool hasInvert:["Pan","Tilt","Roll","Zoom","Focus"].indexOf(modelData)>=0
                                            property string rawText:modelData==="Cam ID"?String(fd.cam):modelData==="Pan"?String(fd.panRaw):modelData==="Tilt"?String(fd.tiltRaw):modelData==="Roll"?String(fd.rollRaw):modelData==="Zoom"?String(fd.zoomRaw):modelData==="Focus"?String(fd.focusRaw):Number(fd.fps).toFixed(3)
                                            property string decodedText:modelData==="Cam ID"?Number(fd.cam).toFixed(4):modelData==="Pan"?Number(fd.pan).toFixed(3)+"°":modelData==="Tilt"?Number(fd.tilt).toFixed(3)+"°":modelData==="Roll"?Number(fd.roll).toFixed(3)+"°":modelData==="Zoom"?Number(fd.zoom).toFixed(0):modelData==="Focus"?Number(fd.focus).toFixed(0):Number(fd.fps).toFixed(3)
                                            HVReadout{width:parent.width*.22;height:parent.height;text:modelData;horizontalAlignment:Text.AlignLeft}
                                            HVReadout{width:parent.width*.18;height:parent.height;text:parent.rawText}
                                            HVReadout{width:parent.width*.25;height:parent.height;text:parent.decodedText}
                                            HVField{width:parent.width*.21;height:parent.height;bindModel:true;readOnly:!parent.hasOffset;modelText:parent.hasOffset?Number(freeDPage.fdDraft.input_offsets[modelData]).toFixed(3):"—";horizontalAlignment:TextInput.AlignHCenter;onCommit:function(v){if(parent.hasOffset){var n=parseFloat(v);if(!isNaN(n))backend.setFreeDOffset("Input",modelData,n)}}}
                                            HVCheck{width:parent.width*.14;height:parent.height;interactive:parent.hasInvert;checked:parent.hasInvert?Boolean(freeDPage.fdDraft.input_inverts[modelData]):false;onToggled:function(v){if(parent.hasInvert)backend.setFreeDInvert("Input",modelData,v)}}
                                        }
                                    }
                                    Row { width:parent.width;height:f(25);Text{text:"Input Rate:  "+Number(backend.freeDFps).toFixed(3)+" fps";color:fg;font.pixelSize:f(11)}Item{width:f(24);height:1}Text{text:"Status:  "+(backend.freeDActive?"Locked":"Off");color:backend.freeDActive?green:muted;font.pixelSize:f(11)} }
                                }
                            }

                            // FREE-D OUTPUT
                            Panel {
                                width:parent.cardWidth; height:parent.height
                                Column {
                                    anchors.fill:parent; anchors.margins:f(12); spacing:f(6)
                                    Text { width:parent.width; text:"FREE-D OUTPUT"; horizontalAlignment:Text.AlignHCenter; color:blue; font.pixelSize:f(18) }
                                    Row {
                                        width:parent.width; height:f(31); spacing:f(5)
                                        Text{width:f(48);anchors.verticalCenter:parent.verticalCenter;text:"Output:";color:fg;font.pixelSize:f(12)}
                                        HVButton{width:f(46);height:parent.height;text:freeDPage.fdDraft.output_enabled?"ON":"OFF";selected:freeDPage.fdDraft.output_enabled;onClicked:backend.setFreeDEnabled("Output",!freeDPage.fdDraft.output_enabled)}
                                        Text{width:f(66);anchors.verticalCenter:parent.verticalCenter;text:"IP Address:";color:fg;font.pixelSize:f(11)}
                                        HVField{width:parent.width-f(48+46+66+31+54+25);height:parent.height;bindModel:true;modelText:freeDPage.fdDraft.target_ip;font.pixelSize:f(12);onCommit:function(v){backend.setFreeDNetwork("Output","IP",v)}}
                                        Text{width:f(31);anchors.verticalCenter:parent.verticalCenter;text:"Port:";color:fg;font.pixelSize:f(11)}
                                        HVField{width:f(54);height:parent.height;bindModel:true;modelText:String(freeDPage.fdDraft.target_port);font.pixelSize:f(12);horizontalAlignment:TextInput.AlignHCenter;onCommit:function(v){backend.setFreeDNetwork("Output","Port",v)}}
                                    }
                                    Row { width:parent.width;height:f(22);spacing:0;HVReadout{width:parent.width*.22;height:parent.height;text:"Parameter";textColor:muted;horizontalAlignment:Text.AlignLeft}HVReadout{width:parent.width*.18;height:parent.height;text:"Raw";textColor:muted}HVReadout{width:parent.width*.25;height:parent.height;text:"Decoded";textColor:muted}HVReadout{width:parent.width*.21;height:parent.height;text:"Offset";textColor:muted}HVReadout{width:parent.width*.14;height:parent.height;text:"Invert";textColor:muted} }
                                    Repeater {
                                        model:["X","Y","Z","FPS"]
                                        delegate:Row {
                                            width:parent.width; height:f(31)
                                            property var fd:backend.freeDOutputPreview
                                            property bool axis:modelData!=="FPS"
                                            property real decoded:modelData==="X"?Number(fd.x):modelData==="Y"?Number(fd.y):modelData==="Z"?Number(fd.z):Number(fd.fps)
                                            HVReadout{width:parent.width*.22;height:parent.height;text:modelData;horizontalAlignment:Text.AlignLeft}
                                            HVField{width:parent.width*.18;height:parent.height;bindModel:true;readOnly:parent.axis;modelText:parent.axis?Number(parent.decoded*freeDPage.fdDraft.pos_scale).toFixed(0):Number(freeDPage.fdDraft.rate_hz).toFixed(3);horizontalAlignment:TextInput.AlignHCenter;onCommit:function(v){if(!parent.axis)backend.setFreeDNetwork("Output","FPS",v)}}
                                            HVReadout{width:parent.width*.25;height:parent.height;text:parent.axis?Number(parent.decoded).toFixed(3)+" m":Number(fd.fps).toFixed(3)}
                                            HVField{width:parent.width*.21;height:parent.height;bindModel:true;readOnly:!parent.axis;modelText:parent.axis?Number(freeDPage.fdDraft.output_offsets[modelData]).toFixed(3):"0.000";horizontalAlignment:TextInput.AlignHCenter;onCommit:function(v){if(parent.axis){var n=parseFloat(v);if(!isNaN(n))backend.setFreeDOffset("Output",modelData,n)}}}
                                            HVCheck{width:parent.width*.14;height:parent.height;interactive:parent.axis;checked:parent.axis?Boolean(freeDPage.fdDraft.output_inverts[modelData]):false;onToggled:function(v){if(parent.axis)backend.setFreeDInvert("Output",modelData,v)}}
                                        }
                                    }
                                    Row { width:parent.width;height:f(25);Text{text:"Output Rate:  "+Number(backend.freeDOutputPreview.fps).toFixed(3)+" fps";color:fg;font.pixelSize:f(11)}Item{width:f(24);height:1}Text{text:"Status:  "+(backend.freeDOutputPreview.fps>0?"Streaming":"Stopped");color:backend.freeDOutputPreview.fps>0?green:muted;font.pixelSize:f(11)} }
                                }
                            }

                            // GEOMETRY
                            Panel {
                                width:parent.cardWidth; height:parent.height
                                Column {
                                    anchors.fill:parent; anchors.margins:f(12); spacing:f(6)
                                    Text { width:parent.width; text:"GEOMETRY"; horizontalAlignment:Text.AlignHCenter; color:blue; font.pixelSize:f(18) }
                                    Text { text:"Cable Geometry Points"; color:blue; font.pixelSize:f(11) }
                                    Row { width:parent.width;height:f(21);Text{width:parent.width*.31;text:"Point";color:muted;font.pixelSize:f(10)}Text{width:parent.width*.23;text:"X (m)";color:muted;font.pixelSize:f(10);horizontalAlignment:Text.AlignHCenter}Text{width:parent.width*.23;text:"Y (m)";color:muted;font.pixelSize:f(10);horizontalAlignment:Text.AlignHCenter}Text{width:parent.width*.23;text:"Z (m)";color:muted;font.pixelSize:f(10);horizontalAlignment:Text.AlignHCenter} }
                                    Repeater {
                                        model:5
                                        delegate:Row {
                                            width:parent.width; height:f(28)
                                            property var gp:freeDPage.fdDraft.geometry[index]
                                            Text{width:parent.width*.31;anchors.verticalCenter:parent.verticalCenter;text:parent.gp?parent.gp.name:"";color:fg;font.pixelSize:f(11)}
                                            HVField {
                                                width: parent.width * 0.23
                                                height: parent.height
                                                bindModel: true
                                                modelText: parent.gp ? Number(parent.gp.x).toFixed(3) : "0.000"
                                                horizontalAlignment: TextInput.AlignHCenter
                                                onTextEdited: {
                                                    var n = parseFloat(text)
                                                    if (!isNaN(n))
                                                        backend.setGeometryPoint(index, "x", n)
                                                }
                                                onCommit: function(v) {
                                                    var n = parseFloat(v)
                                                    if (!isNaN(n))
                                                        backend.setGeometryPoint(index, "x", n)
                                                }
                                            }
                                            HVField {
                                                width: parent.width * 0.23
                                                height: parent.height
                                                bindModel: true
                                                modelText: parent.gp ? Number(parent.gp.y).toFixed(3) : "0.000"
                                                horizontalAlignment: TextInput.AlignHCenter
                                                onTextEdited: {
                                                    var n = parseFloat(text)
                                                    if (!isNaN(n))
                                                        backend.setGeometryPoint(index, "y", n)
                                                }
                                                onCommit: function(v) {
                                                    var n = parseFloat(v)
                                                    if (!isNaN(n))
                                                        backend.setGeometryPoint(index, "y", n)
                                                }
                                            }
                                            HVField {
                                                width: parent.width * 0.23
                                                height: parent.height
                                                bindModel: true
                                                readOnly: index !== 0 && index !== 4
                                                modelText: (index === 0 || index === 4) && parent.gp ? Number(parent.gp.z).toFixed(3) : "—"
                                                horizontalAlignment: TextInput.AlignHCenter
                                                onTextEdited: {
                                                    if (index === 0 || index === 4) {
                                                        var n = parseFloat(text)
                                                        if (!isNaN(n))
                                                            backend.setGeometryPoint(index, "z", n)
                                                    }
                                                }
                                                onCommit: function(v) {
                                                    if (index === 0 || index === 4) {
                                                        var n = parseFloat(v)
                                                        if (!isNaN(n))
                                                            backend.setGeometryPoint(index, "z", n)
                                                    }
                                                }
                                            }
                                        }
                                    }
                                    Text { text:"Weights & Tension"; color:blue; font.pixelSize:f(12); topPadding:f(4) }
                                    Row {
                                        width: parent.width
                                        height: f(31)
                                        Text { width: f(105); anchors.verticalCenter: parent.verticalCenter; text: "Skate Weight:"; color: fg; font.pixelSize: f(11) }
                                        HVField {
                                            width: parent.width - f(105 + 86)
                                            height: parent.height
                                            bindModel: true
                                            modelText: Number(freeDPage.fdDraft.skate_weight_value).toFixed(2)
                                            onTextEdited: {
                                                var n = parseFloat(text)
                                                if (!isNaN(n))
                                                    backend.setWeightValue("Skate", n)
                                            }
                                            onCommit: function(v) {
                                                var n = parseFloat(v)
                                                if (!isNaN(n))
                                                    backend.setWeightValue("Skate", n)
                                            }
                                        }
                                        HVCombo {
                                            width: f(86)
                                            height: parent.height
                                            model: ["kg", "lbs"]
                                            currentIndex: freeDPage.fdDraft.skate_weight_unit === "lbs" ? 1 : 0
                                            onActivated: function() { backend.setWeightUnit("Skate", currentText) }
                                        }
                                    }
                                    Row {
                                        width: parent.width
                                        height: f(31)
                                        Text { width: f(105); anchors.verticalCenter: parent.verticalCenter; text: "Cable Weight:"; color: fg; font.pixelSize: f(11) }
                                        HVField {
                                            width: parent.width - f(105 + 108)
                                            height: parent.height
                                            bindModel: true
                                            modelText: Number(freeDPage.fdDraft.cable_weight_value).toFixed(2)
                                            onTextEdited: {
                                                var n = parseFloat(text)
                                                if (!isNaN(n))
                                                    backend.setWeightValue("Cable", n)
                                            }
                                            onCommit: function(v) {
                                                var n = parseFloat(v)
                                                if (!isNaN(n))
                                                    backend.setWeightValue("Cable", n)
                                            }
                                        }
                                        HVCombo {
                                            width: f(108)
                                            height: parent.height
                                            model: ["kg/100m", "lbs/100m"]
                                            currentIndex: freeDPage.fdDraft.cable_weight_unit === "lbs/100m" ? 1 : 0
                                            onActivated: function() { backend.setWeightUnit("Cable", currentText) }
                                        }
                                    }
                                    Row {
                                        width: parent.width
                                        height: f(31)
                                        Text { width: f(105); anchors.verticalCenter: parent.verticalCenter; text: "Cable Tension:"; color: fg; font.pixelSize: f(11) }
                                        HVField {
                                            width: parent.width - f(105 + 96)
                                            height: parent.height
                                            bindModel: true
                                            modelText: Number(freeDPage.fdDraft.cable_tension_value).toFixed(2)
                                            onTextEdited: {
                                                var n = parseFloat(text)
                                                if (!isNaN(n))
                                                    backend.setWeightValue("Tension", n)
                                            }
                                            onCommit: function(v) {
                                                var n = parseFloat(v)
                                                if (!isNaN(n))
                                                    backend.setWeightValue("Tension", n)
                                            }
                                        }
                                        HVCombo {
                                            width: f(96)
                                            height: parent.height
                                            model: ["kg", "lbs"]
                                            currentIndex: freeDPage.fdDraft.cable_tension_unit === "lbs" ? 1 : 0
                                            onActivated: function() { backend.setWeightUnit("Tension", currentText) }
                                        }
                                    }
                                    Row { width:parent.width;height:f(31);Text{width:f(105);anchors.verticalCenter:parent.verticalCenter;text:"Highline Mode:";color:fg;font.pixelSize:f(11)}HVCombo{width:parent.width-f(105);height:parent.height;model:["Single Highline","Dual Highline"];currentIndex:freeDPage.fdDraft.highline_mode==="Dual Highline"?1:0;onActivated:function(){backend.setHighlineMode(currentText)}} }
                                }
                            }

                            // LENS CALIBRATION -- no FOV values by explicit design request.
                            Panel {
                                width:parent.cardWidth; height:parent.height
                                Column {
                                    anchors.fill:parent; anchors.margins:f(12); spacing:f(6)
                                    Text { width:parent.width; text:"LENS CALIBRATION"; horizontalAlignment:Text.AlignHCenter; color:blue; font.pixelSize:f(18) }
                                    Row { width:parent.width;height:f(31);spacing:f(5);Text{width:f(64);anchors.verticalCenter:parent.verticalCenter;text:"Data Type:";color:fg;font.pixelSize:f(11)}HVCombo{width:(parent.width-f(143))/2;height:parent.height;model:["i16","u16","i24","u24"];currentIndex:window.indexOfValue(model,freeDPage.fdDraft.lens_type);onActivated:function(){backend.setLensType(currentText)}}Text{width:f(64);anchors.verticalCenter:parent.verticalCenter;text:"Data Scale:";color:fg;font.pixelSize:f(11)}HVCombo{width:(parent.width-f(143))/2;height:parent.height;model:["Auto","Manual","Full Scale"];currentIndex:window.indexOfValue(model,freeDPage.fdDraft.lens_scale_mode);onActivated:function(){backend.setLensScale(currentText)}} }
                                    Text { text:"LIVE LENS VALUES"; color:blue; font.pixelSize:f(11) }
                                    Row { width:parent.width;height:f(31);spacing:f(6);Text{width:f(50);anchors.verticalCenter:parent.verticalCenter;text:"Zoom:";color:fg;font.pixelSize:f(11)}HVReadout{width:(parent.width-f(112))/2;height:parent.height;text:Number(backend.freeDInputPreview.zoom).toFixed(0)+" ("+Number(backend.freeDInputPreview.zoomPct).toFixed(3)+"%)"}Text{width:f(50);anchors.verticalCenter:parent.verticalCenter;text:"Focus:";color:fg;font.pixelSize:f(11)}HVReadout{width:(parent.width-f(112))/2;height:parent.height;text:Number(backend.freeDInputPreview.focus).toFixed(0)+" ("+Number(backend.freeDInputPreview.focusPct).toFixed(3)+"%)"} }
                                    Rectangle { width:parent.width;height:1;color:"#343a3e" }
                                    Text { text:"ZOOM (Wide ↔ Tele)"; color:blue; font.pixelSize:f(11) }
                                    Row { width:parent.width;height:f(18);Text{width:f(48);text:"Position";color:muted;font.pixelSize:f(9)}Text{width:parent.width-f(48+72+66);text:"Raw Value";color:muted;font.pixelSize:f(9);horizontalAlignment:Text.AlignHCenter}Text{width:f(72);text:"Decoded";color:muted;font.pixelSize:f(9);horizontalAlignment:Text.AlignHCenter}Text{width:f(66);text:"Calibrate";color:muted;font.pixelSize:f(9);horizontalAlignment:Text.AlignHCenter} }
                                    Row { width:parent.width;height:f(29);spacing:f(4);Text{width:f(48);anchors.verticalCenter:parent.verticalCenter;text:"Wide";color:fg;font.pixelSize:f(11)}HVField{width:parent.width-f(48+72+66+12);height:parent.height;bindModel:true;modelText:Number(freeDPage.fdDraft.lens_cal.zoom_wide).toFixed(0);horizontalAlignment:TextInput.AlignHCenter;onCommit:function(v){var n=parseFloat(v);if(!isNaN(n))backend.setLensCalibration("zoom_wide",n)}}HVReadout{width:f(72);height:parent.height;text:"0.00 %"}HVButton{width:f(66);height:parent.height;text:"Cal";onClicked:backend.captureLens("zoom_wide",backend.freeDInputPreview.zoom)} }
                                    Row { width:parent.width;height:f(29);spacing:f(4);Text{width:f(48);anchors.verticalCenter:parent.verticalCenter;text:"Tele";color:fg;font.pixelSize:f(11)}HVField{width:parent.width-f(48+72+66+12);height:parent.height;bindModel:true;modelText:Number(freeDPage.fdDraft.lens_cal.zoom_tele).toFixed(0);horizontalAlignment:TextInput.AlignHCenter;onCommit:function(v){var n=parseFloat(v);if(!isNaN(n))backend.setLensCalibration("zoom_tele",n)}}HVReadout{width:f(72);height:parent.height;text:"100.00 %"}HVButton{width:f(66);height:parent.height;text:"Cal";onClicked:backend.captureLens("zoom_tele",backend.freeDInputPreview.zoom)} }
                                    Text { text:"FOCUS (Near ↔ Far)"; color:blue; font.pixelSize:f(11) }
                                    Row { width:parent.width;height:f(29);spacing:f(4);Text{width:f(48);anchors.verticalCenter:parent.verticalCenter;text:"Near";color:fg;font.pixelSize:f(11)}HVField{width:parent.width-f(48+72+66+12);height:parent.height;bindModel:true;modelText:Number(freeDPage.fdDraft.lens_cal.focus_near).toFixed(0);horizontalAlignment:TextInput.AlignHCenter;onCommit:function(v){var n=parseFloat(v);if(!isNaN(n))backend.setLensCalibration("focus_near",n)}}HVReadout{width:f(72);height:parent.height;text:"0.00 %"}HVButton{width:f(66);height:parent.height;text:"Cal";onClicked:backend.captureLens("focus_near",backend.freeDInputPreview.focus)} }
                                    Row { width:parent.width;height:f(29);spacing:f(4);Text{width:f(48);anchors.verticalCenter:parent.verticalCenter;text:"Far";color:fg;font.pixelSize:f(11)}HVField{width:parent.width-f(48+72+66+12);height:parent.height;bindModel:true;modelText:Number(freeDPage.fdDraft.lens_cal.focus_far).toFixed(0);horizontalAlignment:TextInput.AlignHCenter;onCommit:function(v){var n=parseFloat(v);if(!isNaN(n))backend.setLensCalibration("focus_far",n)}}HVReadout{width:f(72);height:parent.height;text:"100.00 %"}HVButton{width:f(66);height:parent.height;text:"Cal";onClicked:backend.captureLens("focus_far",backend.freeDInputPreview.focus)} }
                                }
                            }
                        }
                    }

                    Item {
                        width:parent.width; height:parent.height*(1-.66)-f(8)
                        Row {
                            anchors.fill:parent; spacing:f(8)
                            Panel { width:(parent.width-f(8))/2;height:parent.height;SpanDiagram{anchors.fill:parent;title:"Top View";subtitle:"X (Tracking) / Z (Offset)";cableProfile:backend.freeDPreviewCableProfile;geometryPoints:freeDPage.fdDraft.geometry;showGeometryPoints:true;showPresets:false;showSkate:false;showReference:false;nearRamp:backend.nearRampDistance;farRamp:backend.farRampDistance} }
                            Panel { width:(parent.width-f(8))/2;height:parent.height;SpanDiagram{anchors.fill:parent;title:"Side View";subtitle:"X (Tracking) / Y (Sag)";sideView:true;cableProfile:backend.freeDPreviewCableProfile;geometryPoints:freeDPage.fdDraft.geometry;showGeometryPoints:true;showPresets:false;showSkate:false;showReference:false;nearRamp:backend.nearRampDistance;farRamp:backend.farRampDistance} }
                        }
                    }
                }
            }

            // -------------------- LOG --------------------
            Item {
                anchors.fill:parent; visible:window.page===3
                LogPage {
                    anchors.fill:parent
                    scaleFactor:window.s
                    fg:window.fg
                    muted:window.muted
                    green:window.green
                    cyan:window.blue
                }
            }
        }

        // Locked footer. Apply/Reset are centred on Setup and Free-D only.
        Panel {
            width:parent.width-parent.leftPadding-parent.rightPadding; height:f(42)
            Text { anchors.left:parent.left; anchors.leftMargin:f(14); anchors.verticalCenter:parent.verticalCenter; text:"SRVR Time:   "+backend.srvrTime; color:"#d7dbd9"; font.pixelSize:f(12) }
            Text { anchors.right:parent.right; anchors.rightMargin:f(14); anchors.verticalCenter:parent.verticalCenter; text:"Uptime:   "+backend.uptime; color:"#d7dbd9"; font.pixelSize:f(12) }
            Row {
                visible:window.page===1 || window.page===2
                anchors.centerIn:parent; spacing:f(20)
                HVButton{width:f(145);height:f(30);text:"Apply";onClicked:{editCommitSink.forceActiveFocus();if(window.page===1)backend.applySetupSettings();else backend.applyFreeDSettings()}}
                HVButton{width:f(145);height:f(30);text:"Reset";onClicked:{editCommitSink.forceActiveFocus();if(window.page===1)backend.resetSetupSettings();else backend.resetFreeDSettings()}}
            }
        }
    }

    // -------------------- LOCKED LIMIT / WINCH CALIBRATION POPUP --------------------
    Rectangle {
        visible:backend.calibrationOpen
        anchors.fill:parent; color:"#99070a0c"; z:50
        MouseArea { anchors.fill:parent }
        Panel {
            width:f(720); height:f(455); anchors.centerIn:parent
            Column {
                anchors.fill:parent; anchors.margins:f(20); spacing:f(14)
                Row { width:parent.width;height:f(32);Text{width:parent.width-f(35);text:backend.calibrationType==="Winch"?"Winch Calibration":"Limit Calibration";color:blue;font.pixelSize:f(22)}Text{width:f(35);text:"×";color:fg;font.pixelSize:f(26);horizontalAlignment:Text.AlignHCenter;MouseArea{anchors.fill:parent;cursorShape:Qt.PointingHandCursor;onClicked:backend.cancelCalibration()}} }
                Row {
                    width:parent.width;height:f(68);spacing:0
                    Repeater {
                        model:backend.calibrationType==="Winch"?["Set Zero","Set 20 m","Done"]:["Set Near","Set Far","Set Ref","Done"]
                        Item { width:parent.width/(backend.calibrationType==="Winch"?3:4);height:parent.height;Rectangle{width:f(30);height:f(30);radius:f(15);anchors.horizontalCenter:parent.horizontalCenter;y:0;color:index<=backend.calibrationStep?green:"#1b2024";border.color:index<=backend.calibrationStep?green:"#6b7275"}Text{anchors.horizontalCenter:parent.horizontalCenter;y:f(7);text:index+1;color:index<=backend.calibrationStep?"#101410":fg;font.pixelSize:f(13)}Rectangle{visible:index<(backend.calibrationType==="Winch"?2:3);x:parent.width/2+f(15);y:f(14);width:parent.width-f(30);height:1;color:index<backend.calibrationStep?green:"#62686b"}Text{anchors.horizontalCenter:parent.horizontalCenter;y:f(39);text:modelData;color:fg;font.pixelSize:f(12)} }
                    }
                }
                Rectangle { width:parent.width;height:1;color:"#3b4245" }
                Row {
                    width:parent.width;height:f(190);spacing:f(24)
                    Item { width:parent.width*.42;height:parent.height;Canvas{anchors.fill:parent;onPaint:{var c=getContext("2d");c.reset();c.strokeStyle="#d8ddda";c.lineWidth=1;c.beginPath();c.moveTo(52,120);c.lineTo(65,48);c.lineTo(78,120);c.moveTo(45,120);c.lineTo(85,120);c.moveTo(52,90);c.lineTo(78,90);c.stroke();c.strokeRect(width-76,82,38,30);c.strokeRect(width-82,89,6,14);c.strokeRect(width-38,89,6,14);c.strokeStyle=green;c.setLineDash([5,4]);c.beginPath();c.moveTo(90,98);c.lineTo(width-90,98);c.stroke()}}Text{anchors.left:parent.left;anchors.bottom:parent.bottom;text:backend.calibrationStep===0?"NEAR\nLIMIT":backend.calibrationStep===1?"FAR\nLIMIT":"REF\nPOINT";color:fg;font.pixelSize:f(14);horizontalAlignment:Text.AlignHCenter}Text{anchors.right:parent.right;anchors.bottom:parent.bottom;text:"SKATE";color:fg;font.pixelSize:f(14)} }
                    Rectangle { width:1;height:parent.height;color:"#3a4144" }
                    Column { width:parent.width*.53;height:parent.height;spacing:f(14);Text{text:backend.calibrationTitle;color:blue;font.pixelSize:f(22)}Text{width:parent.width;text:backend.calibrationStep===0?"Move the skate to the near limit position,\nthen press Save Near & Continue.":backend.calibrationStep===1?"Move the skate to the far limit position,\nthen press Save Far & Continue.":backend.calibrationStep===2?"Move the skate to the reference position,\nthen press Save Ref & Continue.":"Calibration points have been saved.";color:fg;font.pixelSize:f(15);lineHeight:1.45}Rectangle{width:parent.width;height:f(64);radius:f(5);color:"#1b2024";border.color:"#3f4649";Text{anchors.centerIn:parent;width:parent.width-f(24);text:"ⓘ   Ensure the skate is stable at the selected position before saving.";color:muted;font.pixelSize:f(13);wrapMode:Text.WordWrap}} }
                }
                Item {
                    width:parent.width;height:f(40)
                    HVButton{anchors.left:parent.left;width:f(110);height:parent.height;text:"Cancel";onClicked:backend.cancelCalibration()}
                    HVButton{anchors.right:nextButton.left;anchors.rightMargin:f(12);width:f(110);height:parent.height;text:"Back";enabled:backend.calibrationStep>0;onClicked:backend.calibrationBack()}
                    HVButton{id:nextButton;anchors.right:parent.right;width:f(180);height:parent.height;text:backend.calibrationType==="Limit"?(backend.calibrationStep===0?"Save Near & Continue":backend.calibrationStep===1?"Save Far & Continue":backend.calibrationStep===2?"Save Ref & Continue":"Done"):(backend.calibrationStep===0?"Set Zero & Continue":backend.calibrationStep===1?"Set 20 m & Continue":"Done");selected:true;onClicked:backend.calibrationNext()}
                }
            }
        }
    }


    // -------------------- JOYSTICK CALIBRATION POPUP --------------------
    Rectangle {
        visible: backend.joystickCalibrationOpen
        anchors.fill: parent
        color: "#99070a0c"
        z: 60
        MouseArea { anchors.fill: parent }
        Panel {
            width: f(720)
            height: f(540)
            anchors.centerIn: parent
            Column {
                anchors.fill: parent
                anchors.margins: f(20)
                spacing: f(14)

                Row {
                    width: parent.width
                    height: f(32)
                    Text { width: parent.width-f(35); text: "Joystick Calibration"; color: blue; font.pixelSize: f(22); font.weight: Font.Medium }
                    Text { width: f(35); text: "×"; color: fg; font.pixelSize: f(26); horizontalAlignment: Text.AlignHCenter; MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: backend.cancelJoystickCalibration() } }
                }

                Row {
                    width: parent.width
                    height: f(68)
                    spacing: 0
                    Repeater {
                        model: ["Set Left", "Set Centre", "Set Right"]
                        Item {
                            width: parent.width/3
                            height: parent.height
                            Rectangle { width:f(30); height:f(30); radius:f(15); anchors.horizontalCenter:parent.horizontalCenter; y:0; color:index<=backend.joystickCalibrationStep?blue:"#1b2024"; border.color:index<=backend.joystickCalibrationStep?blue:"#6b7275" }
                            Text { anchors.horizontalCenter:parent.horizontalCenter; y:f(7); text:index+1; color:index<=backend.joystickCalibrationStep?"#081316":fg; font.pixelSize:f(13) }
                            Rectangle { visible:index<2; x:parent.width/2+f(15); y:f(14); width:parent.width-f(30); height:1; color:index<backend.joystickCalibrationStep?blue:"#62686b" }
                            Text { anchors.horizontalCenter:parent.horizontalCenter; y:f(39); text:modelData; color:index<=backend.joystickCalibrationStep?blue:fg; font.pixelSize:f(12) }
                        }
                    }
                }

                Rectangle { width:parent.width; height:1; color:"#3b4245" }

                Column {
                    width: parent.width
                    height: f(225)
                    spacing: f(12)
                    Text { width:parent.width; text:backend.joystickCalibrationTitle; color:blue; font.pixelSize:f(22); font.weight:Font.Medium; horizontalAlignment:Text.AlignHCenter }
                    Text {
                        width: parent.width
                        text: backend.joystickCalibrationStep===0 ? "Move and hold the joystick fully LEFT, then capture the position." : backend.joystickCalibrationStep===1 ? "Release the joystick to its natural CENTRE position, then capture the centre." : "Move and hold the joystick fully RIGHT, then capture the position to finish calibration."
                        color: fg
                        font.pixelSize: f(14)
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                    }
                    Item {
                        width: parent.width
                        height: f(34)
                        Text { anchors.left:parent.left; anchors.verticalCenter:parent.verticalCenter; text:"LEFT"; color:blue; font.pixelSize:f(11) }
                        Text { anchors.right:parent.right; anchors.verticalCenter:parent.verticalCenter; text:"RIGHT"; color:blue; font.pixelSize:f(11) }
                        Rectangle { id:joyCalTrack; anchors.horizontalCenter:parent.horizontalCenter; anchors.verticalCenter:parent.verticalCenter; width:parent.width-f(120); height:1; color:"#697074" }
                        Rectangle { anchors.verticalCenter:parent.verticalCenter; x:joyCalTrack.x+(joyCalTrack.width-width)*Math.max(0,Math.min(1,(backend.joystickRawValue+1)/2)); width:f(15); height:f(15); radius:f(8); color:blue; border.color:"#50646c"; border.width:f(4) }
                    }
                    Row {
                        width: parent.width
                        height: f(44)
                        spacing: f(12)
                        Repeater {
                            model: [
                                {label:"LEFT", key:"left"},
                                {label:"CENTRE", key:"centre"},
                                {label:"RIGHT", key:"right"}
                            ]
                            Item {
                                width:(parent.width-f(24))/3
                                height:parent.height
                                Text { anchors.left:parent.left; anchors.verticalCenter:parent.verticalCenter; width:f(58); text:modelData.label; color:blue; font.pixelSize:f(10) }
                                HVReadout { anchors.right:parent.right; width:parent.width-f(62); height:f(31); anchors.verticalCenter:parent.verticalCenter; text:String(backend.joystickCalibrationCaptures[modelData.key]) }
                            }
                        }
                    }
                    Text { width:parent.width; text:"Current raw value:  "+Number(backend.joystickRawValue).toFixed(4); color:muted; font.pixelSize:f(12); horizontalAlignment:Text.AlignHCenter }
                    Text { visible:backend.joystickCalibrationError!==""; width:parent.width; text:backend.joystickCalibrationError; color:red; font.pixelSize:f(12); horizontalAlignment:Text.AlignHCenter; wrapMode:Text.WordWrap }
                }

                Rectangle { width:parent.width; height:f(52); radius:f(5); color:"#1b2024"; border.color:"#3f4649"; Text { anchors.centerIn:parent; width:parent.width-f(24); text:"ⓘ   Winch output is held at zero during calibration and remains inhibited until the joystick is returned to centre."; color:muted; font.pixelSize:f(13); horizontalAlignment:Text.AlignHCenter; wrapMode:Text.WordWrap } }

                Item {
                    width: parent.width
                    height: f(40)
                    HVButton { anchors.left:parent.left; width:f(110); height:parent.height; text:"Cancel"; onClicked:backend.cancelJoystickCalibration() }
                    HVButton { anchors.right:joyNextButton.left; anchors.rightMargin:f(12); width:f(110); height:parent.height; text:"Back"; enabled:backend.joystickCalibrationStep>0; onClicked:backend.joystickCalibrationBack() }
                    HVButton { id:joyNextButton; anchors.right:parent.right; width:f(190); height:parent.height; text:backend.joystickCalibrationStep===0?"Set Left & Continue":backend.joystickCalibrationStep===1?"Set Centre & Continue":"Set Right & Done"; selected:true; accent:blue; onClicked:backend.joystickCalibrationNext() }
                }
            }
        }
    }

}
