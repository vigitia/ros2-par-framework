# Written by Claude Code
"""Coordinate conversions of the PAR framework, imported as `from par_geometry import ...`."""

from .par_geometry import (apply_homography, camera_pixels_to_surface,
                           compute_camera_to_projector_homography, compute_closest_point_to_rays,
                           compute_pixel_rays, depth_image_to_surface,
                           follow_projector_rays_to_surface, get_homography_from_mapping_msg,
                           projector_pixels_to_surface, quaternion_to_rotation_matrix,
                           surface_to_camera_pixels, surface_to_projector_pixels)

__all__ = ['apply_homography', 'camera_pixels_to_surface',
           'compute_camera_to_projector_homography', 'compute_closest_point_to_rays',
           'compute_pixel_rays', 'depth_image_to_surface', 'follow_projector_rays_to_surface',
           'get_homography_from_mapping_msg', 'projector_pixels_to_surface',
           'quaternion_to_rotation_matrix', 'surface_to_camera_pixels',
           'surface_to_projector_pixels']
