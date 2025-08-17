"""Real-time Flask visualization of (merged) RealSense point cloud.

Features:
 - Background capture thread pulls latest point cloud from MultiRealSense.
 - Flask endpoint '/' serves a page with Plotly 3D scatter updating every N ms via fetch.
 - Endpoint '/pointcloud' returns JSON of x,y,z (downsampled) for latest frame.

Usage (single cam):
    python realtime_flask.py

Usage (dual cam merged):
    python realtime_flask.py --dual

Options:
    --interval  (ms between browser updates, default 500)
    --max-points (limit points sent to browser, default 10000)
    --colorize {depth,height,xyz,rgb}

Note: This is a simple polling approach. For lower latency, consider WebSocket (Flask-SocketIO) or SSE.
"""

import argparse
import threading
import time
import numpy as np
from flask import Flask, jsonify, render_template_string
from multi_realsense_pro import MultiRealSense

app = Flask(__name__)

# Latest point clouds (front / right / merged)
latest_pcd = None  # legacy merged reference
latest_front = None
latest_right = None
lock = threading.Lock()
stop_flag = False


def capture_loop(multi: MultiRealSense, merged: bool, capture_interval_s: float):
    """Continuously pull latest point cloud and store a copy.

    Avoid ambiguous numpy truth-value; explicitly check None / size.
    capture_interval_s controls acquisition throttling (independent of browser poll).
    """
    global latest_pcd, latest_front, latest_right, stop_flag
    while not stop_flag:
        try:
            data = multi()
            pcd = None
            front = data.get('front_point_cloud')
            right = data.get('right_point_cloud')
            with lock:
                if isinstance(front, np.ndarray) and front.size > 0:
                    latest_front = front.copy()
                if isinstance(right, np.ndarray) and right.size > 0:
                    latest_right = right.copy()
                # Provide merged fallback
                if merged and latest_front is not None and latest_right is not None:
                    latest_pcd = np.vstack([latest_front, latest_right])
                else:
                    # Single-camera (or only one side available) fallback without ambiguous numpy truth-value
                    if latest_front is not None:
                        latest_pcd = latest_front
                    elif latest_right is not None:
                        latest_pcd = latest_right
                    else:
                        latest_pcd = None
        except Exception as e:
            # Log once per loop iteration; keep running
            print(f"[capture_loop] error: {e}")
            time.sleep(0.2)
        time.sleep(capture_interval_s)


def make_color(scale: np.ndarray, cmap_name: str):
    try:
        import matplotlib.cm as cm
        cmap = cm.get_cmap(cmap_name)
        cols = (cmap(scale)[:, :3] * 255).astype(np.uint8)
        return [f"rgb({r},{g},{b})" for r, g, b in cols]
    except Exception:
        # fallback grayscale
        gs = (scale * 255).astype(np.uint8)
        return [f"rgb({g},{g},{g})" for g in gs]


