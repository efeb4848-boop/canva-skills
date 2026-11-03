"""
Alyans Dental – sinematik logo intro (Blender 5.2, Cycles)

Gereksinim: pip install bpy==5.2.*   (ya da Blender 5.2 içinden: blender -b -P scene.py -- ...)
Kullanım (bpy modülü ile):
    python scene.py --geo logo_geo.json --out frames/ [--res 1920x1080] [--samples 64]
                    [--frames 1-165] [--save intro.blend] [--no-render]

Zaman çizelgesi (30 fps):
    001-014  arka plan açılır, toz parçacıkları
    008-040  işaret derinlikten uçarak gelir (iniş: 38)
    034-058  "alyansdental" harfleri sırayla döner
    050-072  "ALYANS DİJİTAL DENTAL" açılır
    068-084  ışık süpürmesi  – "zım"
    078-092  yıldız parlaması
    110-118  vakum öncesi nefes
    116-133  vakum: her şey işaretin boşluğuna emilir
    134      KESME: gerilim fragmanı gibi direkt karanlık (trailer vuruşu)
    134-186  siyah – ses kuyruğu, ardından asıl içerik
"""
import bpy, bmesh, json, math, sys, os, random, argparse
from mathutils import Vector

ap = argparse.ArgumentParser()
ap.add_argument('--geo', required=True)
ap.add_argument('--out', default='frames')
ap.add_argument('--res', default='1920x1080')
ap.add_argument('--samples', type=int, default=64)
ap.add_argument('--frames', default=None)
ap.add_argument('--save', default=None)
ap.add_argument('--no-render', action='store_true')
ap.add_argument('--no-mblur', action='store_true')
ap.add_argument('--threads', type=int, default=0)
ap.add_argument('--step', default='1/0')
args = ap.parse_args(sys.argv[1:] if '--' not in sys.argv else sys.argv[sys.argv.index('--') + 1:])

FPS = 30
F_END = 186
T = dict(bg_in=(1, 14), mark_in=(8, 40), land=38, word_in=34, tag_in=(50, 72), shine=(68, 84), spark=(78, 92),
         breathe=(110, 118), vac=(116, 136), pop=136, cut=134)

# ------------------------------------------------------------------ reset scene
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 1, F_END

geo = json.load(open(args.geo))
vb = geo['viewbox']
S = 1 / 250.0
CX = vb[0] + vb[2] / 2
CY = vb[1] + vb[3] / 2


def to_b(p):
    return Vector(((p[0] - CX) * S, -(p[1] - CY) * S, 0.0))


def srgb(h):
    h = h.lstrip('#')
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c) + (1.0,)


# ------------------------------------------------------------------ animation helpers (Blender 5 layered actions)
from bpy_extras import anim_utils


def fcurves_of(idb):
    ad = idb.animation_data
    if ad is None or ad.action is None:
        return []
    cb = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
    return cb.fcurves if cb else []


def key(owner, path, frame, value, interp='BEZIER', easing='AUTO', idb=None, back=None):
    """Insert keyframe and set interpolation of the segment that starts at this key."""
    if isinstance(path, str) and path.startswith('['):
        owner[path[2:-2]] = value
    else:
        setattr(owner, path, value)
    owner.keyframe_insert(path, frame=frame)
    idb = idb or owner.id_data
    full = owner.path_from_id(path) if hasattr(owner, 'path_from_id') and owner != idb else path
    for fc in fcurves_of(idb):
        if fc.data_path == full:
            for kp in fc.keyframe_points:
                if abs(kp.co.x - frame) < 1e-3:
                    kp.interpolation = interp
                    kp.easing = easing
                    if back is not None:
                        kp.back = back


