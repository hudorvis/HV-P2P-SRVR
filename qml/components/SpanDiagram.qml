import QtQuick 2.15

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

    Text { x: 26; y: 14; text: root.title; color: "#f4f5f4"; font.family: "Helvetica Neue"; font.pixelSize: 20; font.weight: Font.Medium }
    Text { x: 137; y: 18; text: root.subtitle; color: "#b7bcba"; font.family: "Helvetica Neue"; font.pixelSize: 14 }

    Canvas {
        id: canvas
        anchors.left: parent.left; anchors.right: parent.right
        anchors.top: parent.top; anchors.bottom: parent.bottom
        anchors.leftMargin: 22; anchors.rightMargin: 22
        anchors.topMargin: 48; anchors.bottomMargin: 12
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Connections { target: backend; function onStateChanged(){ canvas.requestPaint() } function onConfigChanged(){ canvas.requestPaint() } }

        function xFor(v) {
            var span = Math.max(0.001, root.farLimit-root.nearLimit)
            return 76 + (Math.max(root.nearLimit, Math.min(root.farLimit, v))-root.nearLimit)/span*(width-152)
        }
        function cableY(xn) {
            if (!root.sideView) return height*0.35
            var d = Math.abs(xn-0.5)*2
            return height*(0.49-0.13*d)
        }
        function tower(c, x, baseY) {
            c.strokeStyle="#d7dad8"; c.lineWidth=1.1; c.setLineDash([])
            c.beginPath()
            c.moveTo(x-14,baseY); c.lineTo(x,baseY-55); c.lineTo(x+14,baseY)
            c.moveTo(x-20,baseY); c.lineTo(x+20,baseY)
            c.moveTo(x-10,baseY-14); c.lineTo(x+10,baseY-14)
            c.moveTo(x-7,baseY-29); c.lineTo(x+7,baseY-29)
            c.moveTo(x-3,baseY-44); c.lineTo(x+3,baseY-44)
            c.moveTo(x-11,baseY-14); c.lineTo(x+5,baseY-29)
            c.moveTo(x+11,baseY-14); c.lineTo(x-5,baseY-29)
            c.stroke()
        }
        function rampWedge(c, xa, xb, leftSide, base) {
            c.fillStyle="#23292c"; c.strokeStyle="#5f686c"; c.setLineDash([5,5]);
            c.beginPath()
            if (leftSide) { c.moveTo(xa,base+5); c.lineTo(xa,height-10); c.lineTo(xb,height-10) }
            else { c.moveTo(xb,base+5); c.lineTo(xb,height-10); c.lineTo(xa,height-10) }
            c.closePath(); c.fill(); c.stroke(); c.setLineDash([])
        }

        onPaint: {
            var c=getContext("2d"); c.reset(); c.clearRect(0,0,width,height)
            var left=76, right=width-76, base=height*0.35
            var span=Math.max(0.001,root.farLimit-root.nearLimit)
            var nr=xFor(root.nearLimit+Math.max(0,Math.min(span,root.nearRamp)))
            var fr=xFor(root.farLimit-Math.max(0,Math.min(span,root.farRamp)))
            rampWedge(c,left,nr,true,base); rampWedge(c,fr,right,false,base)

            c.strokeStyle="#9aa1a0"; c.lineWidth=1; c.setLineDash([5,5])
            c.beginPath(); c.moveTo(left,18); c.lineTo(left,height-8); c.moveTo(right,18); c.lineTo(right,height-8); c.stroke(); c.setLineDash([])
            c.fillStyle="#e7e9e8"; c.font="12px Helvetica Neue"; c.textAlign="center"
            c.fillText("NEAR LIMIT",left,14); c.fillText("FAR LIMIT",right,14)
            c.font="11px Helvetica Neue"; c.fillText("NEAR",20,46); c.fillText("FAR",width-20,46)
            tower(c,20,height-8); tower(c,width-20,height-8)

            c.strokeStyle="#bfc3c1"; c.lineWidth=1.15; c.beginPath()
            for(var i=0;i<=120;i++) {
                var t=i/120, x=left+t*(right-left), y=root.sideView?cableY(t):base
                if(i===0)c.moveTo(x,y); else c.lineTo(x,y)
            }
            c.stroke()

            // Simple fixed visual camera guide only. No Wide/Tele/Narrow FOV values.
            var sx=xFor(root.currentPosition), st=(sx-left)/(right-left), sy=root.sideView?cableY(st):base
            c.strokeStyle="#596267"; c.lineWidth=1; c.setLineDash([4,5]); c.beginPath()
            c.moveTo(sx,sy+8); c.lineTo(Math.max(left,sx-520),height-10)
            c.moveTo(sx,sy+8); c.lineTo(Math.min(right,sx+520),height-10); c.stroke(); c.setLineDash([])

            for(var p=0;p<root.presets.length;p++) {
                var item=root.presets[p]
                if(!item || !item.visible || !item.set) continue
                var px=xFor(item.position), pt=(px-left)/(right-left), py=root.sideView?cableY(pt):base
                c.strokeStyle="#dfe3e1"; c.fillStyle="#dfe3e1"; c.lineWidth=1
                c.beginPath(); c.arc(px,py,4,0,Math.PI*2); c.stroke()
                c.font="12px Helvetica Neue"; c.textAlign="center"; c.fillText("P"+(p+1),px,py-15)
            }

            var rx=xFor(root.refPoint), rt=(rx-left)/(right-left), ry=root.sideView?cableY(rt):base
            c.fillStyle=root.accent; c.beginPath(); c.moveTo(rx,ry-5);c.lineTo(rx+5,ry);c.lineTo(rx,ry+5);c.lineTo(rx-5,ry);c.closePath();c.fill()
            c.font="12px Helvetica Neue"; c.textAlign="center"; c.fillText("REF",rx,ry-16)

            // Clamp the skate label away from the endpoint text when the skate is at a limit.
            var skateLabelX=Math.max(left+28,Math.min(right-28,sx))
            c.fillStyle=root.accent; c.strokeStyle=root.accent; c.font="13px Helvetica Neue"; c.textAlign="center"
            c.fillText("SKATE",skateLabelX,sy-35)
            c.beginPath(); c.moveTo(sx-9,sy-28);c.lineTo(sx+9,sy-28);c.lineTo(sx,sy-10);c.closePath();c.fill()
            c.strokeStyle="#e4e7e5"; c.strokeRect(sx-8,sy+7,16,13); c.strokeRect(sx-11,sy+10,3,7); c.strokeRect(sx+8,sy+10,3,7)
        }
    }
}
