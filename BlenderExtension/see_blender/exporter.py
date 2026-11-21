import os
import re
import json
from math import degrees, atan, tan
import bpy
import bmesh
from bpy_extras.io_utils import ExportHelper, axis_conversion
from bpy.props import StringProperty, BoolProperty
from bpy.types import Operator

from .ply import save_mesh

def sanitize_path(path):
    # Remove forbidden characters from the filename, make sure it does not end on a . or space
    path = re.sub('[<>:"/\\\\|?*]', "_", path).strip()
    if path.endswith('.'): path = path[:-1]
    path = path.strip()
    assert path != ""
    return path

def map_rgb(rgb):
    return { "type": "rgb", "value": [ rgb[0], rgb[1], rgb[2] ] }

def map_texture(texture, out_dir):
    path = texture.filepath_raw.replace('//', '')
    if path == '':
        path = sanitize_path(texture.name + ".exr")
        texture.file_format = "OPEN_EXR"

    # Convert unsupported formats to EXR
    if not texture.file_format in [
        "BMP",
        "PNG",
        "JPEG",
        "TIFF",
        "OPEN_EXR",
        "HDR"
    ]:
        path = sanitize_path(texture.name + ".exr")
        texture.file_format = "OPEN_EXR"

    # Also convert if the extension is unsupported (Why is this needed? Ask Blender!)
    ext = os.path.splitext(path)[1]
    if not ext in [
        ".exr",
        ".bmp",
        ".png",
        ".jpg", ".jpeg",
        ".tiff", ".hdr"
    ]:
        path = sanitize_path(texture.name + ".exr")
        texture.file_format = "OPEN_EXR"

    # Make sure the image is loaded to memory, so we can write it out
    if not texture.has_data:
        texture.pixels[0]

    os.makedirs(f"{out_dir}/Textures", exist_ok=True)

    # Export the texture and store its path
    name = os.path.basename(path)
    old = texture.filepath_raw
    try:
        texture.filepath_raw = f"{out_dir}/Textures/{name}"
        texture.save()
    finally: # Never break the scene!
        texture.filepath_raw = old

    return { "type": "image", "filename": f"Textures/{name}" }

def map_texture_filename(texture, out_dir):
    path = texture.filepath_raw.replace('//', '')
    if path == '':
        path = sanitize_path(texture.name + ".exr")
        texture.file_format = "OPEN_EXR"

    # Convert unsupported formats to EXR
    if not texture.file_format in [
        "BMP",
        "PNG",
        "JPEG",
        "TIFF",
        "OPEN_EXR",
        "HDR"
    ]:
        path = sanitize_path(texture.name + ".exr")
        texture.file_format = "OPEN_EXR"

    # Also convert if the extension is unsupported (Why is this needed? Ask Blender!)
    ext = os.path.splitext(path)[1]
    if not ext in [
        "exr",
        "bmp",
        "png",
        "jpg", "jpeg",
        "tiff", "hdr"
    ]:
        path = sanitize_path(texture.name + ".exr")
        texture.file_format = "OPEN_EXR"

    # Make sure the image is loaded to memory, so we can write it out
    if not texture.has_data:
        texture.pixels[0]

    os.makedirs(f"{out_dir}/Textures", exist_ok=True)

    # Export the texture and store its path
    name = os.path.basename(path)
    old = texture.filepath_raw
    try:
        texture.filepath_raw = f"{out_dir}/Textures/{name}"
        texture.save()
    finally: # Never break the scene!
        texture.filepath_raw = old

    return f"Textures/{name}"

def material_to_json(material, out_dir):
    if material.base_texture:
        base_color = map_texture(material.base_texture, out_dir)
    else:
        base_color = map_rgb(material.base_color)

    if material.rough_texture:
        roughness = map_texture_filename(material.rough_texture, out_dir)
    else:
        roughness = material.roughness

    return {
        "type": "generic",
        "baseColor": base_color,
        "roughness": roughness,
        "anisotropic": material.anisotropic,
        "IOR": material.indexOfRefraction,
        "metallic": material.metallic,
        "specularTintStrength": material.specularTintStrength,
        "specularTransmittance": material.specularTransmittance,
        "emission": map_rgb((
            material.emission_color[0] * material.emission_strength,
            material.emission_color[1] * material.emission_strength,
            material.emission_color[2] * material.emission_strength
        )),
        "emission_color":  map_rgb(material.emission_color),
        "emission_strength": material.emission_strength,
        "emissionIsGlossy": material.emission_is_glossy,
        "emissionExponent": material.emission_glossy_exponent
    }

def export_materials(result, out_dir):
    result["materials"] = []
    for material in list(bpy.data.materials):
        result["materials"].append(material_to_json(material.seesharp, out_dir))
        # TODO If .obj export is used, spaces need to be replaced to match the name in the output file
        # result["materials"][-1]["name"] = material.name.replace(" ", "_")
        result["materials"][-1]["name"] = material.name