# ------------------------------------------------------------------ geometry
def make_logo_object(name, contours, extrude, bevel, res, max_edge, mat):
    pts = [to_b(p) for c in contours for seg in c for p in seg[1:]]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), 0))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), 0))
    centre = (lo + hi) / 2
    cu = bpy.data.curves.new(name + '_crv', 'CURVE')
    cu.dimensions = '2D'
    cu.fill_mode = 'BOTH'
    cu.extrude = extrude
    cu.bevel_depth = bevel
    cu.bevel_resolution = 3
    cu.resolution_u = res
    for c in contours:
        sp = cu.splines.new('BEZIER')
        n = len(c)
        sp.bezier_points.add(n - 1)
        for bp in sp.bezier_points:
            bp.handle_left_type = 'FREE'
            bp.handle_right_type = 'FREE'
        for i, seg in enumerate(c):
            p0 = to_b(seg[1]) - centre
            if seg[0] == 'L':
                p1 = to_b(seg[2]) - centre
                h_out, h_in = p0 + (p1 - p0) / 3, p1 - (p1 - p0) / 3
            else:
                h_out, h_in = to_b(seg[2]) - centre, to_b(seg[3]) - centre
            bp = sp.bezier_points[i]
            bp.co = p0
            bp.handle_right = h_out
            sp.bezier_points[(i + 1) % n].handle_left = h_in
        sp.use_cyclic_u = True
    tmp = bpy.data.objects.new(name + '_tmp', cu)
    sc.collection.objects.link(tmp)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    bpy.data.objects.remove(tmp)
    bpy.data.curves.remove(cu)
    # densify long edges so the vacuum deformation bends smoothly
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    if max_edge:
        for _ in range(8):
            long_e = [e for e in bm.edges if e.calc_length() > max_edge]
            if not long_e:
                break
            bmesh.ops.subdivide_edges(bm, edges=long_e, cuts=1, use_grid_fill=False)
            bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    for f in bm.faces:
        f.smooth = True
    for e in bm.edges:
        if e.is_manifold and e.calc_face_angle(0) > math.radians(32):
            e.smooth = False
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    sc.collection.objects.link(ob)
    ob.location = centre
    ob['reveal'] = 1.0
    ob['rest'] = list(centre)
    return ob


# ------------------------------------------------------------------ shading: shared shine (light sweep) group
shine = bpy.data.node_groups.new('ShineSweep', 'ShaderNodeTree')
shine.interface.new_socket('Band', in_out='OUTPUT', socket_type='NodeSocketFloat')
N = shine.nodes
L = shine.links
g_out = N.new('NodeGroupOutput')
geo_n = N.new('ShaderNodeNewGeometry')
dirv = N.new('ShaderNodeVectorMath'); dirv.operation = 'DOT_PRODUCT'
d = Vector((1.0, -0.62, 0.0)).normalized()
dirv.inputs[1].default_value = (d.x, d.y, 0.0)
L.new(geo_n.outputs['Position'], dirv.inputs[0])
sweep = N.new('ShaderNodeValue'); sweep.name = sweep.label = 'Sweep'
sub = N.new('ShaderNodeMath'); sub.operation = 'SUBTRACT'
L.new(dirv.outputs['Value'], sub.inputs[0]); L.new(sweep.outputs[0], sub.inputs[1])
div = N.new('ShaderNodeMath'); div.operation = 'DIVIDE'; div.inputs[1].default_value = 0.32
L.new(sub.outputs[0], div.inputs[0])
sq = N.new('ShaderNodeMath'); sq.operation = 'MULTIPLY'
L.new(div.outputs[0], sq.inputs[0]); L.new(div.outputs[0], sq.inputs[1])
neg = N.new('ShaderNodeMath'); neg.operation = 'MULTIPLY'; neg.inputs[1].default_value = -1.0
L.new(sq.outputs[0], neg.inputs[0])
ex = N.new('ShaderNodeMath'); ex.operation = 'EXPONENT'
L.new(neg.outputs[0], ex.inputs[0])
inten = N.new('ShaderNodeValue'); inten.name = inten.label = 'Intensity'
mul = N.new('ShaderNodeMath'); mul.operation = 'MULTIPLY'
L.new(ex.outputs[0], mul.inputs[0]); L.new(inten.outputs[0], mul.inputs[1])
L.new(mul.outputs[0], g_out.inputs[0])


