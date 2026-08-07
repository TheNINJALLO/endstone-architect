"""Spatial lookup and area management."""
from typing import Optional, List

from endstone.level import Location

from endstone_architect.models import BuildArea


class AreaManager:
    """Manages area lookup and caching."""

    def __init__(self, plugin):
        self.plugin = plugin
        self._areas: List[BuildArea] = []

    def reload(self) -> None:
        """Reload areas from database."""
        try:
            self._areas = self.plugin.db.get_all_areas()
            self.plugin.logger.info(f"Loaded {len(self._areas)} build areas")
        except Exception as e:
            self.plugin.logger.error(f"Failed to reload areas: {e}")
            self._areas = []

    def get_all(self) -> List[BuildArea]:
        """Get all areas."""
        return self._areas

    def get_area(self, area_id: str) -> Optional[BuildArea]:
        """Get area by ID."""
        for area in self._areas:
            if area.id == area_id:
                return area
        return None

    def get_area_at(self, location: Location) -> Optional[BuildArea]:
        """Get the area at a specific location."""
        try:
            x, y, z = location.x, location.y, location.z
            dim = getattr(location.dimension, 'name', str(location.dimension)).lower()
        except Exception:
            return None

        for area in self._areas:
            if area.enabled and area.contains(x, y, z, dim):
                return area
        return None

    def get_area_at_coords(self, x: float, y: float, z: float, dimension: str) -> Optional[BuildArea]:
        """Get area at specific coordinates."""
        dim = dimension.lower()
        for area in self._areas:
            if area.enabled and area.contains(x, y, z, dim):
                return area
        return None