def export_background(result, out_dir, scene):
    if scene.world.seesharp.hdr:
        result["background"] = map_texture(scene.world.seesharp.hdr, out_dir)

def export_camera(result, scene):
    camera = scene.camera

    if camera is None:
        result["transforms"] = [
            {
                "name": "camera",
                "position": [ 0, 0, 0 ],
                "rotation": [ 0, 0, 0 ],
                "scale": [ 1.0, 1.0, 1.0 ]
            }
        ]
        result["cameras"] = [
            {
                "fov": 45,
                "transform": "camera",
                "name": "default",
                "type": "perspective"
            }
        ]
        return

    aspect_ratio = scene.render.resolution_y / scene.render.resolution_x
    blend_cam2world = camera.matrix_world.copy()
    blend_world2see_world = axis_conversion(
        to_forward="Z",
        to_up="Y",
    ).to_4x4()
    def matrix_to_row_major_list(m):
        return [
            m[0][0], m[0][1], m[0][2], m[0][3],
            m[1][0], m[1][1], m[1][2], m[1][3],
            m[2][0], m[2][1], m[2][2], m[2][3],
            m[3][0], m[3][1], m[3][2], m[3][3],
        ]

    result["transforms"] = [
        {
            "name": "camera",
            "matrix": matrix_to_row_major_list((blend_world2see_world @  blend_cam2world).transposed())
        }
    ]

    result["cameras"] = [
        {
            # convert horizontal FOV to vertical FOV
            "fov": degrees(2 * atan(aspect_ratio * tan(camera.data.angle / 2))),
            "transform": "camera",
            "name": "default",
            "type": "perspective"
        }
    ]

# def export_ply_object(result, obj, filepath):
#     """ Exports an object as a set of .ply files, separated by material, with baked transformations
#     """
#     global_matrix = axis_conversion(
#         to_forward="Z",
#         to_up="Y",
#     ).to_4x4()

#     mesh = obj.to_mesh()
#     # Iterate over every material and export the faces that use this material
#     for mat_idx in range(0, len(mesh.materials)):
#         bm = bmesh.new()
#         bm.from_mesh(mesh)

#         # Filter by material ID: remove all faces that are not the current material
#         if len(mesh.materials) > 1:
#             for f in bm.faces:
#                 if f.material_index != mat_idx:
#                     bm.faces.remove(f)
#         if len(bm.verts) == 0 or len(bm.faces) == 0 or not bm.is_valid:
#             bm.free()
#             continue

#         # Bake transformation and convert from Blender-space to SeeSharp-space
#         bm.transform(obj.matrix_world)
#         bm.transform(global_matrix)

#         bm.normal_update()

#         filename = sanitize_path(f"{obj.name}.{mat_idx}.ply")

#         path = os.path.join(os.path.dirname(filepath), 'Meshes', filename)
#         save_mesh(path, bm,
#             use_ascii=False,
#             use_normals=True,
#             use_uv=True,
#             use_color=False)

#         result['objects'].append({
#             "name": obj.name,
#             "type": "ply",
#             "material": mesh.materials[mat_idx].name,
#             "relativePath": 'Meshes/' + filename
#         })

#         bm.free()