def make_mat(name, color, rough, coat, shine_gain, alpha_attr=True, base_emit=0.0):
    m = bpy.data.materials.new(name)
    nt = m.node_tree
    p = nt.nodes['Principled BSDF']
    p.inputs['Base Color'].default_value = srgb(color)
    p.inputs['Roughness'].default_value = rough
    p.inputs['Coat Weight'].default_value = coat
    p.inputs['Coat Roughness'].default_value = 0.04
    p.inputs['Emission Color'].default_value = (1, 1, 1, 1)
    gi = nt.nodes.new('ShaderNodeGroup'); gi.node_tree = shine
    gm = nt.nodes.new('ShaderNodeMath'); gm.operation = 'MULTIPLY'; gm.inputs[1].default_value = shine_gain
    ga = nt.nodes.new('ShaderNodeMath'); ga.operation = 'ADD'; ga.inputs[1].default_value = base_emit
    nt.links.new(gi.outputs[0], gm.inputs[0]); nt.links.new(gm.outputs[0], ga.inputs[0])
    nt.links.new(ga.outputs[0], p.inputs['Emission Strength'])
    if alpha_attr:
        at = nt.nodes.new('ShaderNodeAttribute'); at.attribute_type = 'OBJECT'; at.attribute_name = 'reveal'
        nt.links.new(at.outputs['Fac'], p.inputs['Alpha'])
    return m


def emission_mat(name, color, strength, key_name=None):
    m = bpy.data.materials.new(name)
    nt = m.node_tree
    for n_ in list(nt.nodes):
        nt.nodes.remove(n_)
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    em = nt.nodes.new('ShaderNodeEmission')
    em.inputs['Color'].default_value = srgb(color)
    em.inputs['Strength'].default_value = strength
    tr = nt.nodes.new('ShaderNodeBsdfTransparent')
    add = nt.nodes.new('ShaderNodeAddShader')
    nt.links.new(em.outputs[0], add.inputs[0]); nt.links.new(tr.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs['Surface'])
    return m, em


MAT_MARK = make_mat('Isaret', geo['colors']['blue'], 0.28, 0.6, 7.0, alpha_attr=False)
MAT_WORD = make_mat('Yazi', '#FFFFFF', 0.28, 0.35, 4.0, base_emit=0.22)
MAT_TAG = make_mat('AltYazi', '#B9C3D6', 0.45, 0.0, 3.0, base_emit=0.12)

# ------------------------------------------------------------------ build logo
mark = make_logo_object('Isaret', geo['mark'], 0.09, 0.022, 24, 0.06, MAT_MARK)
letters = []
for i, g in enumerate(geo['word']):
    letters.append(make_logo_object(f'Harf_{i:02d}_{g["ch"]}', g['contours'], 0.05, 0.006, 10, 0.03, MAT_WORD))
tags = []
for i, g in enumerate(geo['tag']):
    tags.append(make_logo_object(f'Alt_{i:02d}', g['contours'], 0.02, 0.003, 6, None, MAT_TAG))

hole_c = to_b(geo['mark_hole_centroid'])
vac_center = bpy.data.objects.new('VakumMerkezi', None)
vac_center.empty_display_type = 'SPHERE'
vac_center.empty_display_size = 0.2
vac_center.location = (hole_c.x, hole_c.y, 0.05)
sc.collection.objects.link(vac_center)

