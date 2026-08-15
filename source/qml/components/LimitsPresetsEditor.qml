import QtQuick
import QtQuick.Layouts

Item {
    id:root
    property var runData:({})
    property var bridge
    function f(v,d){var n=Number(v);return isNaN(n)?String(d):n.toFixed(2)}

    ColumnLayout {
        anchors.fill:parent;spacing:10
        RowLayout {
            Layout.fillWidth:true;spacing:10
            Repeater {
                model:[{key:"near",title:"Near Limit",pos:0},{key:"ref",title:"Reference",pos:Number(root.runData.reference||0)},{key:"far",title:"Far Limit",pos:Number(root.runData.span||0)}]
                delegate: Rectangle {
                    Layout.fillWidth:true;implicitHeight:115;radius:7;color:"#0a131c";border.width:1;border.color:"#263744"
                    ColumnLayout {anchors.fill:parent;anchors.margins:9;spacing:6
                        RowLayout{Layout.fillWidth:true;Text{text:modelData.title;color:"#e5ebef";font.pixelSize:13;font.weight:Font.Medium}Item{Layout.fillWidth:true}Text{text:Number(modelData.pos).toFixed(2)+" m";color:modelData.key==="ref"?"#27c4ff":"#cbd4db";font.pixelSize:13}}
                        RowLayout{Layout.fillWidth:true;spacing:5
                            HvButton{Layout.fillWidth:true;implicitHeight:31;text:"SET";confirmRequired:true;onTriggered:root.bridge.setLimitPoint(modelData.key)}
                            HvButton{Layout.fillWidth:true;implicitHeight:31;text:"GOTO";confirmRequired:true;onTriggered:root.bridge.gotoLimit(modelData.key)}
                            HvButton{Layout.fillWidth:true;implicitHeight:31;text:"SLIP";confirmRequired:true;onTriggered:root.bridge.slipLimit(modelData.key)}
                        }
                        RowLayout{visible:modelData.key!=="ref";Layout.fillWidth:true
                            Text{text:"Ramp";color:"#84939f";font.pixelSize:11}
                            HvComboBox{id:rampMode;model:["Distance","Percentage"];Layout.preferredWidth:105}
                            HvTextField{id:rampValue;Layout.fillWidth:true;text:modelData.key==="near"?root.f(root.runData.nearRamp,5):root.f(root.runData.farRamp,5)}
                            HvButton{implicitWidth:60;implicitHeight:31;text:"SAVE";onTriggered:root.bridge.setRamp(modelData.key,rampMode.currentText,Number(rampValue.text))}
                        }
                    }
                }
            }
        }
        Rectangle{Layout.fillWidth:true;height:1;color:"#263744"}
        GridLayout {
            Layout.fillWidth:true;columns:7;columnSpacing:6;rowSpacing:6
            Text{text:"Preset";color:"#778793";font.pixelSize:11}Text{text:"Name";color:"#778793";font.pixelSize:11}Text{text:"Position (m)";color:"#778793";font.pixelSize:11}Text{text:"Show";color:"#778793";font.pixelSize:11}Item{}Item{}Item{}
            Repeater {
                model:6
                delegate: Item {
                    Layout.columnSpan:7;Layout.fillWidth:true;implicitHeight:34
                    property var p:(root.runData.presets||[])[index]||{}
                    RowLayout{anchors.fill:parent;spacing:6
                        Text{Layout.preferredWidth:45;text:"P"+(index+1);color:"#dbe3e9";font.pixelSize:12}
                        HvTextField{id:pname;Layout.preferredWidth:130;text:String(parent.parent.p.name||("P"+(index+1)))}
                        HvTextField{id:ppos;Layout.fillWidth:true;text:parent.parent.p.position===null||parent.parent.p.position===undefined?"":Number(parent.parent.p.position).toFixed(2)}
                        HvCheck{id:pshow;checked:parent.parent.p.visible!==false}
                        HvButton{implicitWidth:65;implicitHeight:31;text:"SET";confirmRequired:true;onTriggered:root.bridge.setPresetHere(index)}
                        HvButton{implicitWidth:70;implicitHeight:31;text:"GOTO";confirmRequired:true;onTriggered:root.bridge.gotoPreset(index)}
                        HvButton{implicitWidth:65;implicitHeight:31;text:"SAVE";onTriggered:root.bridge.updatePreset(index,pname.text,ppos.text,pshow.checked)}
                    }
                }
            }
        }
    }
}