@app.route('/')
def index():
    return render_template_string(
        """
<!DOCTYPE html>
<html>
<head>
  <meta charset='utf-8'/>
  <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
  <title>Real-time Point Cloud</title>
    <style>
        body{margin:0;font-family:Arial;}
        #pcd{width:100vw;height:100vh;}
        #toolbar{position:fixed;top:8px;left:8px;z-index:10;background:rgba(255,255,255,0.8);padding:6px 10px;border-radius:6px;box-shadow:0 2px 4px rgba(0,0,0,.15);}
        #toolbar button{margin-right:6px;}
        #status{font-size:12px;color:#333;}
    </style>
</head>
<body>
    <div id="toolbar">
        <button id="toggle">Pause</button>
        <button id="step" disabled>Step</button>
        <span id="status">Running</span>
    </div>
    {% if dual_mode and view_mode=='separate' %}
    <div style="display:flex;flex-direction:row;height:100vh;width:calc(100vw - 80px);margin-left:80px;">
        <div id="pcd_front" style="flex:1;height:100%;padding:4px 4px 4px 0;"></div>
        <div id="pcd_right" style="flex:1;height:100%;padding:4px;">
        </div>
    </div>
    {% else %}
        <div id="pcd"></div>
    {% endif %}
  <script>
    let first=true;
        let paused=false;
        const toggleBtn=document.getElementById('toggle');
        const stepBtn=document.getElementById('step');
        const statusSpan=document.getElementById('status');
        toggleBtn.onclick=()=>{paused=!paused;toggleBtn.textContent=paused?'Resume':'Pause';statusSpan.textContent=paused?'Paused':'Running';stepBtn.disabled=!paused;};
        stepBtn.onclick=()=>{if(paused){fetchFrame();}};
        window.addEventListener('keydown',e=>{if(e.code==='Space'){toggleBtn.click();}});

        async function fetchFrame(){
            try{
                const resp = await fetch('/pointcloud');
                if(!resp.ok) return;
                const data = await resp.json();
                                {% if dual_mode and view_mode=='separate' %}
                                const front = data.front || {x:[],y:[],z:[],c:[]};
                                const right = data.right || {x:[],y:[],z:[],c:[]};
                                if(first){
                                    Plotly.newPlot('pcd_front',[{x:front.x,y:front.y,z:front.z,mode:'markers',type:'scatter3d',marker:{size:2,color:front.c,opacity:1}}],{margin:{l:0,r:0,t:0,b:0},title:'Front'});
                                    Plotly.newPlot('pcd_right',[{x:right.x,y:right.y,z:right.z,mode:'markers',type:'scatter3d',marker:{size:2,color:right.c,opacity:1}}],{margin:{l:0,r:0,t:0,b:0},title:'Right'});
                                    first=false;
                                }else{
                                    Plotly.update('pcd_front',{x:[front.x],y:[front.y],z:[front.z],'marker.color':[front.c]});
                                    Plotly.update('pcd_right',{x:[right.x],y:[right.y],z:[right.z],'marker.color':[right.c]});
                                }
                                {% else %}
                                if(first){
                                    Plotly.newPlot('pcd',[{x:data.x,y:data.y,z:data.z,mode:'markers',type:'scatter3d',
                                        marker:{size:2,color:data.c,opacity:1}}],{margin:{l:0,r:0,t:0,b:0}});
                                    first=false;
                                }else{
                                    Plotly.update('pcd',{x:[data.x],y:[data.y],z:[data.z], 'marker.color':[data.c]});
                                }
                                {% endif %}
            }catch(e){console.log(e);}
        }
    async function update(){
            if(!paused){
                await fetchFrame();
            }
    }
    setInterval(update, {{ interval }});
    update();
  </script>
</body>
</html>
        """,
    interval=app.config['UPDATE_INTERVAL_MS'],
    dual_mode=app.config['DUAL_MODE'],
    view_mode=app.config['VIEW_MODE']
    )


def _apply_orientation(x,y,z, mode:str):
    # mode options: default, swap_yz, y_up, camera_to_zup
    if mode == 'swap_yz':
        return x, z, y
    if mode == 'y_up':  # flip original y (camera y down) so y becomes up
        return x, -y, z
    if mode == 'camera_to_zup':
        # RealSense camera coords: x=right, y=down, z=forward
        # Convert to z-up right-handed: Xw= z, Yw= x, Zw= -y
        return z, x, -y
    return x,y,z