# ------------------------------------------------------------------ vacuum geometry-nodes modifier
vac = bpy.data.node_groups.new('Vakum', 'GeometryNodeTree')
vac.interface.new_socket('Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
vac.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
VN, VL = vac.nodes, vac.links
gin = VN.new('NodeGroupInput'); gout = VN.new('NodeGroupOutput')
pos = VN.new('GeometryNodeInputPosition')
oi = VN.new('GeometryNodeObjectInfo'); oi.transform_space = 'RELATIVE'; oi.inputs['Object'].default_value = vac_center
prog = VN.new('ShaderNodeValue'); prog.name = prog.label = 'Progress'
breath = VN.new('ShaderNodeValue'); breath.name = breath.label = 'Breath'


def vm(op, a=None, b=None, name=None):
    n_ = VN.new('ShaderNodeVectorMath'); n_.operation = op
    if a is not None: VL.new(a, n_.inputs[0])
    if b is not None: VL.new(b, n_.inputs[1])
    return n_


def fm(op, a=None, b=None, av=None, bv=None, clamp=False):
    n_ = VN.new('ShaderNodeMath'); n_.operation = op; n_.use_clamp = clamp
    if a is not None: VL.new(a, n_.inputs[0])
    elif av is not None: n_.inputs[0].default_value = av
    if b is not None: VL.new(b, n_.inputs[1])
    elif bv is not None: n_.inputs[1].default_value = bv
    return n_


D = vm('SUBTRACT', oi.outputs['Location'], pos.outputs['Position'])          # vector to centre
dist = vm('LENGTH', D.outputs[0])
dn = fm('DIVIDE', dist.outputs['Value'], None, bv=5.2)
dnc = fm('MINIMUM', dn.outputs[0], None, bv=1.0)
SPREAD = 1.35
p1 = fm('MULTIPLY', prog.outputs[0], None, bv=1 + SPREAD)
p2 = fm('MULTIPLY', dnc.outputs[0], None, bv=SPREAD)
lp = fm('SUBTRACT', p1.outputs[0], p2.outputs[0], clamp=True)
f = fm('POWER', lp.outputs[0], None, bv=2.2)                                  # ease-in suction
# breath (anticipation): push slightly away from centre before suction
inv = fm('SUBTRACT', None, f.outputs[0], av=1.0)
br = fm('MULTIPLY', breath.outputs[0], inv.outputs[0])
fac = fm('SUBTRACT', f.outputs[0], br.outputs[0])
off = vm('SCALE', D.outputs[0]); VL.new(fac.outputs[0], off.inputs['Scale'])
newp = vm('ADD', pos.outputs['Position'], off.outputs[0])
rot = VN.new('ShaderNodeVectorRotate'); rot.rotation_type = 'Z_AXIS'
VL.new(newp.outputs[0], rot.inputs['Vector']); VL.new(oi.outputs['Location'], rot.inputs['Center'])
sw = fm('MULTIPLY', f.outputs[0], None, bv=-4.2)                             # swirl (radians)
VL.new(sw.outputs[0], rot.inputs['Angle'])
setp = VN.new('GeometryNodeSetPosition')
VL.new(gin.outputs[0], setp.inputs['Geometry']); VL.new(rot.outputs[0], setp.inputs['Position'])
VL.new(setp.outputs[0], gout.inputs[0])

prog.outputs[0].default_value = 0.0
breath.outputs[0].default_value = 0.0

for ob in [mark] + letters + tags:
    md = ob.modifiers.new('Vakum', 'NODES'); md.node_group = vac

# ------------------------------------------------------------------ dust particles (single mesh, also vacuumed)
random.seed(7)
bm = bmesh.new()
for i in range(130):
    r = random.uniform(0.010, 0.032)
    m_ = bmesh.ops.create_icosphere(bm, subdivisions=1, radius=r)
    c = Vector((random.uniform(-11, 11), random.uniform(-6.5, 6.5), random.uniform(-14, 19)))
    if abs(c.x) < 4.2 and abs(c.y) < 3.4 and c.z > -3:      # keep the hero area clear
        c.x += math.copysign(4.2, c.x if c.x else 1.0)
    bmesh.ops.translate(bm, verts=m_['verts'], vec=c)
dust_me = bpy.data.meshes.new('Toz')
bm.to_mesh(dust_me); bm.free()
dust_mat, dust_em = emission_mat('TozMat', '#A9BEFF', 5.0)
dust_me.materials.append(dust_mat)
dust = bpy.data.objects.new('Toz', dust_me)
sc.collection.objects.link(dust)
md = dust.modifiers.new('Vakum', 'NODES'); md.node_group = vac

# ------------------------------------------------------------------ backdrop
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0.6, -9))
back = bpy.context.active_object; back.name = 'ArkaPlan'; back.scale = (70, 40, 1)
bm_mat = bpy.data.materials.new('ArkaPlanMat'); nt = bm_mat.node_tree
for n_ in list(nt.nodes): nt.nodes.remove(n_)
out = nt.nodes.new('ShaderNodeOutputMaterial')
em = nt.nodes.new('ShaderNodeEmission')
tc = nt.nodes.new('ShaderNodeTexCoord')
mp = nt.nodes.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (70 / 13.0, 40 / 13.0, 1)
gr = nt.nodes.new('ShaderNodeTexGradient'); gr.gradient_type = 'SPHERICAL'
cr = nt.nodes.new('ShaderNodeValToRGB')
cr.color_ramp.interpolation = 'EASE'
cr.color_ramp.elements[0].position = 0.0; cr.color_ramp.elements[0].color = srgb('#010104')
cr.color_ramp.elements[1].position = 1.0; cr.color_ramp.elements[1].color = srgb('#45139A')
e2 = cr.color_ramp.elements.new(0.6); e2.color = srgb('#0D0830')
nt.links.new(tc.outputs['Object'], mp.inputs['Vector']); nt.links.new(mp.outputs[0], gr.inputs['Vector'])
nt.links.new(gr.outputs['Fac'], cr.inputs['Fac']); nt.links.new(cr.outputs['Color'], em.inputs['Color'])
nt.links.new(em.outputs[0], out.inputs['Surface'])
back.data.materials.append(bm_mat)
back_em = em

