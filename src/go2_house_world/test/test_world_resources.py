"""Offline checks for the shared apartment's installed runtime asset contract."""
from pathlib import Path
import os
import xml.etree.ElementTree as ET

ROOT = Path(os.environ.get('GO2_HOUSE_WORLD_SHARE', Path(__file__).resolve().parents[1]))
TARGETS = {
    'target_green_cube_living_room': (3.1, 6.1, .15),
    'target_red_triangle_bedroom1': (7., 5.8, .175),
    'target_blue_cylinder_bedroom2': (10., 5.8, .175),
    'target_yellow_cube_master_bedroom': (13.2, 5.8, .15),
    'target_purple_cylinder_kitchen': (4.7, -.5, .175),
}


def test_model_resource_closure():
    """Every SDF model/mesh and model.config reference resolves within the package."""
    for path in [*ROOT.glob('worlds/*.sdf'), *ROOT.glob('models/*/model.sdf')]:
        for uri in ET.parse(path).findall('.//uri'):
            assert uri.text.startswith('model://'), (path, uri.text)
            relative = uri.text.removeprefix('model://')
            target = ROOT / 'models' / relative
            assert target.exists(), (path, target)
            # colcon --symlink-install links individual assets back to source.
            source_models = Path(__file__).resolve().parents[1] / 'models'
            assert any(target.resolve().is_relative_to(base.resolve())
                       for base in (ROOT / 'models', source_models))
    configs = list(ROOT.glob('models/*/model.config'))
    assert len(configs) == 6
    for config in configs:
        assert (config.parent / ET.parse(config).findtext('sdf')).is_file()


def test_obj_material_and_oak_texture():
    mesh = ROOT / 'models/greenquartz_bto/meshes/GreenQuartz_BTO.obj'
    material = mesh.with_suffix('.mtl')
    assert any(line.strip() == 'mtllib GreenQuartz_BTO.mtl' for line in mesh.read_text().splitlines())
    assert 'newmtl Oak_-_Glossy' in material.read_text()
    textures = [line.split(maxsplit=1)[1] for line in material.read_text().splitlines() if line.startswith('map_Kd ')]
    assert textures == ['../materials/textures/pale_oak.png']
    for name in textures:
        assert (material.parent / name).read_bytes().startswith(b'\x89PNG\r\n\x1a\n')


def test_target_poses_and_geometry():
    world = ET.parse(ROOT / 'worlds/greenquartz_bto.sdf')
    found = {}
    for include in world.findall('.//include'):
        name = include.findtext('name', '')
        if name not in TARGETS:
            continue
        pose = tuple(map(float, include.findtext('pose').split()))
        assert pose == (*TARGETS[name], 0., 0., 0.)
        model = ET.parse(ROOT / 'models' / name / 'model.sdf')
        assert model.findtext('.//static') == 'true'
        visual = model.find('.//visual/geometry')
        collision = model.find('.//collision/geometry')
        def signature(element):
            return (element.tag, (element.text or "").strip(),
                    tuple(signature(child) for child in element))
        assert signature(visual) == signature(collision)
        found[name] = pose
    assert set(found) == set(TARGETS)


def test_collision_floor_and_room_placement():
    apartment = ET.parse(ROOT / 'models/greenquartz_bto/model.sdf')
    assert apartment.findtext('.//model/pose') == '0 0 -0.01 0 0 0'
    collisions = apartment.findall('.//collision')
    assert len(collisions) == 249
    boxes = []
    for collision in collisions:
        xyz = list(map(float, collision.findtext('pose').split()[:3]))
        xyz[2] -= .01
        size = list(map(float, collision.findtext('geometry/box/size').split()))
        boxes.append(([x-s/2 for x,s in zip(xyz,size)], [x+s/2 for x,s in zip(xyz,size)]))
    rooms = [(0.355,5.775,.35,7.465),(5.885,8.655,4.025,7.465),
             (8.765,11.531,4.025,7.465),(11.641,14.571,2.829,7.465),
             (3.522,9.322,-2.018,.852)]
    for (name,xyz), (xmin,xmax,ymin,ymax) in zip(TARGETS.items(),rooms):
        assert xmin < xyz[0] < xmax and ymin < xyz[1] < ymax
        half = (.175,.075,.175) if 'triangle' in name else (.15,.15,xyz[2])
        low = [x-h for x,h in zip(xyz,half)]
        high = [x+h for x,h in zip(xyz,half)]
        assert abs(low[2]) < 1e-9
        assert any(abs(b[2]) < 1e-8 and all(a[i] <= low[i]+1e-8 and b[i] >= high[i]-1e-8 for i in (0,1)) for a,b in boxes)
        assert not any(all(high[i] > a[i]+1e-8 and low[i] < b[i]-1e-8 for i in range(3)) for a,b in boxes)


def test_no_personal_asset_paths():
    for folder in ('models', 'worlds', 'launch'):
        for path in (ROOT / folder).rglob('*'):
            if path.is_file() and path.suffix in ('.obj','.mtl','.sdf','.config','.dae','.py'):
                text = path.read_text()
                assert not any(value in text for value in ('/home/', '~/Downloads', 'go2_jazzy_ws'))
