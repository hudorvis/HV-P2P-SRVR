import QtQuick
import QtQuick.Layouts

Item {
    id: root
    property var modelData: []
    property real skateKg: 35
    property real cableKg100m: 4.8
    property real tensionKg: 1200
    property string highlineMode: "Single Highline"
    property bool initialised: false
    function load(){
        pointModel.clear()
        for(var i=0;i<5;i++){
            var p=(root.modelData&&i<root.modelData.length)?root.modelData[i]:({enabled:false,x:i*25,y:0,z:0})
            pointModel.append({use:!!p.enabled,x:Number(p.x||0),y:Number(p.y||0),z:Number(p.z||0)})
        }
        skate.text=String(root.skateKg); cable.text=String(root.cableKg100m); tension.text=String(root.tensionKg)
        mode.currentIndex=String(root.highlineMode).toLowerCase().startsWith("dual")?1:0
        root.initialised = !!(root.modelData && root.modelData.length)
    }
    function values(){
        var pts=[]; for(var i=0;i<pointModel.count;i++){var p=pointModel.get(i);pts.push({enabled:p.use,x:Number(p.x),y:Number(p.y),z:Number(p.z)})}
        return {points:pts,skateKg:Number(skate.text),cableKg100m:Number(cable.text),tensionKg:Number(tension.text),highlineMode:mode.currentText}
    }
    Component.onCompleted: { if (root.modelData && root.modelData.length) load() }
    onModelDataChanged: { if (!root.initialised && root.modelData && root.modelData.length) load() }

    ListModel{id:pointModel}
    ColumnLayout {
        anchors.fill:parent; spacing:6
        GridLayout {
            Layout.fillWidth:true; columns:5; columnSpacing:6; rowSpacing:5
            Text{text:"Use";color:"#788896";font.pixelSize:11} Text{text:"Point";color:"#788896";font.pixelSize:11} Text{text:"X (m)";color:"#788896";font.pixelSize:11} Text{text:"Y (m)";color:"#788896";font.pixelSize:11} Text{text:"Z (m)";color:"#788896";font.pixelSize:11}
            Repeater {
                model:pointModel
                delegate: Item {
                    Layout.columnSpan:5; Layout.fillWidth:true; implicitHeight:31
                    RowLayout { anchors.fill:parent; spacing:6
                        HvCheck{checked:model.use;onToggled:pointModel.setProperty(index,"use",checked)}
                        Text{Layout.preferredWidth:38;text:"P"+(index+1);color:"#dce3e8";font.pixelSize:12}
                        HvTextField{Layout.fillWidth:true;text:String(model.x);onTextChanged:if(activeFocus)pointModel.setProperty(index,"x",Number(text))}
                        HvTextField{Layout.fillWidth:true;text:String(model.y);onTextChanged:if(activeFocus)pointModel.setProperty(index,"y",Number(text))}
                        HvTextField{Layout.fillWidth:true;text:String(model.z);enabled:index===0||index===4;opacity:enabled?1:0.45;onTextChanged:if(activeFocus)pointModel.setProperty(index,"z",Number(text))}
                    }
                }
            }
        }
        RowLayout { Layout.fillWidth:true
            Text{text:"Skate (kg)";color:"#9aa8b4";font.pixelSize:11} HvTextField{id:skate;Layout.preferredWidth:62}
            Text{text:"Cable (kg/100m)";color:"#9aa8b4";font.pixelSize:11} HvTextField{id:cable;Layout.preferredWidth:62}
            Text{text:"Tension (kg)";color:"#9aa8b4";font.pixelSize:11} HvTextField{id:tension;Layout.preferredWidth:70}
        }
        RowLayout { Layout.fillWidth:true; Text{text:"Highline Mode";color:"#9aa8b4";font.pixelSize:11} HvComboBox{id:mode;Layout.fillWidth:true;model:["Single Highline","Dual Highline"]} }
    }
}
