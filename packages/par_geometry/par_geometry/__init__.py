# Written by Claude Code
"""Coordinate conversions of the PAR framework, imported as `from par_geometry import ...`."""

from .par_geometry import (apply_homography, compute_pixel_rays, depth_to_table,
                           homography_from_msg, intersect_rays, pixels_to_table, project_to_table,
                           projector_to_table, quaternion_to_rotation_matrix, table_to_pixels,
                           table_to_projector)

__all__ = ['apply_homography', 'compute_pixel_rays', 'depth_to_table', 'homography_from_msg',
           'intersect_rays', 'pixels_to_table', 'project_to_table', 'projector_to_table',
           'quaternion_to_rotation_matrix', 'table_to_pixels', 'table_to_projector']
