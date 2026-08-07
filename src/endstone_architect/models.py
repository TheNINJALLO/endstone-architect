"""Data models for architect build zones."""
from dataclasses import dataclass, field
from typing import Literal, List, Optional


@dataclass
class BuildArea:
    """Represents a protected build area."""
    id: str
    type: Literal["team", "tag"]
    dimension: str
    min_x: int
    min_y: int
    min_z: int
    max_x: int
    max_y: int
    max_z: int
    enabled: bool = True
    required_tags: List[str] = field(default_factory=list)
    tag_mode: Literal["ANY", "ALL"] = "ANY"
    blocked_items: List[str] = field(default_factory=list)
    given_items: List[str] = field(default_factory=list)  # Items to give on entry

    @staticmethod
    def _normalize_dimension(dim: str) -> str:
        """Normalize dimension name for comparison."""
        d = dim.lower().replace("minecraft:", "")
        # Handle "the_end" vs "end" variations
        if d in ("end", "the_end"):
            return "the_end"
        return d

    def contains(self, x: float, y: float, z: float, dim: str) -> bool:
        """Check if a position is inside this area."""
        norm_dim = self._normalize_dimension(dim)
        norm_area = self._normalize_dimension(self.dimension)
        if norm_dim != norm_area:
            return False
        # Handle swapped min/max values (user may enter corners in any order)
        x1, x2 = min(self.min_x, self.max_x), max(self.min_x, self.max_x)
        y1, y2 = min(self.min_y, self.max_y), max(self.min_y, self.max_y)
        z1, z2 = min(self.min_z, self.max_z), max(self.min_z, self.max_z)
        return (
            x1 <= x <= x2 and
            y1 <= y <= y2 and
            z1 <= z <= z2
        )


@dataclass
class BuildSession:
    """Tracks a player's build session in an area."""
    player_name: str
    player_xuid: str
    area_id: str
    access_type: Literal["team", "tag"]
    tag_used: Optional[str]
    start_time: float
    end_time: Optional[float] = None
    close_reason: Optional[str] = None
