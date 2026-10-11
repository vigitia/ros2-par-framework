# Written by Claude Code
"""Coordinate conversions of the PAR framework, imported as `from par_geometry import ...`."""

from .par_geometry import (apply_homography, homography_from_msg, pixels_to_table,
                           projector_to_table, rotation_matrix, table_to_projector)

__all__ = ['apply_homography', 'homography_from_msg', 'pixels_to_table', 'projector_to_table',
           'rotation_matrix', 'table_to_projector']
