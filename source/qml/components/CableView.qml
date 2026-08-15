import QtQuick

Rectangle {
    id: root
    property bool sideView: false
    property var snapshot: ({})
    color: "#09131e"
    radius: 9
    border.width: 1
    border.color: "#293b49"

    function n(v, d) { var x=Number(v); return isNaN(x) ? d : x }

    Text {
        id: heading
        x: 20; y: 12
        text: root.sideView ? "Side View" : "Top View"
        color: "#f3f6f9"
        font.family: Qt.platform.os === "osx" ? "SF Pro Display" : "Segoe UI"
        font.pixelSize: 18
        font.weight: Font.DemiBold
    }
    Text {
        anchors.left: heading.right
        anchors.leftMargin: 12
        anchors.baseline: heading.baseline
        text: root.sideView ? "X (Tracking) / Y (Sag)" : "X (Tracking) / Z (Offset)"
        color: "#8796a4"
        font.family: Qt.platform.os === "osx" ? "SF Pro Text" : "Segoe UI"
        font.pixelSize: 14
    }

    Canvas {
        id: canvas
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.margins: 10
        anchors.topMargin: 38
        antialiasing: true

        function px(x, x0, x1, span) { return x0 + Math.max(0, Math.min(1, x/span))*(x1-x0) }
        function lineYTop(x, x0, x1, z0, z1) {
            var t=(x-x0)/(x1-x0); return z0 + (z1-z0)*t
        }
        function tower(ctx, x, y, flip) {
            var h=55, w=23
            ctx.strokeStyle="#cbd6de"; ctx.lineWidth=1.3
            ctx.beginPath(); ctx.moveTo(x,y); ctx.lineTo(x-w/2,y+h); ctx.lineTo(x+w/2,y+h); ctx.closePath(); ctx.stroke()
            ctx.beginPath(); ctx.moveTo(x-w/2,y+h); ctx.lineTo(x+7,y+18); ctx.lineTo(x+w/2,y+h); ctx.moveTo(x+w/2,y+h); ctx.lineTo(x-7,y+18); ctx.stroke()
            ctx.beginPath(); ctx.moveTo(x-w/2+3,y+h-14); ctx.lineTo(x+w/2-3,y+h-14); ctx.stroke()
        }
        function label(ctx, text, x, y, color, align, size, bold) {
            ctx.fillStyle=color; ctx.textAlign=align || "center"; ctx.textBaseline="middle"
            ctx.font=(bold ? "600 " : "") + (size || 12) + "px " + (Qt.platform.os === "osx" ? "Arial" : "Segoe UI")
            ctx.fillText(text,x,y)
        }
        function paintAll() {
            var ctx=getContext("2d"); ctx.reset(); ctx.clearRect(0,0,width,height)
            var r=(root.snapshot && root.snapshot.run) ? root.snapshot.run : {}
            var span=Math.max(0.001,root.n(r.span,100)); var x0=62, x1=width-62
            var chartTop=20, chartBottom=height-34, mid=(chartTop+chartBottom)/2
            var z0=root.n(r.zNear,0), z1=root.n(r.zFar,0)
            var nearRamp=Math.max(0,root.n(r.nearRamp,0)), farRamp=Math.max(0,root.n(r.farRamp,0))
            var skate=Math.max(0,Math.min(span,root.n(r.position,0)))

            // subtle horizontal baseline under the cable, as in the approved render
            ctx.strokeStyle="#1b2b38"; ctx.lineWidth=1
            ctx.beginPath(); ctx.moveTo(x0,chartBottom-6); ctx.lineTo(x1,chartBottom-6); ctx.stroke()

            // ramp zones: understated translucent blue wedges/boxes below the cable
            var nr=px(Math.min(span,nearRamp),x0,x1,span)
            var fr=px(Math.max(0,span-farRamp),x0,x1,span)
            ctx.fillStyle="rgba(20,106,151,0.16)"; ctx.strokeStyle="#225f81"; ctx.lineWidth=1
            if (nr>x0+2) {
                ctx.beginPath(); ctx.moveTo(x0+20,chartBottom-7); ctx.lineTo(nr,chartBottom-7); ctx.lineTo(nr,chartBottom-48); ctx.lineTo(x0+70,chartBottom-48); ctx.closePath(); ctx.fill(); ctx.stroke()
            }
            if (fr<x1-2) {
                ctx.beginPath(); ctx.moveTo(fr,chartBottom-7); ctx.lineTo(x1-20,chartBottom-7); ctx.lineTo(x1-70,chartBottom-48); ctx.lineTo(fr,chartBottom-48); ctx.closePath(); ctx.fill(); ctx.stroke()
            }

            // cable path
            ctx.strokeStyle="#d8e0e6"; ctx.lineWidth=1.7; ctx.beginPath()
            var functionY=function(xm){return mid}
            if (!root.sideView) {
                var maxAbs=Math.max(1,Math.abs(z0),Math.abs(z1));
                var scale=Math.min(32,Math.max(7,22/maxAbs))
                functionY=function(xm){ return mid - (z0+(z1-z0)*(xm/span))*scale }
                ctx.moveTo(x0,functionY(0)); ctx.lineTo(x1,functionY(span)); ctx.stroke()
            } else {
                var samples=r.sideSamples || []
                var ymin=0, ymax=0
                for (var si=0;si<samples.length;si++){var yy=root.n(samples[si][1],0); ymin=Math.min(ymin,yy); ymax=Math.max(ymax,yy)}
                var yr=Math.max(0.5,ymax-ymin); var yp=yr*0.18; ymin-=yp; ymax+=yp
                functionY=function(xm){
                    if (!samples.length) return mid
                    var best=samples[0]
                    for (var k=1;k<samples.length;k++){ if (root.n(samples[k][0],0)>=xm){
                        var a=samples[k-1],b=samples[k], ax=root.n(a[0],0),bx=root.n(b[0],0)
                        var tt=(xm-ax)/Math.max(0.0001,bx-ax); var yv=root.n(a[1],0)+(root.n(b[1],0)-root.n(a[1],0))*tt
                        return chartBottom-18-(yv-ymin)/(ymax-ymin)*(chartBottom-chartTop-46)
                    }}
                    var last=samples[samples.length-1]; return chartBottom-18-(root.n(last[1],0)-ymin)/(ymax-ymin)*(chartBottom-chartTop-46)
                }
                if(samples.length){ctx.moveTo(px(root.n(samples[0][0],0),x0,x1,span),functionY(root.n(samples[0][0],0)))
                    for(var sj=1;sj<samples.length;sj++){ctx.lineTo(px(root.n(samples[sj][0],0),x0,x1,span),functionY(root.n(samples[sj][0],0)))} ctx.stroke()}
            }

            // towers / end labels
            tower(ctx,x0-30,Math.max(6,functionY(0)-26),false); tower(ctx,x1+30,Math.max(6,functionY(span)-26),true)
            label(ctx,"NEAR",x0-30,8,"#28c2ff","center",12,true); label(ctx,"FAR",x1+30,8,"#28c2ff","center",12,true)
            label(ctx,"NEAR LIMIT",x0-30,chartBottom+10,"#28c2ff","center",11,false)
            label(ctx,"FAR LIMIT",x1+30,chartBottom+10,"#28c2ff","center",11,false)
            if(nearRamp>0.001) label(ctx,"RAMP UP ZONE",(x0+nr)/2,chartBottom+10,"#b9c5cd","center",11,false)
            if(farRamp>0.001) label(ctx,"RAMP DOWN ZONE",(fr+x1)/2,chartBottom+10,"#b9c5cd","center",11,false)

            // preset positions
            var presets=r.presets || []
            for(var i=0;i<presets.length;i++){
                var p=presets[i]; if(p.position===null || p.position===undefined || p.visible===false) continue
                var xm=root.n(p.position,-1); if(xm<0 || xm>span) continue
                var xp=px(xm,x0,x1,span), yp2=functionY(xm)
                ctx.fillStyle="#0f1720";ctx.strokeStyle="#e1e7eb";ctx.lineWidth=1.2;ctx.beginPath();ctx.arc(xp,yp2,5,0,Math.PI*2);ctx.fill();ctx.stroke()
                ctx.strokeStyle="#7d8993";ctx.beginPath();ctx.moveTo(xp,yp2-5);ctx.lineTo(xp,yp2-20);ctx.stroke()
                label(ctx,String(p.name||("P"+(i+1))),xp,yp2-29,"#e6ebef","center",12,false)
            }
            // reference marker
            var rx=Math.max(0,Math.min(span,root.n(r.reference,0))), rpx=px(rx,x0,x1,span), rpy=functionY(rx)
            ctx.fillStyle="#28bdf7";ctx.save();ctx.translate(rpx,rpy);ctx.rotate(Math.PI/4);ctx.fillRect(-5,-5,10,10);ctx.restore()
            label(ctx,"REF",rpx,rpy-28,"#2cc5ff","center",12,true)

            // skate + camera
            var sx=px(skate,x0,x1,span), sy=functionY(skate)
            ctx.fillStyle="#62db54";ctx.beginPath();ctx.moveTo(sx,sy+4);ctx.lineTo(sx-10,sy-17);ctx.lineTo(sx+10,sy-17);ctx.closePath();ctx.fill()
            label(ctx,"SKATE",sx,sy-31,"#66e05d","center",12,true)
            ctx.strokeStyle="#3195c7";ctx.setLineDash([5,5]);ctx.lineWidth=1
            ctx.beginPath();ctx.moveTo(sx,sy+5);ctx.lineTo(sx,chartBottom-20);ctx.stroke()
            // Camera field-of-view projection: deliberately light and unobtrusive,
            // matching the approved render rather than a heavy filled cone.
            ctx.beginPath();ctx.moveTo(sx,chartBottom-14);ctx.lineTo(x0+12,chartBottom-1);ctx.stroke()
            ctx.beginPath();ctx.moveTo(sx,chartBottom-14);ctx.lineTo(x1-12,chartBottom-1);ctx.stroke();ctx.setLineDash([])
            ctx.strokeStyle="#28bdf7";ctx.lineWidth=1;ctx.strokeRect(sx-8,chartBottom-19,16,10);ctx.strokeRect(sx-11,chartBottom-16,3,5)
            label(ctx,"CAMERA FOV",sx,chartBottom+2,"#2cc5ff","center",11,false)
        }
        onPaint: paintAll()
    }

    onSnapshotChanged: canvas.requestPaint()
    onWidthChanged: canvas.requestPaint()
    onHeightChanged: canvas.requestPaint()
}
