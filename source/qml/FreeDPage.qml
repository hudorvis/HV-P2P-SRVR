import QtQuick
import QtQuick.Layouts
import "components"

Item {
    id: root
    property var snapshot: ({})
    property var bridge
    property var fd: (snapshot && snapshot.freeD) ? snapshot.freeD : ({})
    function f(v,d){var n=Number(v);return isNaN(n)?String(d):String(n)}
    function b(v){return !!v}
    function copyMap(m){var o={};if(m){for(var k in m)o[k]=m[k]}return o}

    Timer { id:resetTimer; interval:300; repeat:false; onTriggered:root.refreshEditors() }

    ColumnLayout {
        anchors.fill:parent; spacing:10
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; Layout.preferredHeight:390; spacing:10

            HvCard {
                Layout.fillWidth:true; Layout.fillHeight:true; Layout.preferredWidth:360; title:"Free-D Input"; accent:"#27c4ff"
                contentItem: FreeDInputEditor { id:inputEditor; anchors.fill:parent; modelData:root.fd }
            }

            HvCard {
                Layout.fillWidth:true; Layout.fillHeight:true; Layout.preferredWidth:320; title:"Free-D Output"; accent:"#27c4ff"
                contentItem: FreeDOutputEditor { id:outputEditor; anchors.fill:parent; modelData:root.fd }
            }

            HvCard {
                Layout.fillWidth:true; Layout.fillHeight:true; Layout.preferredWidth:355; title:"Geometry"; accent:"#27c4ff"
                contentItem: GeometryEditor { id:geometryEditor; anchors.fill:parent; modelData:root.fd.points||[]; skateKg:Number(root.fd.skateKg||35); cableKg100m:Number(root.fd.cableKg100m||4.8); tensionKg:Number(root.fd.tensionKg||1200); highlineMode:String(root.fd.highlineMode||"Single Highline") }
            }

            HvCard {
                Layout.fillWidth:true; Layout.fillHeight:true; Layout.preferredWidth:275; title:"Lens Calibration"; accent:"#27c4ff"
                contentItem: ColumnLayout {
                    anchors.fill:parent; spacing:7
                    RowLayout { Layout.fillWidth:true; Text{text:"Data Type";color:"#a9b5bf";font.pixelSize:12} HvComboBox{id:lensType;Layout.fillWidth:true;model:["i16","u16","i24","u24"];currentIndex:model.indexOf(String(root.fd.lensType||"i24"))} }
                    RowLayout { Layout.fillWidth:true; Text{text:"Scale";color:"#a9b5bf";font.pixelSize:12} HvComboBox{id:lensScale;Layout.fillWidth:true;model:["Auto","Manual","Full scale"];currentIndex:model.indexOf(String(root.fd.lensScale||"Auto"))} }
                    Rectangle{Layout.fillWidth:true;height:1;color:"#263744"}
                    Text{text:"Zoom Live     "+root.f(root.fd.zoomLive,0);color:"#dce3e8";font.pixelSize:13}
                    RowLayout {Layout.fillWidth:true; HvButton{Layout.fillWidth:true;text:"Wide";onTriggered:root.bridge.captureLens("zoom_wide")} HvButton{Layout.fillWidth:true;text:"Tele";onTriggered:root.bridge.captureLens("zoom_tele")} }
                    Text{text:"Focus Live    "+root.f(root.fd.focusLive,0);color:"#dce3e8";font.pixelSize:13}
                    RowLayout {Layout.fillWidth:true; HvButton{Layout.fillWidth:true;text:"Near";onTriggered:root.bridge.captureLens("focus_near")} HvButton{Layout.fillWidth:true;text:"Far";onTriggered:root.bridge.captureLens("focus_far")} }
                    Item{Layout.fillHeight:true}
                    HvButton{Layout.fillWidth:true;text:"Reset Lens Calibration";confirmRequired:true;onTriggered:root.bridge.resetLens()}
                }
            }

            HvCard {
                Layout.fillHeight:true; Layout.preferredWidth:150; title:"Actions"; accent:"#ffbd16"
                contentItem: ColumnLayout { anchors.fill:parent; spacing:9
                    HvButton{Layout.fillWidth:true;text:"APPLY";selected:true;onTriggered:root.applyNow()}
                    HvButton{Layout.fillWidth:true;text:"RESET";onTriggered:root.resetNow()}
                    Item{Layout.fillHeight:true}
                    Text{text:String(root.snapshot.statusMessage||"");color:"#8999a6";wrapMode:Text.WordWrap;Layout.fillWidth:true;font.pixelSize:11}
                }
            }
        }

        RowLayout {
            Layout.fillWidth:true; Layout.preferredHeight:255; spacing:10
            CableView{Layout.fillWidth:true;Layout.fillHeight:true;snapshot:root.snapshot;sideView:false}
            CableView{Layout.fillWidth:true;Layout.fillHeight:true;snapshot:root.snapshot;sideView:true}
        }
    }

    function resetNow(){ root.bridge.reloadConfig(); resetTimer.restart() }
    function refreshEditors(){
        inputEditor.loadFromModel(); outputEditor.loadFromModel(); geometryEditor.initialised=false; geometryEditor.load()
        lensType.currentIndex=lensType.model.indexOf(String(root.fd.lensType||"i24"))
        lensScale.currentIndex=lensScale.model.indexOf(String(root.fd.lensScale||"Auto"))
    }

    function applyNow(){
        var i=inputEditor.values(), o=outputEditor.values(), g=geometryEditor.values()
        root.bridge.applyFreeD({
            inputEnabled:i.inputEnabled,inputIp:i.inputIp,inputPort:i.inputPort,inputOffsets:i.inputOffsets,inputInverts:i.inputInverts,
            outputEnabled:o.outputEnabled,outputIp:o.outputIp,outputPort:o.outputPort,outputRate:o.outputRate,outputOffsets:o.outputOffsets,outputInverts:o.outputInverts,
            points:g.points,skateKg:g.skateKg,cableKg100m:g.cableKg100m,tensionKg:g.tensionKg,highlineMode:g.highlineMode,
            lensType:lensType.currentText,lensScale:lensScale.currentText,lensCal:root.fd.lensCal||{}
        })
    }
}