@app.route('/pointcloud')
def pointcloud_endpoint():
    def _build_json(pcd, appcfg):
        if pcd is None or pcd.size == 0:
            return dict(x=[], y=[], z=[], c=[])
        x = pcd[:,0]; y = pcd[:,1]; z = pcd[:,2]
        x,y,z = _apply_orientation(x,y,z, appcfg['ORIENT_MODE'])
        max_points = appcfg['MAX_POINTS']
        if x.shape[0] > max_points:
            idx = np.random.choice(x.shape[0], max_points, replace=False)
        else:
            idx = None
        mode = appcfg['COLORIZE_MODE']
        rgb = pcd[:,3:6]
        if mode in ('depth','z'):
            scalar = z if idx is None else z[idx]
        elif mode=='height':
            scalar = y if idx is None else y[idx]
        elif mode=='xyz':
            use = pcd if idx is None else pcd[idx]
            mn = np.min(use[:,:3], axis=0); mx = np.max(use[:,:3], axis=0)
            rng = (mx-mn)+1e-8
            norm = (use[:,:3]-mn)/rng
            cols = (norm*255).astype(int)
            return dict(x=(x if idx is None else x[idx]).tolist(),
                        y=(y if idx is None else y[idx]).tolist(),
                        z=(z if idx is None else z[idx]).tolist(),
                        c=[f"rgb({r},{g},{b})" for r,g,b in cols])
        else:
            use_rgb = rgb if idx is None else rgb[idx]
            return dict(x=(x if idx is None else x[idx]).tolist(),
                        y=(y if idx is None else y[idx]).tolist(),
                        z=(z if idx is None else z[idx]).tolist(),
                        c=[f"rgb({int(r)},{int(g)},{int(b)})" for r,g,b in use_rgb])
        vmin, vmax = float(scalar.min()), float(scalar.max())
        scale = np.zeros_like(scalar) if vmax-vmin < 1e-6 else (scalar - vmin)/(vmax-vmin)
        colors = make_color(scale, 'turbo')
        return dict(x=(x if idx is None else x[idx]).tolist(),
                    y=(y if idx is None else y[idx]).tolist(),
                    z=(z if idx is None else z[idx]).tolist(),
                    c=colors)
    with lock:
        merged = None if latest_pcd is None else latest_pcd.copy()
        front = None if latest_front is None else latest_front.copy()
        right = None if latest_right is None else latest_right.copy()
    # separate output for dual separate mode
    if app.config['DUAL_MODE'] and app.config['VIEW_MODE']=='separate':
        # Pass app.config (a dict-like mapping) rather than the Flask app object itself
        return jsonify(front=_build_json(front, app.config), right=_build_json(right, app.config))
    pcd = merged
    if pcd is None:
        return jsonify(x=[], y=[], z=[], c=[])

    # pcd columns: x,y,z,r,g,b
    x = pcd[:, 0]
    y = pcd[:, 1]
    z = pcd[:, 2]
    x,y,z = _apply_orientation(x,y,z, app.config['ORIENT_MODE'])

    # Downsample by random choice if too many points
    max_points = app.config['MAX_POINTS']
    if x.shape[0] > max_points:
        idx = np.random.choice(x.shape[0], max_points, replace=False)
        x, y, z, rgb = x[idx], y[idx], z[idx], pcd[idx, 3:6]
    else:
        rgb = pcd[:, 3:6]

    mode = app.config['COLORIZE_MODE']
    if mode == 'depth' or mode == 'z':
        v = z
    elif mode == 'height':
        v = y
    elif mode == 'xyz':
        mn = np.min(pcd[:, :3], axis=0)
        mx = np.max(pcd[:, :3], axis=0)
        rng = (mx - mn) + 1e-8
        norm = (pcd[:, :3] - mn) / rng
        cols = (norm * 255).astype(int)
        if x.shape[0] > max_points and cols.shape[0] > max_points:
            cols = cols[idx]
        c = [f"rgb({r},{g},{b})" for r, g, b in cols]
        return jsonify(x=x.tolist(), y=y.tolist(), z=z.tolist(), c=c)
    else:  # rgb
        cols = rgb.astype(int)
        c = [f"rgb({r},{g},{b})" for r, g, b in cols]
        return jsonify(x=x.tolist(), y=y.tolist(), z=z.tolist(), c=c)

    # scalar based colormap
    vmin, vmax = float(v.min()), float(v.max())
    if vmax - vmin < 1e-6:
        scale = np.zeros_like(v)
    else:
        scale = (v - vmin) / (vmax - vmin)
    if x.shape[0] > max_points and scale.shape[0] > max_points:
        scale = scale[idx]
    c = make_color(scale, 'turbo')
    return jsonify(x=x.tolist(), y=y.tolist(), z=z.tolist(), c=c)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dual', action='store_true', help='Use two cameras merged')
    parser.add_argument('--interval', type=int, default=500, help='Browser update interval ms')
    parser.add_argument('--max-points', type=int, default=10000, help='Max points to send per frame')
    parser.add_argument('--colorize', type=str, default='depth', help='rgb|depth|height|xyz')
    parser.add_argument('--orient', type=str, default='default', help='default|swap_yz|y_up|camera_to_zup')
    parser.add_argument('--capture-interval', type=int, default=100, help='Capture thread interval (ms)')
    parser.add_argument('--view', type=str, default='merged', help='merged|separate (dual only)')
    args = parser.parse_args()

    multi = MultiRealSense(use_front_cam=True, use_right_cam=args.dual,
                           apply_rotations=False, apply_crop=False,
                           debug_pointcloud=False, colorize_mode=args.colorize)

    app.config['UPDATE_INTERVAL_MS'] = args.interval
    app.config['MAX_POINTS'] = args.max_points
    app.config['COLORIZE_MODE'] = args.colorize.lower()
    app.config['ORIENT_MODE'] = args.orient.lower()
    app.config['DUAL_MODE'] = args.dual
    app.config['VIEW_MODE'] = args.view.lower()

    t = threading.Thread(
        target=capture_loop,
        args=(multi, args.dual, max(1, args.capture_interval) / 1000.0),
        daemon=True,
    )
    t.start()
    try:
        app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
    finally:
        global stop_flag
        stop_flag = True
        multi.finalize()


if __name__ == '__main__':
    main()