# ------------------------------------------------------------------ fx objects: sparkle, suction ring
def sphere(name, r, loc, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=24, ring_count=12, location=loc)
    o = bpy.context.active_object; o.name = name; o.data.materials.append(mat)
    for p in o.data.polygons: p.use_smooth = True
    return o


spark_mat, spark_em = emission_mat('YildizMat', '#FFFFFF', 0.0)
# sparkle at the right-hand tip of the mark (front face)
mk_pts = [to_b(p) for seg in geo['mark'][0] for p in seg[1:]]
tip = max(mk_pts, key=lambda v: v.x)
spark = sphere('Yildiz', 0.035, (tip.x - 0.18, tip.y, 0.16), spark_mat)


ring_in_mat, ring_in_em = emission_mat('HalkaIcMat', '#7FB2FF', 0.0)
bpy.ops.mesh.primitive_torus_add(major_radius=1.0, minor_radius=0.012, major_segments=128, minor_segments=8,
                                 location=vac_center.location)
ring_in = bpy.context.active_object; ring_in.name = 'HalkaIc'; ring_in.data.materials.append(ring_in_mat)
for o in (ring_in,):
    for p in o.data.polygons: p.use_smooth = True

# ------------------------------------------------------------------ lights
def area(name, loc, size, energy, color='#FFFFFF', size_y=None, target=(0, 0, 0)):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.energy = energy; ld.color = srgb(color)[:3]
    if size_y:
        ld.shape = 'RECTANGLE'; ld.size = size; ld.size_y = size_y
    else:
        ld.size = size
    o = bpy.data.objects.new(name, ld); sc.collection.objects.link(o)
    o.location = loc
    dvec = Vector(target) - Vector(loc)
    o.rotation_euler = dvec.to_track_quat('-Z', 'Y').to_euler()
    return o


area('Anahtar', (-7, 7, 13), 7, 3600)
area('Dolgu', (8, -3, 14), 10, 700, '#C9D8FF')
area('KenarSol', (-7, 2, -5), 3, 1800, '#6F7BFF')
area('KenarSag', (7, -1, -5), 3, 1800, '#38A8FF')
area('Ust', (0, 9, 4), 12, 600, '#FFFFFF', size_y=1.2)

world = bpy.data.worlds.new('Dunya'); sc.world = world
world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.002, 0.002, 0.004, 1)

# ------------------------------------------------------------------ camera
cam_d = bpy.data.cameras.new('Kamera'); cam_d.lens = 60
cam = bpy.data.objects.new('Kamera', cam_d); sc.collection.objects.link(cam); sc.camera = cam
focus = bpy.data.objects.new('Odak', None); focus.location = (0, 0, 0.1); sc.collection.objects.link(focus)
cam_d.dof.use_dof = True; cam_d.dof.focus_object = focus; cam_d.dof.aperture_fstop = 0.18
cam_d.dof.aperture_blades = 7; cam_d.dof.aperture_rotation = math.radians(12)

# ------------------------------------------------------------------ ANIMATION
# camera: slow push, then quick push during suction
key(cam, 'location', 1, Vector((0.35, 0.25, 30.5)), 'SINE', 'EASE_OUT')
key(cam, 'location', T['vac'][0], Vector((-0.1, 0.12, 27.6)), 'QUAD', 'EASE_IN')
key(cam, 'location', T['pop'], Vector((hole_c.x * 0.35, hole_c.y * 0.35, 25.4)), 'BEZIER')
key(cam, 'rotation_euler', 1, Vector((0.0, math.radians(0.6), math.radians(-0.8))), 'SINE', 'EASE_OUT')
key(cam, 'rotation_euler', T['vac'][0], Vector((0, 0, 0)), 'BEZIER')

