import QtQuick
import QtQuick.Layouts

Item {
    id: root
    property string heading: "MODE 1"
    property var modelData: ({})
    function f(v,d){ var n=Number(v); return isNaN(n)?String(d):String(n) }
    function values(){ return {name:nameField.text,maxSpeed:Number(maxField.text),gotoSpeed:Number(gotoField.text),accel:Number(accelField.text),decel:Number(decelField.text),crossover:Number(crossField.text),stopDecel:Number(stopField.text)} }
    function loadFromModel(){
        nameField.text=String(root.modelData.name||root.heading.replace("MODE","Mode"))
        maxField.text=root.f(root.modelData.maxSpeed,20)
        gotoField.text=root.f(root.modelData.gotoSpeed,1)
        accelField.text=root.f(root.modelData.accel,2)
        decelField.text=root.f(root.modelData.decel,2)
        crossField.text=root.f(root.modelData.crossover,4)
        stopField.text=root.f(root.modelData.stopDecel,4)
    }

    ColumnLayout {
        anchors.fill: parent; spacing:6
        Text { text:root.heading; color:"#27c4ff"; font.pixelSize:14; font.weight:Font.Medium }
        GridLayout {
            Layout.fillWidth:true; columns:3; columnSpacing:7; rowSpacing:6
            Text{text:"Name";color:"#a9b5bf";font.pixelSize:12} HvTextField{id:nameField;Layout.fillWidth:true;text:String(root.modelData.name||root.heading.replace("MODE","Mode"))} Text{text:""}
            Text{text:"Max Speed";color:"#a9b5bf";font.pixelSize:12} HvTextField{id:maxField;Layout.fillWidth:true;text:root.f(root.modelData.maxSpeed,20)} Text{text:"m/s";color:"#758493";font.pixelSize:11}
            Text{text:"Goto Speed";color:"#a9b5bf";font.pixelSize:12} HvTextField{id:gotoField;Layout.fillWidth:true;text:root.f(root.modelData.gotoSpeed,1)} Text{text:"m/s";color:"#758493";font.pixelSize:11}
            Text{text:"Acceleration";color:"#a9b5bf";font.pixelSize:12} HvTextField{id:accelField;Layout.fillWidth:true;text:root.f(root.modelData.accel,2)} Text{text:"m/s²";color:"#758493";font.pixelSize:11}
            Text{text:"Deceleration";color:"#a9b5bf";font.pixelSize:12} HvTextField{id:decelField;Layout.fillWidth:true;text:root.f(root.modelData.decel,2)} Text{text:"m/s²";color:"#758493";font.pixelSize:11}
            Text{text:"Crossover";color:"#a9b5bf";font.pixelSize:12} HvTextField{id:crossField;Layout.fillWidth:true;text:root.f(root.modelData.crossover,4)} Text{text:"m/s²";color:"#758493";font.pixelSize:11}
            Text{text:"Stop Decel";color:"#a9b5bf";font.pixelSize:12} HvTextField{id:stopField;Layout.fillWidth:true;text:root.f(root.modelData.stopDecel,4)} Text{text:"m/s²";color:"#758493";font.pixelSize:11}
        }
    }
}
