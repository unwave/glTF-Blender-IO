# Copyright 2018-2021 The glTF-Blender-IO authors.
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
import typing
from ....io.com import gltf2_io
from ....io.com.gltf2_io_extensions import Extension
from ....io.exp.gltf2_io_user_extensions import export_user_extensions
from ..gltf2_blender_gather_sampler import detect_manual_uv_wrapping
from ..gltf2_blender_gather_cache import cached
from . import gltf2_blender_gather_texture
from .gltf2_blender_search_node_tree import \
    get_texture_node_from_socket, \
    from_socket, \
    FilterByType, \
    previous_node, \
    get_const_from_socket, \
    NodeSocket, \
    get_texture_transform_from_mapping_node

# blender_shader_sockets determine the texture and primary_socket determines
# the textransform and UVMap. Ex: when combining an ORM texture, for
# occlusion the primary_socket would be the occlusion socket, and
# blender_shader_sockets would be the (O,R,M) sockets.

# Default socket parameter is used when there is a mapping between channels, and one of the channel is not a texture
# In that case, we will create a texture with one channel from texture, other from default socket value
# Example: MetallicRoughness

def gather_texture_info(primary_socket, blender_shader_sockets, default_sockets, export_settings, filter_type='ALL'):
    return __gather_texture_info_helper(primary_socket, blender_shader_sockets, default_sockets, 'DEFAULT', filter_type, export_settings)

def gather_material_normal_texture_info_class(primary_socket, blender_shader_sockets, export_settings, filter_type='ALL'):
    return __gather_texture_info_helper(primary_socket, blender_shader_sockets, (), 'NORMAL', filter_type, export_settings)

def gather_material_occlusion_texture_info_class(primary_socket, blender_shader_sockets, default_sockets, export_settings, filter_type='ALL'):
    return __gather_texture_info_helper(primary_socket, blender_shader_sockets, default_sockets, 'OCCLUSION', filter_type, export_settings)


@cached
def __gather_texture_info_helper(
        primary_socket: bpy.types.NodeSocket,
        blender_shader_sockets: typing.Tuple[bpy.types.NodeSocket],
        default_sockets,
        kind: str,
        filter_type: str,
        export_settings):
    if not __filter_texture_info(primary_socket, blender_shader_sockets, filter_type, export_settings):
        return None, {}, {'udim': False}, None

    tex_transform, uvmap_info = __gather_texture_transform_and_tex_coord(primary_socket, export_settings)

    index, factor, udim_image = __gather_index(blender_shader_sockets, default_sockets, export_settings)
    udim_info = {'udim': udim_image is not None, 'image': udim_image}

    fields = {
        'extensions': __gather_extensions(tex_transform, export_settings),
        'extras': __gather_extras(blender_shader_sockets, export_settings),
        'index': index,
        'tex_coord': None # This will be set later, as some data are dependant of mesh or object
    }

    if kind == 'DEFAULT':
        texture_info = gltf2_io.TextureInfo(**fields)

    elif kind == 'NORMAL':
        fields['scale'] = __gather_normal_scale(primary_socket, export_settings)
        texture_info = gltf2_io.MaterialNormalTextureInfoClass(**fields)

    elif kind == 'OCCLUSION':
        fields['strength'] = __gather_occlusion_strength(primary_socket, export_settings)
        texture_info = gltf2_io.MaterialOcclusionTextureInfoClass(**fields)

    if texture_info.index is None:
        return None, {} if udim_image is None else uvmap_info, udim_info, None

    export_user_extensions('gather_texture_info_hook', export_settings, texture_info, blender_shader_sockets)

    return texture_info, uvmap_info, udim_info, factor


def __filter_texture_info(primary_socket, blender_shader_sockets, filter_type, export_settings):
    if primary_socket is None:
        return False
    if get_texture_node_from_socket(primary_socket, export_settings) is None:
        return False
    if not blender_shader_sockets:
        return False
    if not all([elem is not None for elem in blender_shader_sockets]):
        return False
    if filter_type == "ALL":
        # Check that all sockets link to texture
        if any([get_texture_node_from_socket(socket, export_settings) is None for socket in blender_shader_sockets]):
            # sockets do not lead to a texture --> discard
            return False
    elif filter_type == "ANY":
        # Check that at least one socket link to texture
        if all([get_texture_node_from_socket(socket, export_settings) is None for socket in blender_shader_sockets]):
            return False
    elif filter_type == "NONE":
        # No check
        pass

    return True