# backdrop: fade in, glow pulse at shine, fade out
key(back_em.inputs['Strength'], 'default_value', 1, 0.0, 'SINE', 'EASE_OUT', idb=bm_mat.node_tree)
key(back_em.inputs['Strength'], 'default_value', T['bg_in'][1], 1.0, 'SINE', 'EASE_IN_OUT', idb=bm_mat.node_tree)
key(back_em.inputs['Strength'], 'default_value', T['shine'][0] + 6, 1.35, 'SINE', 'EASE_IN_OUT', idb=bm_mat.node_tree)
key(back_em.inputs['Strength'], 'default_value', T['shine'][1] + 8, 1.0, 'SINE', 'EASE_IN_OUT', idb=bm_mat.node_tree)
key(back_em.inputs['Strength'], 'default_value', T['vac'][0], 1.0, 'QUAD', 'EASE_IN', idb=bm_mat.node_tree)
key(back_em.inputs['Strength'], 'default_value', T['pop'], 0.55, 'BEZIER', idb=bm_mat.node_tree)

# dust: gentle drift + fade in
dust.rotation_euler = (0, 0, 0)
key(dust, 'location', 1, Vector((0.6, -0.2, 0)), 'LINEAR')
key(dust, 'location', 165, Vector((-0.8, 0.35, 1.5)), 'LINEAR')
key(dust_em.inputs['Strength'], 'default_value', 1, 0.0, 'SINE', 'EASE_OUT', idb=dust_mat.node_tree)
key(dust_em.inputs['Strength'], 'default_value', 18, 5.0, 'BEZIER', idb=dust_mat.node_tree)
key(dust_em.inputs['Strength'], 'default_value', T['vac'][1], 5.0, 'BEZIER', idb=dust_mat.node_tree)
key(dust_em.inputs['Strength'], 'default_value', T['vac'][1] + 4, 0.0, 'CONSTANT', idb=dust_mat.node_tree)

# mark: fly in from depth with a spin, settle with a soft overshoot
rest = Vector(mark['rest'])
a0, a1 = T['mark_in']
key(mark, 'location', 1, rest + Vector((-2.6, 2.4, -42)), 'CONSTANT')
key(mark, 'location', a0, rest + Vector((-2.6, 2.4, -42)), 'EXPO', 'EASE_OUT')
key(mark, 'location', a1 - 4, rest, 'BEZIER')
key(mark, 'rotation_euler', 1, Vector((math.radians(35), math.radians(-200), math.radians(-40))), 'CONSTANT')
key(mark, 'rotation_euler', a0, Vector((math.radians(35), math.radians(-200), math.radians(-40))), 'BACK', 'EASE_OUT', back=1.1)
key(mark, 'rotation_euler', a1, Vector((0, 0, 0)), 'SINE', 'EASE_IN_OUT')
# idle float
key(mark, 'rotation_euler', a1 + 30, Vector((math.radians(-2.0), math.radians(4.0), 0)), 'SINE', 'EASE_IN_OUT')
key(mark, 'rotation_euler', T['vac'][0], Vector((0, 0, 0)), 'SINE', 'EASE_IN_OUT')

# wordmark letters: flip up one after another
w0 = T['word_in']
for i, ob in enumerate(letters):
    r = Vector(ob['rest'])
    s0 = w0 + i * 1.6
    key(ob, 'location', 1, r + Vector((0, -0.45, -0.6)), 'CONSTANT')
    key(ob, 'location', s0, r + Vector((0, -0.45, -0.6)), 'EXPO', 'EASE_OUT')
    key(ob, 'location', s0 + 14, r, 'BEZIER')
    key(ob, 'rotation_euler', 1, Vector((math.radians(-100), 0, 0)), 'CONSTANT')
    key(ob, 'rotation_euler', s0, Vector((math.radians(-100), 0, 0)), 'BACK', 'EASE_OUT', back=1.6)
    key(ob, 'rotation_euler', s0 + 15, Vector((0, 0, 0)), 'BEZIER')
    key(ob, '["reveal"]', 1, 0.0, 'CONSTANT')
    key(ob, '["reveal"]', s0, 0.0, 'SINE', 'EASE_OUT')
    key(ob, '["reveal"]', s0 + 6, 1.0, 'CONSTANT')

# tagline: letters open from the centre outward
t0, t1 = T['tag_in']
xs = [Vector(o['rest']).x for o in tags]
xc = (min(xs) + max(xs)) / 2
for ob in tags:
    r = Vector(ob['rest'])
    st = t0 + abs(r.x - xc) * 1.8
    squeezed = Vector((xc + (r.x - xc) * 0.62, r.y, r.z))
    key(ob, 'location', 1, squeezed, 'CONSTANT')
    key(ob, 'location', st, squeezed, 'EXPO', 'EASE_OUT')
    key(ob, 'location', t1, r, 'BEZIER')
    key(ob, '["reveal"]', 1, 0.0, 'CONSTANT')
    key(ob, '["reveal"]', st, 0.0, 'SINE', 'EASE_OUT')
    key(ob, '["reveal"]', st + 10, 1.0, 'CONSTANT')

