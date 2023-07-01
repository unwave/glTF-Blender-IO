# Copyright 2018-2023 The glTF-Blender-IO authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import bpy
from ...io.imp.gltf2_io_user_extensions import import_user_extensions
from ...io.imp.gltf2_io_binary import BinaryData
from .gltf2_blender_animation_utils import make_fcurve
from .gltf2_blender_light import BlenderLight


class BlenderPointerAnim():
    """Blender Pointer Animation."""
    def __new__(cls, *args, **kwargs):
        raise RuntimeError("%s should not be instantiated" % cls)

    @staticmethod
    def anim(gltf, anim_idx, asset, asset_idx, asset_type):
        animation = gltf.data.animations[anim_idx]

        if asset_type in ["LIGHT"]:
            if anim_idx not in asset['animations'].keys():
                return
            tab = asset['animations']
        else:
            if anim_idx not in asset.animations.keys():
                return
            tab = asset.animations

        for channel_idx in tab[anim_idx]:
            channel = animation.channels[channel_idx]
            BlenderPointerAnim.do_channel(gltf, anim_idx, channel, asset, asset_idx, asset_type)

    @staticmethod
    def do_channel(gltf, anim_idx, channel, asset, asset_idx, asset_type):
        animation = gltf.data.animations[anim_idx]
        pointer_tab = channel.target.extensions["KHR_animation_pointer"]["pointer"].split("/")

        import_user_extensions('gather_import_animation_pointer_channel_before_hook', gltf, animation, channel)

        action = BlenderPointerAnim.get_or_create_action(gltf, asset, asset_idx, animation.track_name, asset_type)

        keys = BinaryData.get_data_from_accessor(gltf, animation.samplers[channel.sampler].input)
        values = BinaryData.get_data_from_accessor(gltf, animation.samplers[channel.sampler].output)

        if animation.samplers[channel.sampler].interpolation == "CUBICSPLINE":
            # TODO manage tangent?
            values = values[1::3]

        # Convert the curve from glTF to Blender.
        blender_path = None
        num_components = None
        group_name = ''
        ### Camera
        if len(pointer_tab) == 5 and pointer_tab[1] == "cameras" and \
            pointer_tab[3] in ["perspective"] and \
            pointer_tab[4] in ["yfov", "znear", "zfar"]:
            blender_path = {
                "yfov": "angle_y", #TODOPointer : need to convert, angle can't be animated
                "znear": "clip_start",
                "zfar": "clip_end"
            }.get(pointer_tab[4])
            num_components = 1

        if len(pointer_tab) == 5 and pointer_tab[1] == "cameras" and \
            pointer_tab[3] in ["orthographic"] and \
            pointer_tab[4] in ["ymag", "xmag"]:
            # TODOPointer need to calculate, and before, check if both are animated of not
            num_components = 1

        ### Light
        if len(pointer_tab) == 6 and pointer_tab[1] == "extensions" and \
            pointer_tab[2] == "KHR_lights_punctual" and \
            pointer_tab[3] == "lights" and \
            pointer_tab[5] in ["intensity", "color", "range"]:

            blender_path = {
                "color": "color",
                "intensity": "energy"
            }.get(pointer_tab[5])
            group_name = 'Color'
            num_components = 3 if blender_path == "color" else 1

            # TODO perf, using numpy
            if blender_path == "energy":
                old_values = values.copy()
                for idx, i in enumerate(old_values):
                    if asset['type'] in ["SPOT", "POINT"]:
                        values[idx] = [BlenderLight.calc_energy_pointlike(gltf, i[0])]
                    else:
                        values[idx] = [BlenderLight.calc_energy_directional(gltf, i[0])]

            #TODO range, not implemented (even not in static import)

        if len(pointer_tab) == 7 and pointer_tab[1] == "extensions" and \
            pointer_tab[2] == "KHR_lights_punctual" and \
            pointer_tab[3] == "lights" and \
            pointer_tab[5] == "spot" and \
            pointer_tab[6] in ["outerConeAngle", "innerConeAngle"]:

            if pointer_tab[6] == "outerConeAngle":
                blender_path = "spot_size"
                num_components = 1

            # TODOPointer innerConeAngle, need to calculate, and before, check if innerConeAngle are animated of not

        #### Materials
        if len(pointer_tab) == 4 and pointer_tab[1] == "materials" and \
            pointer_tab[3] in ["emissiveFactor", "alphaCutoff"]:

            pass
            # blender_path = ""
            # num_components =

        if len(pointer_tab) == 5 and pointer_tab[1] == "materials" and \
            pointer_tab[3] == "normalTexture" and \
            pointer_tab[4] == "scale":

            pass
            # blender_path = ""
            # num_components =

        if len(pointer_tab) == 5 and pointer_tab[1] == "materials" and \
            pointer_tab[3] == "occlusionTexture" and \
            pointer_tab[4] == "strength":

            pass
            # blender_path = ""
            # num_components =

        if len(pointer_tab) == 5 and pointer_tab[1] == "materials" and \
            pointer_tab[3] == "pbrMetallicRoughness" and \
            pointer_tab[4] in ["baseColorFactor", "roughnessFactor", "metallicFactor"]:

            pass
            # blender_path = ""
            # num_components =

        if len(pointer_tab) == 8 and pointer_tab[1] == "materials" and \
            pointer_tab[3] == "pbrMetallicRoughness" and \
            pointer_tab[4] == "baseColorFactor" and \
            pointer_tab[5] == "extensions" and \
            pointer_tab[6] == "KHR_texture_transform" and \
            pointer_tab[7] in ["scale", "offset"]:

            pass
            # blender_path = ""
            # num_components =

        if len(pointer_tab) == 6 and pointer_tab[1] == "materials" and \
            pointer_tab[3] == "extensions" and \
            pointer_tab[4] == "KHR_materials_emissive_strength" and \
            pointer_tab[5] == "emissiveStrength":

            pass
            # blender_path = ""
            # num_components =

        if len(pointer_tab) == 6 and pointer_tab[1] == "materials" and \
            pointer_tab[3] == "extensions" and \
            pointer_tab[4] == "KHR_materials_volume" and \
            pointer_tab[5] in ["thicknessFactor", "attenuationDistance", "attenuationColor"]:

            pass
            # blender_path = ""
            # num_components =

        if len(pointer_tab) == 6 and pointer_tab[1] == "materials" and \
            pointer_tab[3] == "extensions" and \
            pointer_tab[4] == "KHR_materials_ior" and \
            pointer_tab[5] == "ior":

            pass
            # blender_path = ""
            # num_components =

        if len(pointer_tab) == 6 and pointer_tab[1] == "materials" and \
            pointer_tab[3] == "extensions" and \
            pointer_tab[4] == "KHR_materials_transmission" and \
            pointer_tab[5] == "transmissionFactor":

            pass
            # blender_path = ""
            # num_components =


        if blender_path is None:
            return # Should not happen if all specification is managed

        fps = bpy.context.scene.render.fps

        coords = [0] * (2 * len(keys))
        coords[::2] = (key[0] * fps for key in keys)

        for i in range(0, num_components):
            coords[1::2] = (vals[i] for vals in values)
            make_fcurve(
                action,
                coords,
                data_path=blender_path,
                index=i,
                group_name=group_name,
                interpolation=animation.samplers[channel.sampler].interpolation,
            )

    @staticmethod
    def get_or_create_action(gltf, asset, asset_idx, anim_name, asset_type):

        action = None
        if asset_type == "CAMERA":
            data_name = "camera_" + asset.name or "Camera%d" % asset_idx
            action = gltf.action_cache.get(data_name)
            id_root = "CAMERA"
            stash = asset.blender_object_data
        elif asset_type == "LIGHT":
            data_name = "light_" + asset['name'] or "Light%d" % asset_idx
            action = gltf.action_cache.get(data_name)
            id_root = "LIGHT"
            stash = asset['blender_object_data']

        if not action:
            name = anim_name + "_" + data_name
            action = bpy.data.actions.new(name)
            action.id_root = id_root
            gltf.needs_stash.append((stash, action))
            gltf.action_cache[data_name] = action

        return action
