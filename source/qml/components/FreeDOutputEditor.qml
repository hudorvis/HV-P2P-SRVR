import QtQuick
import QtQuick.Layouts

Item {
    id:root
    property var modelData:({})
    function f(v,d){var n=Number(v);return isNaN(n)?String(d):String(n)}
    function values(){return {
        outputEnabled:enable.currentText==="ON",outputIp:ip.text,outputPort:Number(port.text),outputRate:Number(rate.text),
        outputOffsets:{X:Number(xOff.text),Y:Number(yOff.text),Z:Number(zOff.text)},
        outputInverts:{X:xInv.checked,Y:yInv.checked,Z:zInv.checked}
    }}
    function loadFromModel(){
        enable.currentIndex=root.modelData.outputEnabled?1:0; ip.text=String(root.modelData.outputIp||""); port.text=root.f(root.modelData.outputPort,40000); rate.text=root.f(root.modelData.outputRate,25)
        xOff.text=root.f((root.modelData.outputOffsets||{}).X,0); yOff.text=root.f((root.modelData.outputOffsets||{}).Y,0); zOff.text=root.f((root.modelData.outputOffsets||{}).Z,0)
        xInv.checked=!!(root.modelData.outputInverts||{}).X; yInv.checked=!!(root.modelData.outputInverts||{}).Y; zInv.checked=!!(root.modelData.outputInverts||{}).Z
    }
    ColumnLayout {
        anchors.fill:parent;spacing:8
        RowLayout {Layout.fillWidth:true
            Text{text:"Output";color:"#a9b5bf";font.pixelSize:12} HvComboBox{id:enable;model:["OFF","ON"];currentIndex:root.modelData.outputEnabled?1:0;Layout.preferredWidth:70}
            Text{text:"IP Address";color:"#a9b5bf";font.pixelSize:12} HvTextField{id:ip;text:String(root.modelData.outputIp||"");Layout.fillWidth:true}
            Text{text:"Port";color:"#a9b5bf";font.pixelSize:12} HvTextField{id:port;text:root.f(root.modelData.outputPort,40000);Layout.preferredWidth:70}
        }
        GridLayout{Layout.fillWidth:true;columns:4;columnSpacing:7;rowSpacing:7
            Text{text:"Axis";color:"#788896";font.pixelSize:11} Text{text:"Decoded";color:"#788896";font.pixelSize:11} Text{text:"Offset";color:"#788896";font.pixelSize:11} Text{text:"Invert";color:"#788896";font.pixelSize:11}
            Text{text:"X";color:"#dce3e8"} Text{text:Number((root.modelData.xyz||{}).x||0).toFixed(3)+" m";color:"#dce3e8"} HvTextField{id:xOff;text:root.f((root.modelData.outputOffsets||{}).X,0)} HvCheck{id:xInv;checked:!!(root.modelData.outputInverts||{}).X}
            Text{text:"Y";color:"#dce3e8"} Text{text:Number((root.modelData.xyz||{}).y||0).toFixed(3)+" m";color:"#dce3e8"} HvTextField{id:yOff;text:root.f((root.modelData.outputOffsets||{}).Y,0)} HvCheck{id:yInv;checked:!!(root.modelData.outputInverts||{}).Y}
            Text{text:"Z";color:"#dce3e8"} Text{text:Number((root.modelData.xyz||{}).z||0).toFixed(3)+" m";color:"#dce3e8"} HvTextField{id:zOff;text:root.f((root.modelData.outputOffsets||{}).Z,0)} HvCheck{id:zInv;checked:!!(root.modelData.outputInverts||{}).Z}
            Text{text:"FPS";color:"#dce3e8"} Text{text:Number(root.modelData.outputFps||0).toFixed(2);color:"#dce3e8"} HvTextField{id:rate;text:root.f(root.modelData.outputRate,25)} Item{}
        }
        Item{Layout.fillHeight:true}
        Text{text:"X = Tracking   /   Y = Sag   /   Z = Offset";color:"#71818e";font.pixelSize:11}
    }
}
