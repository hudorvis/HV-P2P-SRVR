import QtQuick 2.15

Item {
    id: root
    property string title: "Top View"
    property string subtitle: "X (Tracking) / Z (Offset)"
    property bool sideView: false
    property var geometryPoints: []
    property real nearRamp: 0
    property real farRamp: 0

    Text { x: 18; y: 12; text: root.title; color: "#f4f5f4"; font.family: "Helvetica Neue"; font.pixelSize: 18; font.weight: Font.Medium }
    Text { x: 112; y: 15; text: root.subtitle; color: "#b7bcba"; font.family: "Helvetica Neue"; font.pixelSize: 13 }

    Canvas {
        id: canvas
        anchors.fill: parent
        anchors.leftMargin: 18; anchors.rightMargin: 18; anchors.topMargin: 42; anchors.bottomMargin: 10
        onWidthChanged: requestPaint(); onHeightChanged: requestPaint()
        Connections { target: backend; function onConfigChanged(){ canvas.requestPaint() } function onStateChanged(){ canvas.requestPaint() } }

        function tower(c,x,b) {
            c.strokeStyle="#dadcdb";c.lineWidth=1;c.beginPath();c.moveTo(x-11,b);c.lineTo(x,b-46);c.lineTo(x+11,b);c.moveTo(x-16,b);c.lineTo(x+16,b);c.moveTo(x-8,b-13);c.lineTo(x+8,b-13);c.moveTo(x-5,b-26);c.lineTo(x+5,b-26);c.stroke()
        }
        onPaint: {
            var c=getContext("2d"); c.reset(); c.clearRect(0,0,width,height)
            if(!root.geometryPoints || root.geometryPoints.length<2) return
            var left=52, right=width-52, top=24, bottom=height-14
            var minX=Number(root.geometryPoints[0].x), maxX=Number(root.geometryPoints[root.geometryPoints.length-1].x)
            var span=Math.max(0.001,maxX-minX)
            function xp(v){return left+(Number(v)-minX)/span*(right-left)}
            var vals=[]
            for(var i=0;i<root.geometryPoints.length;i++) vals.push(root.sideView?Number(root.geometryPoints[i].y):Number(root.geometryPoints[i].z===null?0:root.geometryPoints[i].z))
            var minV=Math.min.apply(Math,vals), maxV=Math.max.apply(Math,vals)
            if(Math.abs(maxV-minV)<0.1){minV-=1;maxV+=1}
            function yp(v){return bottom-26-(Number(v)-minV)/(maxV-minV)*(bottom-top-45)}

            // Subtle Near/Far ramp zones from the same saved limit settings as
            // the Run page; no FOV value labels are involved.
            var nearEnd = xp(Math.min(maxX, minX + Math.max(0, root.nearRamp)))
            var farStart = xp(Math.max(minX, maxX - Math.max(0, root.farRamp)))
            var baseLineY = sideView ? yp(vals[0]) : yp(vals[0])
            c.fillStyle="#2a3033"; c.strokeStyle="#596166"; c.lineWidth=1; c.setLineDash([4,4])
            c.beginPath(); c.moveTo(left,baseLineY); c.lineTo(left,bottom-10); c.lineTo(nearEnd,bottom-10); c.closePath(); c.fill(); c.stroke()
            var farY = sideView ? yp(vals[vals.length-1]) : yp(vals[vals.length-1])
            c.beginPath(); c.moveTo(right,farY); c.lineTo(right,bottom-10); c.lineTo(farStart,bottom-10); c.closePath(); c.fill(); c.stroke(); c.setLineDash([])

            c.fillStyle="#e6e8e7"; c.font="11px Helvetica Neue"; c.textAlign="center"
            c.fillText("NEAR LIMIT",left,12);c.fillText("FAR LIMIT",right,12)
            tower(c,16,bottom);tower(c,width-16,bottom)
            c.strokeStyle="#c1c4c3";c.lineWidth=1.2;c.beginPath()
            for(var j=0;j<root.geometryPoints.length;j++){
                var p=root.geometryPoints[j], x=xp(p.x), v=root.sideView?Number(p.y):Number(p.z===null?0:p.z), y=yp(v)
                if(j===0)c.moveTo(x,y);else c.lineTo(x,y)
            }
            c.stroke()
            for(var k=0;k<root.geometryPoints.length;k++){
                var q=root.geometryPoints[k], qx=xp(q.x), qv=root.sideView?Number(q.y):Number(q.z===null?0:q.z), qy=yp(qv)
                c.fillStyle="#f2f3f2";c.beginPath();c.arc(qx,qy,4,0,Math.PI*2);c.fill()
                c.font="11px Helvetica Neue";c.fillText("P"+(k+1),qx,qy+19)
            }
        }
    }
}