# shine ("zım"): band sweeps along direction d across all logo surfaces
proj = [p.dot(d) for p in [to_b(q) for c in geo['mark'] for seg in c for q in seg[1:]]]
proj += [Vector(o['rest']).dot(d) for o in letters + tags]
smin, smax = min(proj) - 0.8, max(proj) + 0.8
sw_node = shine.nodes['Sweep'].outputs[0]
in_node = shine.nodes['Intensity'].outputs[0]
key(sw_node, 'default_value', 1, smin, 'CONSTANT', idb=shine)
key(sw_node, 'default_value', T['shine'][0], smin, 'QUAD', 'EASE_IN_OUT', idb=shine)
key(sw_node, 'default_value', T['shine'][1], smax, 'CONSTANT', idb=shine)
key(in_node, 'default_value', 1, 0.0, 'CONSTANT', idb=shine)
key(in_node, 'default_value', T['shine'][0], 1.0, 'CONSTANT', idb=shine)
key(in_node, 'default_value', T['shine'][1], 0.0, 'CONSTANT', idb=shine)

# sparkle star
s0, s1 = T['spark']
key(spark, 'scale', 1, Vector((0, 0, 0)), 'CONSTANT')
key(spark, 'scale', s0, Vector((0, 0, 0)), 'EXPO', 'EASE_OUT')
key(spark, 'scale', s0 + 4, Vector((1, 1, 1)), 'SINE', 'EASE_IN')
key(spark, 'scale', s1, Vector((0, 0, 0)), 'CONSTANT')
key(spark_em.inputs['Strength'], 'default_value', 1, 0.0, 'CONSTANT', idb=spark_mat.node_tree)
key(spark_em.inputs['Strength'], 'default_value', s0, 400.0, 'CONSTANT', idb=spark_mat.node_tree)
key(spark, 'rotation_euler', s0, Vector((0, 0, 0)), 'LINEAR')
key(spark, 'rotation_euler', s1, Vector((0, 0, math.radians(90))), 'LINEAR')

# vacuum ("çık" öncesi): breath, suction with swirl
b0, b1 = T['breathe']
v0, v1 = T['vac']
bn = vac.nodes['Breath'].outputs[0]
pn = vac.nodes['Progress'].outputs[0]
key(bn, 'default_value', 1, 0.0, 'CONSTANT', idb=vac)
key(bn, 'default_value', b0, 0.0, 'SINE', 'EASE_OUT', idb=vac)
key(bn, 'default_value', b1, 0.06, 'SINE', 'EASE_IN', idb=vac)
key(bn, 'default_value', v1, 0.0, 'CONSTANT', idb=vac)
key(pn, 'default_value', 1, 0.0, 'CONSTANT', idb=vac)
key(pn, 'default_value', v0, 0.0, 'QUAD', 'EASE_IN', idb=vac)
key(pn, 'default_value', v1 - 1, 1.0, 'CONSTANT', idb=vac)

# HARD CUT TO BLACK (thriller-trailer style): everything disappears on one frame
CUT = T['cut']
for ob in [mark] + letters + tags + [dust, ring_in, spark, back]:
    key(ob, 'hide_render', 1, False, 'CONSTANT')
    key(ob, 'hide_render', CUT, True, 'CONSTANT')
wbg = world.node_tree.nodes['Background'].inputs['Strength']
key(wbg, 'default_value', 1, 1.0, 'CONSTANT', idb=world.node_tree)
key(wbg, 'default_value', CUT, 0.0, 'CONSTANT', idb=world.node_tree)

# inward ring (suction cue)
key(ring_in, 'scale', 1, Vector((6.5, 6.5, 1)), 'CONSTANT')
key(ring_in, 'scale', v0 - 4, Vector((6.5, 6.5, 1)), 'CUBIC', 'EASE_IN')
key(ring_in, 'scale', v1 - 1, Vector((0.02, 0.02, 1)), 'CONSTANT')
key(ring_in_em.inputs['Strength'], 'default_value', 1, 0.0, 'CONSTANT', idb=ring_in_mat.node_tree)
key(ring_in_em.inputs['Strength'], 'default_value', v0 - 4, 0.0, 'SINE', 'EASE_IN')
key(ring_in_em.inputs['Strength'], 'default_value', v1 - 2, 10.0, 'CONSTANT', idb=ring_in_mat.node_tree)
key(ring_in_em.inputs['Strength'], 'default_value', v1, 0.0, 'CONSTANT', idb=ring_in_mat.node_tree)

