# Written by Claude Code
"""Coordinate conversions of the PAR framework, imported as `from par_geometry import ...`."""

from .par_geometry import (apply_homography, compute_camera_to_projector_homography,
                           compute_closest_point_to_rays, compute_pixel_rays, depth_to_table,
                           get_homography_from_mapping_msg, pixels_to_table, project_to_table,
                           projector_to_table, quaternion_to_rotation_matrix, table_to_pixels,
                           table_to_projector)

__all__ = ['apply_homography', 'compute_camera_to_projector_homography',
           'compute_closest_point_to_rays', 'compute_pixel_rays',
           'depth_to_table', 'get_homography_from_mapping_msg', 'pixels_to_table',
           'project_to_table', 'projector_to_table', 'quaternion_to_rotation_matrix',
           'table_to_pixels', 'table_to_projector']
