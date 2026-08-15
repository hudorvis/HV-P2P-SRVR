import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "components"

Item {
    id: root
    property var snapshot: ({})
    property var bridge
    property var setup: (snapshot && snapshot.setup) ? snapshot.setup : ({})
    property var auxOptions: ["None","Accel Mode","Battery Change","Drive Mode","Goto Far","Goto Near","Goto P1","Goto P2","Goto P3","Goto P4","Goto P5","Goto P6","Goto Ref","Slip Far","Slip Near","Slip P1","Slip P2","Slip P3","Slip P4","Slip P5","Slip P6","Slip Ref","Limit Calibration","Winch Calibration"]
    function idx(arr,v){ var i=arr.indexOf(String(v)); return i<0?0:i }
    function f(v,d){ var n=Number(v); return isNaN(n)?String(d):String(n) }
    function modeObj(which){ return which===1 ? (setup.mode1||{}) : (setup.mode2||{}) }

    FileDialog { id:loadConfigDialog; title:"Load HV P2P SRVR Configuration"; nameFilters:["JSON configuration (*.json)"]; fileMode:FileDialog.OpenFile; onAccepted:root.bridge.loadConfigPath(selectedFile) }
    FileDialog { id:saveConfigDialog; title:"Save HV P2P SRVR Configuration Backup"; nameFilters:["JSON configuration (*.json)"]; fileMode:FileDialog.SaveFile; onAccepted:root.bridge.saveConfigPath(selectedFile) }

    Timer { id:resetTimer; interval:300; repeat:false; onTriggered:root.refreshEditors() }

    Flickable {
        anchors.fill: parent
        contentWidth: width
        contentHeight: page.implicitHeight
        clip: true
        ScrollBar.vertical: ScrollBar {}

        ColumnLayout {
            id: page
            width: parent.width
            spacing: 10

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 330
                spacing: 10

                HvCard {
                    Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 310
                    title: "CONTROLLER"; accent: "#27c4ff"
                    contentItem: GridLayout {
                        anchors.fill: parent; columns: 2; columnSpacing: 10; rowSpacing: 8
                        Text { text:"CTRL IP"; color:"#a9b5bf"; font.pixelSize:13 }
                        HvTextField { id:ctrlIp; Layout.fillWidth:true; text:String(root.setup.controllerIp||"") }
                        Text { text:"CTRL-TS Link"; color:"#a9b5bf"; font.pixelSize:13 }
                        Text { text: root.setup.ctrlTsConnected ? "● Connected" : "● Disconnected"; color: root.setup.ctrlTsConnected ? "#59db63" : "#8b98a4"; font.pixelSize:13 }
                        Text { text:"ADS1115 Link"; color:"#a9b5bf"; font.pixelSize:13 }
                        Text { text: root.setup.adsConnected ? "● Connected" : "● Disconnected"; color: root.setup.adsConnected ? "#59db63" : "#8b98a4"; font.pixelSize:13 }
                        Text { text:"Direction"; color:"#a9b5bf"; font.pixelSize:13 }
                        HvComboBox { id:ctrlDir; Layout.fillWidth:true; model:["Normal","Inverted"]; currentIndex: root.setup.controllerDirection==="Inverted"?1:0 }
                        Rectangle { Layout.columnSpan:2; Layout.fillWidth:true; height:1; color:"#263744"; Layout.topMargin:5 }
                        Text { Layout.columnSpan:2; text:"Joystick Calibration"; color:"#27c4ff"; font.pixelSize:14; font.weight:Font.Medium }
                        Text { text:"Center"; color:"#a9b5bf"; font.pixelSize:12 }
                        HvTextField { id:joyCenter; Layout.fillWidth:true; text:root.f((root.setup.joy||{}).center,0) }
                        Text { text:"Minimum"; color:"#a9b5bf"; font.pixelSize:12 }
                        HvTextField { id:joyMin; Layout.fillWidth:true; text:root.f((root.setup.joy||{}).min,-1) }
                        Text { text:"Maximum"; color:"#a9b5bf"; font.pixelSize:12 }
                        HvTextField { id:joyMax; Layout.fillWidth:true; text:root.f((root.setup.joy||{}).max,1) }
                    }
                }

                HvCard {
                    Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 310
                    title: "WINCH"; accent: "#27c4ff"
                    contentItem: GridLayout {
                        anchors.fill: parent; columns:2; columnSpacing:10; rowSpacing:9
                        Text { text:"W1P IP"; color:"#a9b5bf"; font.pixelSize:13 }
                        HvTextField { id:winchIp; Layout.fillWidth:true; text:String(root.setup.winchIp||"") }
                        Text { text:"W1P-TS Link"; color:"#a9b5bf"; font.pixelSize:13 }
                        Text { text:root.setup.w1pTsConnected?"● Connected":"● Disconnected"; color:root.setup.w1pTsConnected?"#59db63":"#8b98a4"; font.pixelSize:13 }
                        Text { text:"RS485 Link"; color:"#a9b5bf"; font.pixelSize:13 }
                        Text { text:String(root.setup.rs485||"--"); color:String(root.setup.rs485||"").toLowerCase().indexOf("connect")>=0?"#59db63":"#d6a33d"; font.pixelSize:13 }
                        Text { text:"Direction"; color:"#a9b5bf"; font.pixelSize:13 }
                        HvComboBox { id:winchDir; Layout.fillWidth:true; model:["Normal","Inverted"]; currentIndex:root.setup.winchDirection==="Inverted"?1:0 }
                        Text { text:"CMD Units Per M"; color:"#a9b5bf"; font.pixelSize:13 }
                        HvTextField { id:unitsPerM; Layout.fillWidth:true; text:root.f(root.setup.unitsPerM,21220.7) }
                        Text { text:"Position Source"; color:"#a9b5bf"; font.pixelSize:13 }
                        Rectangle { Layout.fillWidth:true; implicitHeight:34; radius:6; color:"#0a121a"; border.width:1; border.color:"#2b3c4a"; Text{anchors.centerIn:parent;text:String(root.setup.positionSource||"--");color:"#dce4ea";font.pixelSize:13} }
                    }
                }

                HvCard {
                    Layout.fillWidth:true; Layout.fillHeight:true; Layout.preferredWidth:560
                    title:"MOTION PROFILES"; accent:"#27c4ff"
                    contentItem: RowLayout {
                        anchors.fill:parent; spacing:14
                        ModeProfileEditor { id:mode1Editor; Layout.fillWidth:true; Layout.fillHeight:true; heading:"MODE 1"; modelData:root.setup.mode1||{} }
                        Rectangle { width:1; Layout.fillHeight:true; color:"#263744" }
                        ModeProfileEditor { id:mode2Editor; Layout.fillWidth:true; Layout.fillHeight:true; heading:"MODE 2"; modelData:root.setup.mode2||{} }
                    }
                }

                HvCard {
                    Layout.fillHeight:true; Layout.preferredWidth:165
                    title:"ACTIONS"; accent:"#ffbd16"
                    contentItem: ColumnLayout {
                        anchors.fill:parent; spacing:9
                        HvButton { Layout.fillWidth:true; text:"APPLY"; selected:true; onTriggered:root.applyNow() }
                        HvButton { Layout.fillWidth:true; text:"RESET"; onTriggered:root.resetNow() }
                        HvButton { Layout.fillWidth:true; text:"SAVE CONFIG"; onTriggered:saveConfigDialog.open() }
                        HvButton { Layout.fillWidth:true; text:"LOAD CONFIG"; onTriggered:loadConfigDialog.open() }
                        Item { Layout.fillHeight:true }
                        Text { text:String(root.snapshot.statusMessage||""); color:"#8ea0ad"; wrapMode:Text.WordWrap; Layout.fillWidth:true; font.pixelSize:11 }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth:true
                Layout.preferredHeight:245
                spacing:10
                HvCard {
                    Layout.fillWidth:true; Layout.fillHeight:true; title:"CTRL-TS AUX ASSIGN"; accent:"#27c4ff"
                    contentItem: AuxAssignEditor { id:ctrlAuxEditor; anchors.fill:parent; options:root.auxOptions; valuesModel:root.setup.auxCtrl||[] }
                }
                HvCard {
                    Layout.fillWidth:true; Layout.fillHeight:true; title:"W1P-TS AUX ASSIGN"; accent:"#27c4ff"
                    contentItem: AuxAssignEditor { id:w1ptsAuxEditor; anchors.fill:parent; options:root.auxOptions; valuesModel:root.setup.auxW1pts||[] }
                }
                HvCard {
                    Layout.fillWidth:true; Layout.fillHeight:true; Layout.preferredWidth:600; title:"CALIBRATION"; accent:"#27c4ff"
                    contentItem: RowLayout {
                        anchors.fill:parent; spacing:12
                        ColumnLayout {
                            Layout.fillWidth:true; spacing:8
                            HvButton { Layout.fillWidth:true; text:String(root.setup.limitCalibrationLabel||"Limit Calibration"); confirmRequired:true; onTriggered:root.bridge.setupAction("Limit Calibration") }
                            HvButton { Layout.fillWidth:true; text:String(root.setup.winchCalibrationLabel||"Winch Calibration"); confirmRequired:true; onTriggered:root.bridge.setupAction("Winch Calibration") }
                            Text { text:"Calibration buttons advance through the same proven v26.06.26.25 calibration sequence."; color:"#7e8d99"; wrapMode:Text.WordWrap; Layout.fillWidth:true; font.pixelSize:11 }
                        }
                        Rectangle{width:1;Layout.fillHeight:true;color:"#263744"}
                        ColumnLayout {
                            Layout.fillWidth:true
                            Text{text:"Near";color:"#9aa8b4";font.pixelSize:12} Text{text:Number((root.snapshot.run||{}).toNear||0).toFixed(2)+" m";color:"#55d861";font.pixelSize:16}
                            Text{text:"Reference";color:"#9aa8b4";font.pixelSize:12} Text{text:Number((root.snapshot.run||{}).reference||0).toFixed(2)+" m";color:"#55d861";font.pixelSize:16}
                            Text{text:"Far";color:"#9aa8b4";font.pixelSize:12} Text{text:Number((root.snapshot.run||{}).span||0).toFixed(2)+" m";color:"#55d861";font.pixelSize:16}
                        }
                    }
                }
            }

            HvCard {
                Layout.fillWidth:true
                Layout.preferredHeight:380
                title:"LIMITS & PRESETS"
                accent:"#27c4ff"
                contentItem: LimitsPresetsEditor { anchors.fill:parent; runData:root.snapshot.run||{}; bridge:root.bridge }
            }
        }
    }

    function resetNow(){ root.bridge.reloadConfig(); resetTimer.restart() }
    function refreshEditors(){
        ctrlIp.text=String(root.setup.controllerIp||"")
        ctrlDir.currentIndex=root.setup.controllerDirection==="Inverted"?1:0
        winchIp.text=String(root.setup.winchIp||"")
        winchDir.currentIndex=root.setup.winchDirection==="Inverted"?1:0
        unitsPerM.text=root.f(root.setup.unitsPerM,21220.7)
        joyCenter.text=root.f((root.setup.joy||{}).center,0)
        joyMin.text=root.f((root.setup.joy||{}).min,-1)
        joyMax.text=root.f((root.setup.joy||{}).max,1)
        mode1Editor.loadFromModel(); mode2Editor.loadFromModel()
        ctrlAuxEditor.loadFromModel(); w1ptsAuxEditor.loadFromModel()
    }

    // Apply is intentionally centralised so subsequent UI refinements do not
    // change the worker protocol.  Mode values are read from snapshot unless
    // edited profile fields are exposed in a later focused profile editor.
    function applyNow(){
        var d={
            controllerIp:ctrlIp.text,
            controllerDirection:ctrlDir.currentText,
            winchIp:winchIp.text,
            winchDirection:winchDir.currentText,
            unitsPerM:Number(unitsPerM.text),
            mode1:mode1Editor.values(), mode2:mode2Editor.values(),
            auxCtrl:ctrlAuxEditor.values(), auxW1pts:w1ptsAuxEditor.values(),
            joy:{center:Number(joyCenter.text),min:Number(joyMin.text),max:Number(joyMax.text)}
        }
        root.bridge.applySetup(d)
    }
}
