import QtQuick 2.15
import QtQuick.Controls 2.15
Item {
    id: root
    property string title: "Top View"
    property string subtitle: "X (Tracking) / Z (Offset)"
    property bool sideView: false
    property real currentPosition: 50
    property real nearLimit: 0
    property real farLimit: 100
    property real refPoint: 50
    property var presets: []
    property real nearRamp: 15
    property real farRamp: 10
    property color accent: "#72ed21"
    Text { x: 18; y: 14; text: root.title; color: "#f4f5f4"; font.family: "Helvetica Neue"; font.pixelSize: 20; font.weight: Font.Medium }
    Text { x: 126; y: 18; text: root.subtitle; color: "#b7bcba"; font.family: "Helvetica Neue"; font.pixelSize: 14 }
    Canvas {
        id: canvas; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.bottom: parent.bottom; anchors.margins: 20; anchors.topMargin: 52
        onWidthChanged: requestPaint(); onHeightChanged: requestPaint()
        Connections { target: backend; function onStateChanged(){ canvas.requestPaint() } }
        function xFor(v){ var span=Math.max(0.001, root.farLimit-root.nearLimit); return 62 + (Math.max(root.nearLimit,Math.min(root.farLimit,v))-root.nearLimit)/span*(width-124) }
        function cableY(xn){ if(!root.sideView) return height*0.38; var d=Math.abs(xn-0.5)*2; return height*(0.56-0.17*d) }
        onPaint: {
            var c=getContext("2d"); c.reset(); c.clearRect(0,0,width,height);
            var left=62, right=width-62, base=height*0.38;
            // ramp zones as subtle wedges - no text labels
            function wedge(xa,xb,leftSide){ c.fillStyle="#252d31"; c.strokeStyle="#626a6e"; c.setLineDash([5,5]); c.beginPath(); if(leftSide){c.moveTo(xa,base+4);c.lineTo(xa,height-12);c.lineTo(xb,height-12);} else {c.moveTo(xb,base+4);c.lineTo(xb,height-12);c.lineTo(xa,height-12);} c.closePath(); c.fill(); c.stroke(); }
            var nr=xFor(root.nearLimit+root.nearRamp), fr=xFor(root.farLimit-root.farRamp); wedge(left,nr,true); wedge(fr,right,false);
            // end limits
            c.strokeStyle="#a4aaa7"; c.setLineDash([5,5]); c.beginPath(); c.moveTo(left,20); c.lineTo(left,height-8); c.moveTo(right,20); c.lineTo(right,height-8); c.stroke(); c.setLineDash([]);
            c.fillStyle="#e8eae9"; c.font="12px Helvetica Neue"; c.textAlign="center"; c.fillText("NEAR LIMIT",left,15); c.fillText("FAR LIMIT",right,15);
            c.font="11px Helvetica Neue"; c.fillText("NEAR",16,48); c.fillText("FAR",width-16,48);
            // cable
            c.strokeStyle="#b9bdbb"; c.lineWidth=1.2; c.beginPath();
            for(var i=0;i<=100;i++){ var t=i/100, x=left+t*(right-left), y=root.sideView?cableY(t):base; if(i===0)c.moveTo(x,y); else c.lineTo(x,y); } c.stroke();
            // camera FOV guide without label
            var sx=xFor(root.currentPosition), sy=root.sideView?cableY((sx-left)/(right-left)):base;
            c.strokeStyle="#606a6f"; c.setLineDash([4,5]); c.beginPath(); c.moveTo(sx,sy+8); c.lineTo(Math.max(left,sx-500),height-12); c.moveTo(sx,sy+8); c.lineTo(Math.min(right,sx+500),height-12); c.stroke(); c.setLineDash([]);
            // presets
            for(var p=0;p<root.presets.length;p++){ var item=root.presets[p]; if(!item.visible||!item.set) continue; var px=xFor(item.position), pt=(px-left)/(right-left), py=root.sideView?cableY(pt):base; c.strokeStyle="#dfe3e1"; c.fillStyle="#dfe3e1"; c.lineWidth=1; c.beginPath(); c.arc(px,py,4,0,Math.PI*2); c.stroke(); c.font="12px Helvetica Neue"; c.textAlign="center"; c.fillText("P"+(p+1),px,py-16); }
            // reference
            var rx=xFor(root.refPoint), rt=(rx-left)/(right-left), ry=root.sideView?cableY(rt):base; c.fillStyle=root.accent; c.beginPath(); c.moveTo(rx,ry-5);c.lineTo(rx+5,ry);c.lineTo(rx,ry+5);c.lineTo(rx-5,ry);c.closePath();c.fill(); c.font="12px Helvetica Neue"; c.fillText("REF",rx,ry-17);
            // skate
            c.fillStyle=root.accent; c.strokeStyle=root.accent; c.textAlign="center"; c.font="13px Helvetica Neue"; c.fillText("SKATE",sx,sy-37); c.beginPath(); c.moveTo(sx-9,sy-30);c.lineTo(sx+9,sy-30);c.lineTo(sx,sy-11);c.closePath();c.fill(); c.strokeStyle="#e4e7e5"; c.strokeRect(sx-8,sy+8,16,13); c.strokeRect(sx-11,sy+11,3,7); c.strokeRect(sx+8,sy+11,3,7);
        }
    }
}
