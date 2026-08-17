import QtQuick 2.15

Item {
    id: root

    property string title: "Top View"
    property string subtitle: "X (Tracking) / Z (Offset)"
    property bool sideView: false

    // One canonical calculated cable profile is supplied by the Python engine
    // and is used on BOTH Run and Free-D.  The only difference between pages
    // is which markers are drawn over that same profile.
    property var cableProfile: []
    property var geometryPoints: []
    property var presets: []
    property bool showGeometryPoints: false
    property bool showPresets: true
    property bool showSkate: true
    property bool showReference: true

    // Run positions are relative to Near.  Free-D geometry uses the same X span.
    property real currentPosition: 0
    property real refPoint: 0
    property real nearLimit: 0
    property real farLimit: 100
    property real nearRamp: 0
    property real farRamp: 0
    property color accent: "#72ed21"
    property color headingColor: "#26d5ff"
    property color subheadingColor: headingColor

    // Repaint from the component's own bound properties instead of reaching
    // out to the Python context property from inside this reusable component.
    // This keeps qmllint fully qualified and also guarantees that both Run and
    // Free-D repaint whenever their shared calculated profile or overlays change.
    onCableProfileChanged: canvas.requestPaint()
    onGeometryPointsChanged: canvas.requestPaint()
    onPresetsChanged: canvas.requestPaint()
    onShowGeometryPointsChanged: canvas.requestPaint()
    onShowPresetsChanged: canvas.requestPaint()
    onShowSkateChanged: canvas.requestPaint()
    onShowReferenceChanged: canvas.requestPaint()
    onCurrentPositionChanged: canvas.requestPaint()
    onRefPointChanged: canvas.requestPaint()
    onNearLimitChanged: canvas.requestPaint()
    onFarLimitChanged: canvas.requestPaint()
    onNearRampChanged: canvas.requestPaint()
    onFarRampChanged: canvas.requestPaint()
    onSideViewChanged: canvas.requestPaint()

    Text {
        x: 26; y: 14
        text: root.title
        color: root.headingColor
        font.family: "Helvetica Neue"
        font.pixelSize: 20
        font.weight: Font.Medium
    }
    Text {
        x: 137; y: 18
        text: root.subtitle
        color: root.subheadingColor
        font.family: "Helvetica Neue"
        font.pixelSize: 14
    }

    Canvas {
        id: canvas
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.leftMargin: 22
        anchors.rightMargin: 22
        anchors.topMargin: 48
        anchors.bottomMargin: 12

        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        function profileFirstX() {
            if (root.cableProfile && root.cableProfile.length > 1)
                return Number(root.cableProfile[0].x)
            return Number(root.nearLimit)
        }
        function profileLastX() {
            if (root.cableProfile && root.cableProfile.length > 1)
                return Number(root.cableProfile[root.cableProfile.length-1].x)
            return Number(root.farLimit)
        }
        function domainMin() {
            var a = profileFirstX()
            var b = profileLastX()
            return Math.min(a, b)
        }
        function domainMax() {
            var a = profileFirstX()
            var b = profileLastX()
            return Math.max(a, b)
        }
        function xFor(v, left, right) {
            var lo = domainMin(), hi = domainMax()
            var span = Math.max(0.001, hi-lo)
            var q = Math.max(lo, Math.min(hi, Number(v)))
            return left + (q-lo)/span*(right-left)
        }
        function profileValue(xv, key) {
            var list = root.cableProfile
            if (!list || list.length < 1)
                return 0
            var x = Number(xv)
            if (x <= Number(list[0].x)) return Number(list[0][key])
            var last = list[list.length-1]
            if (x >= Number(last.x)) return Number(last[key])
            for (var i=0; i<list.length-1; ++i) {
                var a=list[i], b=list[i+1]
                var ax=Number(a.x), bx=Number(b.x)
                if (ax <= x && x <= bx) {
                    var t=(x-ax)/Math.max(0.000001,bx-ax)
                    return Number(a[key]) + (Number(b[key])-Number(a[key]))*t
                }
            }
            return Number(last[key])
        }
        function geometryZ(index) {
            var gp=root.geometryPoints
            if (!gp || gp.length<1) return 0
            var p=gp[index]
            if (p && p.z !== null && p.z !== undefined && !isNaN(Number(p.z)))
                return Number(p.z)
            return profileValue(Number(p.x), "z")
        }
        function verticalRange(key) {
            var vals=[]
            var list=root.cableProfile
            if (list) {
                for(var i=0;i<list.length;i++) vals.push(Number(list[i][key]))
            }
            if (root.showGeometryPoints && root.geometryPoints) {
                for(var j=0;j<root.geometryPoints.length;j++) {
                    vals.push(root.sideView ? Number(root.geometryPoints[j].y) : geometryZ(j))
                }
            }
            if(vals.length===0) vals=[0]
            var lo=Math.min.apply(Math,vals), hi=Math.max.apply(Math,vals)
            if(!isFinite(lo) || !isFinite(hi)){lo=-1;hi=1}
            var span=hi-lo
            if(span<0.25){lo-=1;hi+=1;span=hi-lo}
            var pad=Math.max(0.20,span*0.18)
            return {lo:lo-pad, hi:hi+pad}
        }
        function yFor(value, vr, top, bottom) {
            return bottom - (Number(value)-vr.lo)/Math.max(0.000001,vr.hi-vr.lo)*(bottom-top)
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
        function rampWedge(c, endpointX, boundaryX, endpointY, leftSide, bottom) {
            if (Math.abs(boundaryX-endpointX) < 1) return
            c.fillStyle="#23292c"
            c.strokeStyle="#5f686c"
            c.lineWidth=1
            c.setLineDash([5,5])
            c.beginPath()
            c.moveTo(endpointX,endpointY+4)
            c.lineTo(endpointX,bottom)
            c.lineTo(boundaryX,bottom)
            c.closePath()
            c.fill(); c.stroke(); c.setLineDash([])
        }

        onPaint: {
            var c=getContext("2d")
            c.reset(); c.clearRect(0,0,width,height)

            var left=76, right=width-76
            var graphTop=30, graphBottom=height-16
            var key=root.sideView ? "y" : "z"
            var vr=verticalRange(key)
            var lo=domainMin(), hi=domainMax(), span=Math.max(0.001,hi-lo)

            function yy(xv) { return yFor(profileValue(xv,key),vr,graphTop+20,graphBottom-18) }
            var nearY=yy(lo), farY=yy(hi)

            // Unlabelled ramping zones: same geometry on Run and Free-D.
            var nrX=xFor(lo+Math.max(0,Math.min(span,root.nearRamp)),left,right)
            var frX=xFor(hi-Math.max(0,Math.min(span,root.farRamp)),left,right)
            rampWedge(c,left,nrX,nearY,true,graphBottom)
            rampWedge(c,right,frX,farY,false,graphBottom)

            // Limits and towers.
            c.strokeStyle="#9aa1a0"; c.lineWidth=1; c.setLineDash([5,5])
            c.beginPath(); c.moveTo(left,18); c.lineTo(left,graphBottom); c.moveTo(right,18); c.lineTo(right,graphBottom); c.stroke(); c.setLineDash([])
            c.fillStyle="#e7e9e8"; c.font="12px Helvetica Neue"; c.textAlign="center"
            c.fillText("NEAR LIMIT",left,14); c.fillText("FAR LIMIT",right,14)
            c.font="11px Helvetica Neue"; c.fillText("NEAR",20,46); c.fillText("FAR",width-20,46)
            tower(c,20,graphBottom); tower(c,width-20,graphBottom)

            // Canonical calculated cable line. No camera guide lines.
            c.strokeStyle="#c4c8c6"; c.lineWidth=1.25; c.setLineDash([])
            c.beginPath()
            if(root.cableProfile && root.cableProfile.length>1) {
                for(var i=0;i<root.cableProfile.length;i++) {
                    var cp=root.cableProfile[i]
                    var cx=xFor(Number(cp.x),left,right)
                    var cy=yFor(Number(cp[key]),vr,graphTop+20,graphBottom-18)
                    if(i===0)c.moveTo(cx,cy);else c.lineTo(cx,cy)
                }
            } else {
                c.moveTo(left,nearY); c.lineTo(right,farY)
            }
            c.stroke()

            // Free-D page: show the five operator-entered geometry points. The
            // cable itself remains the calculated smooth/sagged profile above.
            if(root.showGeometryPoints && root.geometryPoints) {
                for(var g=0;g<root.geometryPoints.length;g++) {
                    var gp=root.geometryPoints[g]
                    var gx=xFor(Number(gp.x),left,right)
                    var gv=root.sideView ? Number(gp.y) : geometryZ(g)
                    var gy=yFor(gv,vr,graphTop+20,graphBottom-18)
                    c.fillStyle="#f1f3f2"; c.strokeStyle="#f1f3f2"
                    c.beginPath(); c.arc(gx,gy,4,0,Math.PI*2); c.fill()
                    c.font="11px Helvetica Neue"; c.textAlign="center"
                    c.fillText("P"+(g+1),gx,Math.min(graphBottom-2,gy+19))
                }
            }

            // Run page: saved preset markers are plotted on the SAME calculated
            // cable profile as the Free-D page.
            if(root.showPresets && root.presets) {
                for(var p=0;p<root.presets.length;p++) {
                    var item=root.presets[p]
                    if(!item || !item.visible || !item.set) continue
                    var px=xFor(Number(item.position),left,right)
                    var py=yy(Number(item.position))
                    c.strokeStyle="#dfe3e1"; c.fillStyle="#dfe3e1"; c.lineWidth=1
                    c.beginPath(); c.arc(px,py,4,0,Math.PI*2); c.stroke()
                    c.font="12px Helvetica Neue"; c.textAlign="center"
                    c.fillText("P"+(p+1),px,py-15)
                }
            }

            if(root.showReference) {
                var rx=xFor(root.refPoint,left,right), ry=yy(root.refPoint)
                c.fillStyle=root.accent
                c.beginPath(); c.moveTo(rx,ry-5);c.lineTo(rx+5,ry);c.lineTo(rx,ry+5);c.lineTo(rx-5,ry);c.closePath();c.fill()
                c.font="12px Helvetica Neue"; c.textAlign="center"; c.fillText("REF",rx,ry-16)
            }

            if(root.showSkate) {
                var sx=xFor(root.currentPosition,left,right), sy=yy(root.currentPosition)
                // The moving green arrow and camera/skate icon are deliberately
                // self-explanatory; no SKATE text is drawn, avoiding collisions
                // with the Near/Far Limit labels at either endpoint.
                c.fillStyle=root.accent; c.strokeStyle=root.accent
                c.beginPath(); c.moveTo(sx-9,sy-28);c.lineTo(sx+9,sy-28);c.lineTo(sx,sy-10);c.closePath();c.fill()
                c.strokeStyle="#e4e7e5"; c.strokeRect(sx-8,sy+7,16,13); c.strokeRect(sx-11,sy+10,3,7); c.strokeRect(sx+8,sy+10,3,7)
            }
        }
    }
}