def export_ply_object(result, obj, filepath):
    """
    Export an object to separate binary PLY files per material.

    Positions, UVs, triangle indices and material indices are
    processed using NumPy.

    Normals are calculated using the original BMesh technique:
        v.normal if f.smooth else f.normal
    """
    import numpy as np
    mesh = obj.to_mesh()

    if mesh is None:
        return

    bm = None

    try:
        # ---------------------------------------------------------
        # 1. Prepare coordinate transformation
        # ---------------------------------------------------------

        global_matrix = axis_conversion(
            to_forward="Z",
            to_up="Y",
        ).to_4x4()

        transform = global_matrix @ obj.matrix_world

        # ---------------------------------------------------------
        # 2. Triangulate mesh
        # ---------------------------------------------------------

        mesh.calc_loop_triangles()

        triangles = mesh.loop_triangles
        triangle_count = len(triangles)

        if triangle_count == 0:
            return

        # ---------------------------------------------------------
        # 3. Extract vertex positions using foreach_get
        # ---------------------------------------------------------

        vertices = np.empty(
            len(mesh.vertices) * 3,
            dtype=np.float32
        )

        mesh.vertices.foreach_get("co", vertices)

        vertices = vertices.reshape(-1, 3)

        # Apply object-world and coordinate-system transformations.
        transform_np = np.array(transform, dtype=np.float32)

        positions = (
            vertices @ transform_np[:3, :3].T
            + transform_np[:3, 3]
        )

        # ---------------------------------------------------------
        # 4. Extract triangle information
        # ---------------------------------------------------------

        # Three vertex indices per triangle.
        tri_vertices = np.empty(
            triangle_count * 3,
            dtype=np.int32
        )

        triangles.foreach_get("vertices", tri_vertices)

        tri_vertices = tri_vertices.reshape(-1, 3)

        # Three original loop indices per triangle.
        tri_loops = np.empty(
            triangle_count * 3,
            dtype=np.int32
        )

        triangles.foreach_get("loops", tri_loops)

        tri_loops = tri_loops.reshape(-1, 3)

        # Original polygon index for each triangle.
        tri_polygon_indices = np.empty(
            triangle_count,
            dtype=np.int32
        )

        triangles.foreach_get(
            "polygon_index",
            tri_polygon_indices
        )

        # Material index for each triangle.
        tri_material_indices = np.empty(
            triangle_count,
            dtype=np.int32
        )

        triangles.foreach_get(
            "material_index",
            tri_material_indices
        )

        # ---------------------------------------------------------
        # 5. Calculate normals using the OLD BMesh technique
        # ---------------------------------------------------------

        bm = bmesh.new()
        bm.from_mesh(mesh)

        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        bm.verts.index_update()
        bm.faces.index_update()

        # Apply the same transformations as the original exporter.
        bm.transform(transform)

        # Recalculate vertex and face normals.
        bm.normal_update()

        # Extract vertex normals.
        vertex_normals = np.array(
            [v.normal[:] for v in bm.verts],
            dtype=np.float32
        )

        # Extract face normals.
        face_normals = np.array(
            [f.normal[:] for f in bm.faces],
            dtype=np.float32
        )

        # Extract smooth/flat shading information.
        face_smooth = np.array(
            [f.smooth for f in bm.faces],
            dtype=bool
        )

        # Build three corner normals for every triangle.
        normals = np.empty(
            (triangle_count, 3, 3),
            dtype=np.float32
        )

        # Determine whether each triangle belongs to a smooth face.
        smooth_triangles = face_smooth[tri_polygon_indices]

        # Smooth faces: use the corresponding vertex normals.
        normals[smooth_triangles] = vertex_normals[
            tri_vertices[smooth_triangles]
        ]

        # Flat faces: use the original polygon face normal
        # for all three triangle corners.
        flat_normals = face_normals[
            tri_polygon_indices[~smooth_triangles]
        ]

        normals[~smooth_triangles] = np.repeat(
            flat_normals[:, None, :],
            3,
            axis=1
        )

        # BMesh is no longer needed.
        bm.free()
        bm = None

        # ---------------------------------------------------------
        # 6. Extract UV coordinates
        # ---------------------------------------------------------

        uv_layer = None

        if len(mesh.uv_layers) > 0:
            uv_index = mesh.uv_layers.active_index

            if 0 <= uv_index < len(mesh.uv_layers):
                uv_layer = mesh.uv_layers[uv_index]

        if uv_layer is not None:

            uv = np.empty(
                len(mesh.loops) * 2,
                dtype=np.float32
            )

            uv_layer.uv.foreach_get("vector", uv)

            uv = uv.reshape(-1, 2)

            # Map UVs using the original triangle loop indices.
            triangle_uvs = uv[tri_loops]

        else:
            # No UV layer: use zero UV coordinates.
            triangle_uvs = np.zeros(
                (triangle_count, 3, 2),
                dtype=np.float32
            )

        # ---------------------------------------------------------
        # 7. Get triangle positions
        # ---------------------------------------------------------

        triangle_positions = positions[tri_vertices]

        # ---------------------------------------------------------
        # 8. Prepare output directory
        # ---------------------------------------------------------

        mesh_dir = os.path.join(
            os.path.dirname(filepath),
            "Meshes"
        )

        os.makedirs(mesh_dir, exist_ok=True)

        # ---------------------------------------------------------
        # 9. Export one PLY file per material
        # ---------------------------------------------------------

        for mat_idx, material in enumerate(mesh.materials):

            # Select triangles belonging to this material.
            selected = tri_material_indices == mat_idx

            if not np.any(selected):
                continue

            # Select triangle data.
            selected_positions = triangle_positions[selected]
            selected_normals = normals[selected]
            selected_uvs = triangle_uvs[selected]

            # Combine attributes:
            # x, y, z, nx, ny, nz, u, v
            #
            # Shape:
            # (triangle_count, 3, 8)

            data = np.concatenate(
                (
                    selected_positions,
                    selected_normals,
                    selected_uvs
                ),
                axis=2
            )

            # Flatten triangle corners.
            data = data.reshape(-1, 8)

            # -----------------------------------------------------
            # 10. Deduplicate vertices
            # -----------------------------------------------------

            unique_vertices, inverse_indices = np.unique(
                data,
                axis=0,
                return_inverse=True
            )

            # Reconstruct triangle indices.
            face_indices = inverse_indices.reshape(-1, 3)

            # Ensure correct binary data types.
            unique_vertices = np.asarray(
                unique_vertices,
                dtype="<f4"
            )

            face_indices = np.asarray(
                face_indices,
                dtype="<i4"
            )

            # -----------------------------------------------------
            # 11. Generate PLY filename
            # -----------------------------------------------------

            filename = sanitize_path(
                f"{obj.name}.{mat_idx}.ply"
            )

            output_path = os.path.join(
                mesh_dir,
                filename
            )

            # -----------------------------------------------------
            # 12. Write binary PLY
            # -----------------------------------------------------

            with open(output_path, "wb") as f:

                header = (
                    "ply\n"
                    "format binary_little_endian 1.0\n"
                    f"element vertex {len(unique_vertices)}\n"
                    "property float x\n"
                    "property float y\n"
                    "property float z\n"
                    "property float nx\n"
                    "property float ny\n"
                    "property float nz\n"
                    "property float s\n"
                    "property float t\n"
                    f"element face {len(face_indices)}\n"
                    "property list uchar int vertex_indices\n"
                    "end_header\n"
                )

                f.write(header.encode("ascii"))

                # Write vertex attributes.
                f.write(unique_vertices.tobytes())

                # Write face records.
                # Each record:
                # 1 byte: number of vertices (3)
                # 4 bytes: vertex index 0
                # 4 bytes: vertex index 1
                # 4 bytes: vertex index 2

                face_records = np.empty(
                    len(face_indices),
                    dtype=[
                        ("count", "u1"),
                        ("indices", "<i4", (3,))
                    ]
                )

                face_records["count"] = 3
                face_records["indices"] = face_indices

                f.write(face_records.tobytes())

            # -----------------------------------------------------
            # 13. Update SeeSharp JSON description
            # -----------------------------------------------------

            result["objects"].append({
                "name": obj.name,
                "type": "ply",
                "material": material.name,
                "relativePath": "Meshes/" + filename
            })

    finally:

        # Clean up BMesh if an exception occurred.
        if bm is not None:
            bm.free()

        # Release the evaluated mesh.
        obj.to_mesh_clear()