def __gather_extensions(texture_transform, export_settings):
    if texture_transform is None:
        return None
    extension = Extension("KHR_texture_transform", texture_transform)
    return {"KHR_texture_transform": extension}


def __gather_extras(blender_shader_sockets, export_settings):
    return None


# MaterialNormalTextureInfo only
def __gather_normal_scale(primary_socket, export_settings):
    result = from_socket(
        primary_socket,
        FilterByType(bpy.types.ShaderNodeNormalMap))
    if not result:
        return None
    strengthInput = result[0].shader_node.inputs['Strength']
    if not strengthInput.is_linked and strengthInput.default_value != 1:
        return strengthInput.default_value
    return None


# MaterialOcclusionTextureInfo only
def __gather_occlusion_strength(primary_socket, export_settings):
    # Look for a MixRGB node that mixes with pure white in front of
    # primary_socket. The mix factor gives the occlusion strength.
    node = previous_node(primary_socket)
    if node and node.node.type == 'MIX' and node.node.blend_type == 'MIX':
        fac = get_const_from_socket(NodeSocket(node.node.inputs['Factor'], node.group_path), kind='VALUE')
        col1 = get_const_from_socket(NodeSocket(node.node.inputs[6], node.group_path), kind='RGB')
        col2 = get_const_from_socket(NodeSocket(node.node.inputs[7], node.group_path), kind='RGB')
        if fac is not None:
            if col1 == [1.0, 1.0, 1.0] and col2 is None:
                return fac
            if col1 is None and col2 == [1.0, 1.0, 1.0]:
                return 1.0 - fac  # reversed for reversed inputs

    return None


def __gather_index(blender_shader_sockets, default_sockets, export_settings):
    # We just put the actual shader into the 'index' member
    return gltf2_blender_gather_texture.gather_texture(blender_shader_sockets, default_sockets, export_settings)


def __gather_texture_transform_and_tex_coord(primary_socket, export_settings):
    # We're expecting
    #
    #     [UV Map] => [Mapping] => [UV Wrapping] => [Texture Node] => ... => primary_socket
    #
    # The [UV Wrapping] is for wrap modes like MIRROR that use nodes,
    # [Mapping] is for KHR_texture_transform, and [UV Map] is for texCoord.
    result_tex = get_texture_node_from_socket(primary_socket, export_settings)
    blender_shader_node = result_tex.shader_node

    # Skip over UV wrapping stuff (it goes in the sampler)
    result = detect_manual_uv_wrapping(blender_shader_node, result_tex.group_path)
    if result:
        node = previous_node(result['next_socket'])
    else:
        node = previous_node(NodeSocket(blender_shader_node.inputs['Vector'], result_tex.group_path))

    texture_transform = None
    if node.node and node.node.type == 'MAPPING':
        texture_transform = get_texture_transform_from_mapping_node(node)
        node = previous_node(NodeSocket(node.node.inputs['Vector'], node.group_path))

    uvmap_info = {}

    if node.node and node.node.type == 'UVMAP' and node.node.uv_map:
        uvmap_info['type'] = "Fixed"
        uvmap_info['value'] = node.node.uv_map

    elif node and node.node and node.node.type == 'ATTRIBUTE' \
            and node.node.attribute_type == "GEOMETRY" \
            and node.node.attribute_name:
        uvmap_info['type'] = 'Attribute'
        uvmap_info['value'] = node.node.attribute_name

    else:
        uvmap_info['type'] = 'Active'

    return texture_transform, uvmap_info


def check_same_size_images(
    blender_shader_sockets: typing.Tuple[bpy.types.NodeSocket],
    export_settings
) -> bool:
    """Check that all sockets leads to images of the same size."""
    if not blender_shader_sockets or not all(blender_shader_sockets):
        return False

    sizes = set()
    for socket in blender_shader_sockets:
        tex = get_texture_node_from_socket(socket, export_settings)
        if tex is None:
            return False
        size = tex.shader_node.image.size
        sizes.add((size[0], size[1]))

    return len(sizes) == 1
