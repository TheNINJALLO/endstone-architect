"""Zone entry/exit handler with tag validation."""
import time
from typing import Optional, Dict

from endstone import Player, GameMode
from endstone.form import ActionForm
from endstone.level import Location

from endstone_architect.models import BuildArea, BuildSession


class ZoneHandler:
    """Handles player entry/exit from build areas."""

    def __init__(self, plugin):
        self.plugin = plugin
        self._active_sessions: Dict[str, BuildSession] = {}
        self._player_areas: Dict[str, str] = {}
        self._pending_entry: set = set()  # Players with an open entry form

    def has_required_tags(self, player: Player, area: BuildArea) -> bool:
        """Check if player has required vanilla tags for area access."""
        try:
            player_tags = set(player.scoreboard_tags)
        except Exception:
            player_tags = set()
        
        required = set(area.required_tags)
        if not required:
            return True
        
        if area.tag_mode == "ALL":
            return required.issubset(player_tags)
        return bool(required & player_tags)

    def get_matching_tag(self, player: Player, area: BuildArea) -> Optional[str]:
        """Return first matching tag for logging purposes."""
        try:
            player_tags = set(player.scoreboard_tags)
        except Exception:
            return None
        
        for tag in area.required_tags:
            if tag in player_tags:
                return tag
        return None

    def get_player_area(self, player_name: str) -> Optional[str]:
        """Get the area ID a player is currently in."""
        return self._player_areas.get(player_name)

    def is_in_area(self, player_name: str) -> bool:
        """Check if player is currently in any area."""
        return player_name in self._player_areas

    def show_entry_form(self, player: Player, area: BuildArea) -> None:
        """Show a confirmation form before entering a build area."""
        player_name = player.name

        # Don't re-open the form if one is already pending
        if player_name in self._pending_entry:
            return
        self._pending_entry.add(player_name)

        def on_submit(p, selection):
            # Clear pending flag regardless of choice
            self._pending_entry.discard(p.name)

            if selection is None:  # Form closed / X button
                self.eject_player(p, area, "entry_declined")
                return
            if selection == 0:  # Yes
                self.enter_area(p, area)
            else:  # No
                self.eject_player(p, area, "entry_declined")

        form = ActionForm(
            title="\u00a7l\u00a76Build Area Entry",
            content=(
                "\u00a7eYou're Entering a Build Area\n"
                "\u00a7cYour Inventory Will Be Cleared\n\n"
                "\u00a7fDo you wish to continue?"
            ),
            on_submit=on_submit,
        )
        form.add_button("\u00a7aYes")
        form.add_button("\u00a7cNo")
        player.send_form(form)

    def enter_area(self, player: Player, area: BuildArea) -> None:
        """Grant creative mode, clear inventory, and give items on area entry."""
        player_name = player.name

        # Record session and area tracking immediately
        session = BuildSession(
            player_name=player_name,
            player_xuid=getattr(player, 'xuid', 'unknown'),
            area_id=area.id,
            access_type=area.type,
            tag_used=self.get_matching_tag(player, area) if area.type == "tag" else None,
            start_time=time.time()
        )
        self._active_sessions[player_name] = session
        self._player_areas[player_name] = area.id

        # Defer gamemode/inventory changes to next tick so they aren't
        # silently dropped when called inside an event handler.
        def _do_enter():
            try:
                p = self.plugin.server.get_player(player_name)
                if p is None:
                    return
                
                # Set game mode via property
                p.game_mode = GameMode.CREATIVE
                
                # Fallback: also dispatch command to ensure it sticks
                try:
                    self.plugin.server.dispatch_command(
                        self.plugin.server.command_sender,
                        f'gamemode creative "{player_name}"'
                    )
                except Exception:
                    pass
                
                # Clear inventory including armor slots
                p.inventory.clear()
                try:
                    p.inventory.helmet = None
                    p.inventory.chestplate = None
                    p.inventory.leggings = None
                    p.inventory.boots = None
                except Exception:
                    pass
                
                if area.given_items:
                    self._give_items(p, area.given_items)
                
                p.send_message(f"§aEntered build area: §f{area.id}")
                self.plugin.logger.info(
                    f"[Zone] {player_name} entered area '{area.id}' -> Creative "
                    f"(game_mode={p.game_mode})"
                )
            except Exception as e:
                self.plugin.logger.warning(f"Failed to setup player for area: {e}")
        self.plugin.server.scheduler.run_task(self.plugin, _do_enter, delay=2)

    def exit_area(self, player: Player, reason: str = "exit") -> None:
        """Restore survival mode, clear inventory, and teleport to ground on exit."""
        player_name = player.name

        # Record session end immediately
        if player_name in self._active_sessions:
            session = self._active_sessions.pop(player_name)
            session.end_time = time.time()
            session.close_reason = reason
            try:
                self.plugin.db.save_session(session)
            except Exception as e:
                self.plugin.logger.error(f"Failed to save session: {e}")

        if player_name in self._player_areas:
            del self._player_areas[player_name]

        # Defer gamemode/inventory changes to next tick so they aren't
        # silently dropped when called inside an event handler.
        def _do_exit():
            try:
                p = self.plugin.server.get_player(player_name)
                if p is None:
                    return
                
                # Clear inventory including armor slots
                p.inventory.clear()
                try:
                    p.inventory.helmet = None
                    p.inventory.chestplate = None
                    p.inventory.leggings = None
                    p.inventory.boots = None
                except Exception:
                    pass
                
                self._teleport_to_ground(p)
                
                # Set game mode via property
                p.game_mode = GameMode.SURVIVAL
                
                # Fallback: also dispatch command to ensure it sticks
                try:
                    self.plugin.server.dispatch_command(
                        self.plugin.server.command_sender,
                        f'gamemode survival "{player_name}"'
                    )
                except Exception:
                    pass
                
                p.send_message(f"§eExited build area ({reason})")
                self.plugin.logger.info(
                    f"[Zone] {player_name} exited area -> Survival "
                    f"(game_mode={p.game_mode})"
                )
            except Exception as e:
                self.plugin.logger.warning(f"Failed to restore player state: {e}")
        self.plugin.server.scheduler.run_task(self.plugin, _do_exit, delay=2)


    def eject_player(self, player: Player, area: BuildArea, reason: str) -> None:
        """Force player out of area by teleporting to world spawn.

        Unlike exit_area, this does NOT clear the player's inventory.
        The player is simply teleported to the world spawn point and
        set back to survival mode.
        """
        player_name = player.name

        # ── Session cleanup (same as exit_area, minus the inventory wipe) ──
        if player_name in self._active_sessions:
            session = self._active_sessions.pop(player_name)
            session.end_time = time.time()
            session.close_reason = reason
            try:
                self.plugin.db.save_session(session)
            except Exception as e:
                self.plugin.logger.error(f"Failed to save session: {e}")

        if player_name in self._player_areas:
            del self._player_areas[player_name]

        # ── Deferred teleport + gamemode restore (next tick) ──
        def _do_eject():
            try:
                p = self.plugin.server.get_player(player_name)
                if p is None:
                    return

                # Teleport to world spawn (inventory is NOT touched)
                try:
                    self.plugin.server.dispatch_command(
                        self.plugin.server.command_sender,
                        f'tp "{player_name}" 438 97 757'
                    )
                except Exception as tp_err:
                    self.plugin.logger.error(f"Failed to tp to spawn: {tp_err}")

                # Restore survival mode
                p.game_mode = GameMode.SURVIVAL
                try:
                    self.plugin.server.dispatch_command(
                        self.plugin.server.command_sender,
                        f'gamemode survival "{player_name}"'
                    )
                except Exception:
                    pass

                self.plugin.logger.info(
                    f"[Zone] {player_name} ejected from '{area.id}' -> "
                    f"world spawn (reason={reason})"
                )
            except Exception as e:
                self.plugin.logger.warning(f"Failed to eject player: {e}")

        self.plugin.server.scheduler.run_task(self.plugin, _do_eject, delay=2)

        # Provide clear feedback on why the player was ejected
        if reason == "no_access":
            player.send_message("§cYou don't have the required tag to enter this area")
        elif reason == "rejoin_no_access":
            player.send_message("§cYou don't have access to this area and have been moved outside")
        else:
            player.send_message(f"§cRemoved from build area: {reason}")

    def _teleport_to_ground(self, player: Player) -> None:
        """Find and teleport player to closest ground block below them."""
        try:
            loc = player.location
            dim = player.dimension
            x, z = int(loc.x), int(loc.z)
            start_y = int(loc.y)
            
            # Search downward for a solid block to stand on
            ground_y = None
            for y in range(start_y, max(start_y - 384, -64), -1):
                try:
                    block = dim.get_block_at(x, y, z)
                    if block:
                        block_type = str(block.type).lower()
                        # Skip air and non-solid blocks
                        if "air" not in block_type and block_type != "":
                            # Check if block above is air (can stand there)
                            block_above = dim.get_block_at(x, y + 1, z)
                            if block_above:
                                above_type = str(block_above.type).lower()
                                if "air" in above_type:
                                    ground_y = y + 1
                                    break
                except Exception:
                    continue
            
            if ground_y is not None:
                safe_loc = Location(
                    dim,
                    float(x) + 0.5, float(ground_y), float(z) + 0.5,
                    loc.pitch, loc.yaw
                )
                player.teleport(safe_loc)
                self.plugin.logger.info(f"Teleported {player.name} to ground at Y={ground_y}")
        except Exception as e:
            self.plugin.logger.warning(f"Failed to teleport to ground: {e}")

    def _give_items(self, player: Player, items: list) -> None:
        """Give specified items to player using /give command."""
        for item in items:
            try:
                # Parse item string - supports "item_name" or "item_name:count"
                item_str = item.strip()
                if not item_str:
                    continue
                
                parts = item_str.rsplit(":", 1)
                # Check if last part is a count (number)
                if len(parts) == 2 and parts[1].isdigit():
                    item_id = parts[0]
                    count = int(parts[1])
                else:
                    item_id = item_str
                    count = 1
                
                # Ensure item has namespace
                if ":" not in item_id:
                    item_id = f"minecraft:{item_id}"
                
                # Execute give command via server
                cmd = f'give "{player.name}" {item_id} {count}'
                self.plugin.server.dispatch_command(self.plugin.server.command_sender, cmd)
                self.plugin.logger.info(f"Gave {player.name} {count}x {item_id}")
            except Exception as e:
                self.plugin.logger.warning(f"Failed to give item '{item}': {e}")

    def cleanup_player(self, player_name: str) -> None:
        """Clean up player data on disconnect."""
        self._pending_entry.discard(player_name)

        if player_name in self._active_sessions:
            session = self._active_sessions.pop(player_name)
            session.end_time = time.time()
            session.close_reason = "disconnect"
            try:
                self.plugin.db.save_session(session)
            except Exception:
                pass
        
        if player_name in self._player_areas:
            del self._player_areas[player_name]

