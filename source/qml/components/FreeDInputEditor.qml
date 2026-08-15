import QtQuick
import QtQuick.Layouts

Item {
    id: root
    property var modelData: ({})
    function f(v,d){var n=Number(v);return isNaN(n)?String(d):String(n)}
    function values(){return {
        inputEnabled:enable.currentText==="ON",inputIp:ip.text,inputPort:Number(port.text),
        inputOffsets:{Pan:Number(panOff.text),Tilt:Number(tiltOff.text),Roll:Number(rollOff.text)},
        inputInverts:{Pan:panInv.checked,Tilt:tiltInv.checked,Roll:rollInv.checked,Zoom:zoomInv.checked,Focus:focusInv.checked}
    }}
    function loadFromModel(){
        enable.currentIndex=root.modelData.inputEnabled?1:0; ip.text=String(root.modelData.inputIp||"0.0.0.0"); port.text=root.f(root.modelData.inputPort,40001)
        panOff.text=root.f((root.modelData.inputOffsets||{}).Pan,0); tiltOff.text=root.f((root.modelData.inputOffsets||{}).Tilt,0); rollOff.text=root.f((root.modelData.inputOffsets||{}).Roll,0)
        panInv.checked=!!(root.modelData.inputInverts||{}).Pan; tiltInv.checked=!!(root.modelData.inputInverts||{}).Tilt; rollInv.checked=!!(root.modelData.inputInverts||{}).Roll; zoomInv.checked=!!(root.modelData.inputInverts||{}).Zoom; focusInv.checked=!!(root.modelData.inputInverts||{}).Focus
    }
    ColumnLayout {
        anchors.fill:parent;spacing:7
        RowLayout { Layout.fillWidth:true
            Text{text:"Input";color:"#a9b5bf";font.pixelSize:12} HvComboBox{id:enable;model:["OFF","ON"];currentIndex:root.modelData.inputEnabled?1:0;Layout.preferredWidth:70}
            Text{text:"IP Address";color:"#a9b5bf";font.pixelSize:12} HvTextField{id:ip;text:String(root.modelData.inputIp||"0.0.0.0");Layout.fillWidth:true}
            Text{text:"Port";color:"#a9b5bf";font.pixelSize:12} HvTextField{id:port;text:root.f(root.modelData.inputPort,40001);Layout.preferredWidth:70}
        }
        GridLayout { Layout.fillWidth:true;columns:5;columnSpacing:6;rowSpacing:5
            Text{text:"Value";color:"#788896";font.pixelSize:11} Text{text:"Raw";color:"#788896";font.pixelSize:11} Text{text:"Decoded";color:"#788896";font.pixelSize:11} Text{text:"Offset";color:"#788896";font.pixelSize:11} Text{text:"Invert";color:"#788896";font.pixelSize:11}
            Text{text:"Pan";color:"#dce3e8";font.pixelSize:12} Text{text:String((root.modelData.inputRaw||{}).pan||0);color:"#bac6ce";font.pixelSize:11} Text{text:Number((root.modelData.inputDecoded||{}).pan||0).toFixed(3)+"°";color:"#dce3e8";font.pixelSize:11} HvTextField{id:panOff;text:root.f((root.modelData.inputOffsets||{}).Pan,0)} HvCheck{id:panInv;checked:!!(root.modelData.inputInverts||{}).Pan}
            Text{text:"Tilt";color:"#dce3e8";font.pixelSize:12} Text{text:String((root.modelData.inputRaw||{}).tilt||0);color:"#bac6ce";font.pixelSize:11} Text{text:Number((root.modelData.inputDecoded||{}).tilt||0).toFixed(3)+"°";color:"#dce3e8";font.pixelSize:11} HvTextField{id:tiltOff;text:root.f((root.modelData.inputOffsets||{}).Tilt,0)} HvCheck{id:tiltInv;checked:!!(root.modelData.inputInverts||{}).Tilt}
            Text{text:"Roll";color:"#dce3e8";font.pixelSize:12} Text{text:String((root.modelData.inputRaw||{}).roll||0);color:"#bac6ce";font.pixelSize:11} Text{text:Number((root.modelData.inputDecoded||{}).roll||0).toFixed(3)+"°";color:"#dce3e8";font.pixelSize:11} HvTextField{id:rollOff;text:root.f((root.modelData.inputOffsets||{}).Roll,0)} HvCheck{id:rollInv;checked:!!(root.modelData.inputInverts||{}).Roll}
            Text{text:"Zoom";color:"#dce3e8";font.pixelSize:12} Text{text:String((root.modelData.inputRaw||{}).zoom||0);color:"#bac6ce";font.pixelSize:11} Text{text:String((root.modelData.inputDecoded||{}).zoom||0);color:"#dce3e8";font.pixelSize:11} Item{} HvCheck{id:zoomInv;checked:!!(root.modelData.inputInverts||{}).Zoom}
            Text{text:"Focus";color:"#dce3e8";font.pixelSize:12} Text{text:String((root.modelData.inputRaw||{}).focus||0);color:"#bac6ce";font.pixelSize:11} Text{text:String((root.modelData.inputDecoded||{}).focus||0);color:"#dce3e8";font.pixelSize:11} Item{} HvCheck{id:focusInv;checked:!!(root.modelData.inputInverts||{}).Focus}
            Text{text:"FPS";color:"#dce3e8";font.pixelSize:12} Text{text:"--";color:"#bac6ce";font.pixelSize:11} Text{text:Number((root.modelData.inputDecoded||{}).fps||0).toFixed(2);color:"#dce3e8";font.pixelSize:11} Item{} Item{}
        }
    }
}
