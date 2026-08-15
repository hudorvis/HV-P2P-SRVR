import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Item {
    id:root
    property var snapshot:({})
    property var bridge
    property string filterText:""
    property string severity:"All"
    function matches(line){
        var s=String(line||"")
        if(filterText.length && s.toLowerCase().indexOf(filterText.toLowerCase())<0)return false
        if(severity==="Warning" && s.indexOf("WARN")<0)return false
        if(severity==="Fault" && s.indexOf("ERROR")<0 && s.indexOf("FAULT")<0 && s.indexOf("E-STOP")<0)return false
        if(severity==="Info" && (s.indexOf("WARN")>=0||s.indexOf("ERROR")>=0||s.indexOf("FAULT")>=0))return false
        return true
    }
    function filtered(){var out=[];var l=root.snapshot.log||[];for(var i=0;i<l.length;i++)if(matches(l[i]))out.push(l[i]);return out}

    ColumnLayout {
        anchors.fill:parent;spacing:10
        RowLayout {Layout.fillWidth:true;Layout.preferredHeight:82;spacing:10
            HvCard {Layout.fillWidth:true;Layout.fillHeight:true;Layout.preferredWidth:390;title:"Log View";accent:"#27c4ff";contentItem:RowLayout{anchors.fill:parent;spacing:7
                Repeater{model:["Live","Network","Safety","Free-D"];HvButton{Layout.fillWidth:true;text:modelData;selected:index===0}}
            }}
            HvCard {Layout.fillWidth:true;Layout.fillHeight:true;Layout.preferredWidth:390;title:"Severity";accent:"#27c4ff";contentItem:RowLayout{anchors.fill:parent;spacing:7
                Repeater{model:["All","Info","Warning","Fault"];HvButton{Layout.fillWidth:true;text:modelData;selected:root.severity===modelData;accent:modelData==="Fault"?"#f35c5c":(modelData==="Warning"?"#f0b62b":"#27c4ff");onTriggered:root.severity=modelData}}
            }}
            HvCard {Layout.fillWidth:true;Layout.fillHeight:true;Layout.preferredWidth:370;title:"Search";accent:"#27c4ff";contentItem:HvTextField{anchors.fill:parent;placeholderText:"Search logs…";onTextChanged:root.filterText=text}}
            HvCard {Layout.preferredWidth:320;Layout.fillHeight:true;title:"Actions";accent:"#27c4ff";contentItem:RowLayout{anchors.fill:parent;spacing:8
                HvButton{Layout.fillWidth:true;text:"Save Log";onTriggered:root.bridge.saveLog()} HvButton{Layout.fillWidth:true;text:"Clear Log";confirmRequired:true;onTriggered:root.bridge.clearLog()}
            }}
        }

        RowLayout {Layout.fillWidth:true;Layout.fillHeight:true;spacing:10
            HvCard {Layout.fillWidth:true;Layout.fillHeight:true;title:"Live Log";accent:"#27c4ff";contentItem:Rectangle{anchors.fill:parent;color:"#060b10";radius:6;border.width:1;border.color:"#1c2a35"
                ListView {
                    id:list;anchors.fill:parent;anchors.margins:10;clip:true;model:root.filtered();spacing:2
                    onCountChanged:positionViewAtEnd()
                    delegate:Text{
                        width:list.width;text:modelData;color:String(modelData).indexOf("ERROR")>=0||String(modelData).indexOf("FAULT")>=0?"#ff6666":(String(modelData).indexOf("WARN")>=0?"#ffc239":"#cbd4db")
                        font.family:Qt.platform.os === "osx"?"Menlo":"Consolas";font.pixelSize:12;elide:Text.ElideRight
                    }
                    ScrollBar.vertical:ScrollBar{}
                }
            }}
            ColumnLayout {Layout.preferredWidth:340;Layout.fillHeight:true;spacing:10
                HvCard {Layout.fillWidth:true;Layout.preferredHeight:180;title:"System Summary";accent:"#27c4ff";contentItem:ColumnLayout{anchors.fill:parent
                    Text{text:"Backend: "+(backend.backendReady?"Running":"Stopped");color:backend.backendReady?"#58da62":"#ff6868";font.pixelSize:15}
                    Text{text:"CTRL: "+(((root.snapshot.connections||{}).ctrl)?"Connected":"Disconnected");color:"#d7dfe5";font.pixelSize:13}
                    Text{text:"W1P: "+(((root.snapshot.connections||{}).w1p)?"Connected":"Disconnected");color:"#d7dfe5";font.pixelSize:13}
                    Text{text:"Free-D: "+(((root.snapshot.connections||{}).freeD)?"Active":"Inactive");color:"#d7dfe5";font.pixelSize:13}
                    Item{Layout.fillHeight:true}
                }}
                HvCard {Layout.fillWidth:true;Layout.fillHeight:true;title:"Recent Status";accent:"#27c4ff";contentItem:Text{anchors.fill:parent;text:String(root.snapshot.statusMessage||"");color:"#bdc8d0";wrapMode:Text.WordWrap;font.pixelSize:13}}
            }
        }
    }
}