def export_ply_meshes(result, depsgraph, filepath):
    import time
    start = time.time()

    os.makedirs(os.path.join(os.path.dirname(filepath), 'Meshes'), exist_ok=True)
    result['objects'] = []
    for inst in depsgraph.object_instances:
        objType = inst.object.type
        if objType == "MESH" or objType == "CURVE" or objType == "SURFACE":
            export_ply_object(result, inst.object, filepath)

    end = time.time()
    print(f".ply meshes exported in {end - start:.3f}s")


def export_scene(filepath, scene, depsgraph):
    result = {}
    export_materials(result, os.path.dirname(filepath))
    export_camera(result, scene)
    export_background(result, os.path.dirname(filepath), scene)
    export_ply_meshes(result, depsgraph, filepath)

    result["exposure"] = scene.view_settings.exposure

    # Write the result into the .json
    with open(filepath, 'w') as fp:
        json.dump(result, fp, indent=2)

class SeeSharpExport(Operator, ExportHelper):
    """SeeSharp scene exporter"""
    bl_idname = "export.to_seesharp"
    bl_label = "SeeSharp Scene Exporter"

    # ExportHelper mixin class uses this
    filename_ext = ".json"

    filter_glob: StringProperty(
        default="*.json",
        options={'HIDDEN'},
        maxlen=255,  # Max internal buffer length, longer would be clamped.
    )

    animations: BoolProperty(
        name="Export Animations",
        description="If true, writes .json and .obj files for each frame in the animation.",
        default=False,
    )

    def execute(self, context):
        if context.window is not None:
            context.window.cursor_set('WAIT')

        if self.animations is True:
            for frame in range(context.scene.frame_start, context.scene.frame_end+1):
                context.scene.frame_set(frame)
                depsgraph = context.evaluated_depsgraph_get()
                export_scene(self.filepath.replace('.json', f'{frame:04}.json'), context.scene, depsgraph)
        else:
            depsgraph = context.evaluated_depsgraph_get()
            export_scene(self.filepath, context.scene, depsgraph)

        if context.window is not None:
            context.window.cursor_set('DEFAULT')
        return {'FINISHED'}

def menu_func_export(self, context):
    self.layout.operator(SeeSharpExport.bl_idname, text="SeeSharp Export")

def register():
    bpy.utils.register_class(SeeSharpExport)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    bpy.utils.unregister_class(SeeSharpExport)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

if __name__ == "__main__":
    register()

    # test call
    bpy.ops.export.to_seesharp('INVOKE_DEFAULT')
