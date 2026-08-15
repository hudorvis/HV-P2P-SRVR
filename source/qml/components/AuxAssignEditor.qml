import QtQuick
import QtQuick.Layouts

Item {
    id: root
    property var options: []
    property var valuesModel: []
    function idx(v){var i=options.indexOf(String(v));return i<0?0:i}
    function values(){return [a1.currentText,a2.currentText,a3.currentText,a4.currentText]}
    function loadFromModel(){a1.currentIndex=root.idx(root.valuesModel[0]);a2.currentIndex=root.idx(root.valuesModel[1]);a3.currentIndex=root.idx(root.valuesModel[2]);a4.currentIndex=root.idx(root.valuesModel[3])}
    GridLayout {
        anchors.fill:parent; columns:2; columnSpacing:10; rowSpacing:8
        Text{text:"Aux 1";color:"#a9b5bf";font.pixelSize:13} HvComboBox{id:a1;Layout.fillWidth:true;model:root.options;currentIndex:root.idx(root.valuesModel[0])}
        Text{text:"Aux 2";color:"#a9b5bf";font.pixelSize:13} HvComboBox{id:a2;Layout.fillWidth:true;model:root.options;currentIndex:root.idx(root.valuesModel[1])}
        Text{text:"Aux 3";color:"#a9b5bf";font.pixelSize:13} HvComboBox{id:a3;Layout.fillWidth:true;model:root.options;currentIndex:root.idx(root.valuesModel[2])}
        Text{text:"Aux 4";color:"#a9b5bf";font.pixelSize:13} HvComboBox{id:a4;Layout.fillWidth:true;model:root.options;currentIndex:root.idx(root.valuesModel[3])}
    }
}