# ------------------------------------------------------------------ compositor: bloom + star streaks + vignette-free grade
comp = bpy.data.node_groups.new('Kompozit', 'CompositorNodeTree')
sc.compositing_node_group = comp
comp.interface.new_socket('Image', in_out='OUTPUT', socket_type='NodeSocketColor')
CN, CL = comp.nodes, comp.links
rl = CN.new('CompositorNodeRLayers')
bloom = CN.new('CompositorNodeGlare')
bloom.inputs['Type'].default_value = 'Bloom'
bloom.inputs['Quality'].default_value = 'High'
bloom.inputs['Threshold'].default_value = 0.9
bloom.inputs['Strength'].default_value = 0.55
bloom.inputs['Size'].default_value = 0.7
streak = CN.new('CompositorNodeGlare')
streak.inputs['Type'].default_value = 'Streaks'
streak.inputs['Quality'].default_value = 'High'
streak.inputs['Threshold'].default_value = 6.0
streak.inputs['Streaks'].default_value = 4
streak.inputs['Streaks Angle'].default_value = math.radians(18)
streak.inputs['Fade'].default_value = 0.93
streak.inputs['Strength'].default_value = 0.75
lens = CN.new('CompositorNodeLensdist')
lens.inputs['Dispersion'].default_value = 0.012
co = CN.new('NodeGroupOutput')
CL.new(rl.outputs['Image'], bloom.inputs['Image'])
CL.new(bloom.outputs['Image'], streak.inputs['Image'])
CL.new(streak.outputs['Image'], lens.inputs['Image'])
CL.new(lens.outputs['Image'], co.inputs[0])

# ------------------------------------------------------------------ render settings
W, H = map(int, args.res.split('x'))
r = sc.render
r.engine = 'CYCLES'
r.resolution_x, r.resolution_y, r.resolution_percentage = W, H, 100
r.use_motion_blur = not args.no_mblur
r.motion_blur_shutter = 0.5
r.film_transparent = False
r.use_persistent_data = True
if args.threads:
    r.threads_mode = 'FIXED'; r.threads = args.threads
r.compositor_device = 'CPU'
r.compositor_precision = 'FULL'
r.image_settings.file_format = 'PNG'
r.image_settings.color_depth = '16'
r.image_settings.color_mode = 'RGB'
cy = sc.cycles
cy.device = 'CPU'
cy.samples = args.samples
cy.use_adaptive_sampling = True
cy.adaptive_threshold = 0.02
cy.use_denoising = True
cy.max_bounces = 6
cy.diffuse_bounces = 2
cy.glossy_bounces = 3
cy.transmission_bounces = 2
cy.transparent_max_bounces = 8
cy.caustics_reflective = False
cy.caustics_refractive = False
cy.blur_glossy = 1.0
cy.sample_clamp_indirect = 8.0
sc.view_settings.view_transform = 'AgX'
sc.view_settings.look = 'AgX - Punchy'
sc.view_settings.exposure = 0.0

if args.save:
    r.filepath = '//render/'
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.save), compress=True)
    print('saved', args.save)

if not args.no_render:
    os.makedirs(args.out, exist_ok=True)
    if args.frames:
        frames = []
        for part in args.frames.split(','):
            if '-' in part:
                a, b = map(int, part.split('-')); frames += list(range(a, b + 1))
            else:
                frames.append(int(part))
    else:
        frames = list(range(1, F_END + 1))
    n_, k_ = map(int, args.step.split('/'))
    frames = [f_ for i_, f_ in enumerate(frames) if i_ % n_ == k_]
    import time
    for fr in frames:
        path = os.path.join(args.out, f'{fr:04d}.png')
        if os.path.exists(path):
            continue
        t = time.time()
        sc.frame_set(fr)
        r.filepath = path
        bpy.ops.render.render(write_still=True)
        print(f'FRAME {fr} {time.time() - t:.1f}s', flush=True)
