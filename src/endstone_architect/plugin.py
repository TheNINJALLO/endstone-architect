"""Endstone Architect Plugin - Tag-gated build zones."""
import json
from pathlib import Path

from endstone import GameMode, Player
from endstone.plugin import Plugin
from endstone.event import event_handler, EventPriority
from endstone.event import (
    PlayerMoveEvent, PlayerJoinEvent, PlayerQuitEvent,
    BlockBreakEvent, BlockPlaceEvent, PlayerInteractEvent,
    PlayerItemHeldEvent
)
from endstone.form import ActionForm, ModalForm, TextInput, Dropdown

from endstone_architect.database import ArchitectDatabase
from endstone_architect.models import BuildArea
from endstone_architect.area_manager import AreaManager
from endstone_architect.zone_handler import ZoneHandler
from endstone_architect.dashboard.app import ArchitectDashboard


class ArchitectPlugin(Plugin):
    """Main plugin class for tag-gated build zones."""
    

    api_version = "0.11"
    
    commands = {
        "architect": {
            "description": "Open the architect zone manager",
            "usages": ["/architect", "/architect debug"],
            "permissions": ["architect.admin"]
        }
    }
    
    permissions = {
        "architect.admin": {
            "description": "Access to architect zone management",
            "default": "op"
        }
    }

    def __init__(self):
        super().__init__()
        self.db = None
        self.area_manager = None
        self.zone_handler = None
        self.dashboard = None
        self._last_positions = {}
        self._debug_mode = False  # Toggle for debug logging

    def on_load(self) -> None:
        self.logger.info("Architect plugin loading...")

    def on_enable(self) -> None:
        data_path = Path(self.data_folder)
        data_path.mkdir(parents=True, exist_ok=True)
        
        db_path = data_path / "architect.db"
        self.db = ArchitectDatabase(db_path)
        
        self.area_manager = AreaManager(self)
        self.area_manager.reload()
        
        self.zone_handler = ZoneHandler(self)
        
        # Start web dashboard
        try:
            self.dashboard = ArchitectDashboard(self, port=25687)
            self.dashboard.start()
            self.logger.info("Web dashboard started on port 25687")
        except Exception as e:
            self.logger.warning(f"Failed to start dashboard: {e}")
        
        self._start_tag_validation_task()
        
        # CRITICAL: Register event listeners - without this, no events fire!
        self.register_events(self)
        
        self.logger.info(f"Architect plugin enabled - {len(self.area_manager.get_all())} areas loaded")
        self.logger.info("Event handlers registered successfully")

    def on_disable(self) -> None:
        if self.db:
            self.db.close()
        self.logger.info("Architect plugin disabled")

    def on_command(self, sender, command, args) -> bool:
        if command.name.lower() == "architect":
            # Handle debug toggle
            if args and args[0].lower() == "debug":
                self._debug_mode = not self._debug_mode
                status = "§aENABLED" if self._debug_mode else "§cDISABLED"
                sender.send_message(f"§bArchitect debug mode: {status}")
                return True
            
            if hasattr(sender, 'send_form'):
                self._open_main_menu(sender)
            else:
                sender.send_message("§cThis command can only be used in-game")
            return True
        return False

    # ─────────────────────────────────────────────────────────────────
    # FORM MENUS
    # ─────────────────────────────────────────────────────────────────

    def _open_main_menu(self, player: Player) -> None:
        """Main architect management menu."""
        def on_submit(p, selection):
            if selection is None:
                return
            if selection == 0:
                self._open_create_area_form(p)
            elif selection == 1:
                self._open_area_list(p)
            elif selection == 2:
                self._open_preview_selector(p)

        form = ActionForm(
            title="§l§bArchitect Zones",
            content="Manage build areas and permissions",
            on_submit=on_submit
        )
        form.add_button("➕ Create New Area")
        form.add_button("📋 View All Areas")
        form.add_button("👁️ Preview Area")
        player.send_form(form)

    def _open_create_area_form(self, player: Player) -> None:
        """ModalForm for creating a new area."""
        def on_submit(p, response):
            if response is None:
                return
            try:
                values = json.loads(response) if isinstance(response, str) else response
                area_id = values[0].strip()
                area_type = "tag" if values[1] == 0 else "team"
                
                lower = values[2].strip().split()
                upper = values[3].strip().split()
                dim_idx = values[4]
                dims = ["overworld", "nether", "the_end"]
                dimension = dims[dim_idx] if dim_idx < len(dims) else "overworld"
                
                tags = [t.strip() for t in values[5].split(",") if t.strip()]
                tag_mode = "ANY" if values[6] == 0 else "ALL"
                blocked = [b.strip() for b in values[7].split(",") if b.strip()]
                
                area = BuildArea(
                    id=area_id,
                    type=area_type,
                    dimension=dimension,
                    min_x=int(lower[0]), min_y=int(lower[1]), min_z=int(lower[2]),
                    max_x=int(upper[0]), max_y=int(upper[1]), max_z=int(upper[2]),
                    enabled=True,
                    required_tags=tags,
                    tag_mode=tag_mode,
                    blocked_items=blocked
                )
                
                self.db.save_area(area)
                self.area_manager.reload()
                p.send_message(f"§aCreated area: {area_id}")
                
            except Exception as e:
                p.send_message(f"§cError creating area: {e}")

        form = ModalForm(title="§lCreate Build Area", on_submit=on_submit)
        form.add_control(TextInput(label="Area ID", placeholder="hub_expansion"))
        form.add_control(Dropdown(label="Type", options=["Tag-Gated", "Team-Based"]))
        form.add_control(TextInput(label="Lower Corner (x y z)", placeholder="-100 64 -100"))
        form.add_control(TextInput(label="Upper Corner (x y z)", placeholder="100 128 100"))
        form.add_control(Dropdown(label="Dimension", options=["overworld", "nether", "the_end"]))
        form.add_control(TextInput(label="Required Tags (comma-sep)", placeholder="architect, builder"))
        form.add_control(Dropdown(label="Tag Mode", options=["ANY", "ALL"]))
        form.add_control(TextInput(label="Blocked Items (comma-sep)", placeholder="tnt, lava_bucket"))
        player.send_form(form)

    def _open_area_list(self, player: Player) -> None:
        """Show list of all areas."""
        areas = self.area_manager.get_all()
        if not areas:
            player.send_message("§eNo areas defined yet")
            return

        def on_submit(p, selection):
            if selection is None or selection >= len(areas):
                return
            self._open_area_detail(p, areas[selection])

        form = ActionForm(
            title="§lAll Areas",
            content=f"{len(areas)} areas defined",
            on_submit=on_submit
        )
        for area in areas:
            status = "§a●" if area.enabled else "§c○"
            form.add_button(f"{status} {area.id} ({area.type})")
        player.send_form(form)

    def _open_area_detail(self, player: Player, area: BuildArea) -> None:
        """Show area details with actions."""
        def on_submit(p, selection):
            if selection is None:
                return
            if selection == 0:
                area.enabled = not area.enabled
                self.db.save_area(area)
                self.area_manager.reload()
                p.send_message(f"§aArea {area.id} {'enabled' if area.enabled else 'disabled'}")
            elif selection == 1:
                self.db.delete_area(area.id)
                self.area_manager.reload()
                p.send_message(f"§cDeleted area: {area.id}")

        content = (
            f"§7Type: §f{area.type}\n"
            f"§7Dimension: §f{area.dimension}\n"
            f"§7Bounds: §f({area.min_x},{area.min_y},{area.min_z}) to ({area.max_x},{area.max_y},{area.max_z})\n"
            f"§7Tags: §f{', '.join(area.required_tags) or 'None'}\n"
            f"§7Tag Mode: §f{area.tag_mode}\n"
            f"§7Blocked Items: §f{', '.join(area.blocked_items) or 'None'}\n"
            f"§7Enabled: §f{'Yes' if area.enabled else 'No'}"
        )

        form = ActionForm(
            title=f"§l{area.id}",
            content=content,
            on_submit=on_submit
        )
        form.add_button("🔄 Toggle Enable/Disable")
        form.add_button("🗑️ Delete Area")
        player.send_form(form)

    def _open_preview_selector(self, player: Player) -> None:
        """Select area to preview."""
        areas = self.area_manager.get_all()
        if not areas:
            player.send_message("§eNo areas to preview")
            return

        def on_submit(p, selection):
            if selection is None or selection >= len(areas):
                return
            area = areas[selection]
            p.send_message(f"§bPreviewing: {area.id}")
            p.send_message(f"§7From ({area.min_x}, {area.min_y}, {area.min_z}) to ({area.max_x}, {area.max_y}, {area.max_z})")

        form = ActionForm(
            title="§lPreview Area",
            content="Select an area to preview",
            on_submit=on_submit
        )
        for area in areas:
            form.add_button(area.id)
        player.send_form(form)

    # ─────────────────────────────────────────────────────────────────
    # EVENT HANDLERS
    # ─────────────────────────────────────────────────────────────────

    @event_handler
    def on_player_move(self, event: PlayerMoveEvent) -> None:
        """Track player position and handle area entry/exit."""
        try:
            player = event.player
            if not player:
                return
            
            # Don't process operators - they bypass zone restrictions
            # Temporarily logging is_op for debugging
            is_op = player.is_op
            
            loc = player.location
            
            # Debug: Log position info every few seconds (use a simple throttle)
            if self._debug_mode:
                player_name = player.name
                import time
                now = time.time()
                last_debug = self._last_positions.get(f"{player_name}_debug", 0)
                if now - last_debug > 5:  # Log every 5 seconds
                    self._last_positions[f"{player_name}_debug"] = now
                    
                    # Get dimension info
                    try:
                        dim_raw = loc.dimension
                        dim_name = getattr(dim_raw, 'name', str(dim_raw)).lower()
                    except Exception as de:
                        dim_name = f"error: {de}"
                    
                    # Get player tags
                    try:
                        player_tags = list(player.scoreboard_tags)
                    except Exception as te:
                        player_tags = f"error: {te}"
                    
                    # Log debug info - include is_op status!
                    self.logger.info(f"[DEBUG] Player {player_name} is_op={is_op} at ({loc.x:.1f}, {loc.y:.1f}, {loc.z:.1f}) dim={dim_name}")
                    self.logger.info(f"[DEBUG] Player tags: {player_tags}")
                    
                    # Check all areas
                    for area in self.area_manager.get_all():
                        contains = area.contains(loc.x, loc.y, loc.z, dim_name)
                        self.logger.info(f"[DEBUG] Area '{area.id}': dim={area.dimension}, enabled={area.enabled}, contains={contains}, tags={area.required_tags}")
            
            # Skip operators - they bypass zone restrictions
            if is_op:
                return
            
            current_area = self.area_manager.get_area_at(loc)
            player_current = self.zone_handler.get_player_area(player.name)

            if current_area and not player_current:
                if current_area.type == "tag":
                    has_tags = self.zone_handler.has_required_tags(player, current_area)
                    if self._debug_mode:
                        self.logger.info(f"[DEBUG] Entering area {current_area.id}, has_tags={has_tags}")
                    if has_tags:
                        event.cancelled = True
                        self.zone_handler.show_entry_form(player, current_area)
                    else:
                        # Eject unauthorized players - cancel movement and push them back out
                        event.cancelled = True
                        self.zone_handler.eject_player(player, current_area, "no_access")
                elif current_area.type == "team":
                    self.zone_handler.enter_area(player, current_area)

            elif not current_area and player_current:
                self.zone_handler.exit_area(player, "exit")

        except Exception as e:
            self.logger.error(f"Error in move handler: {e}")

    @event_handler
    def on_player_join(self, event: PlayerJoinEvent) -> None:
        """Handle rejoin inside area."""
        try:
            player = event.player
            area = self.area_manager.get_area_at(player.location)
            
            if not area or not area.enabled:
                return

            has_access = False
            if area.type == "tag":
                has_access = self.zone_handler.has_required_tags(player, area)
            elif area.type == "team":
                has_access = True

            if has_access:
                self.zone_handler.enter_area(player, area)
            else:
                self.zone_handler.eject_player(player, area, "rejoin_no_access")

        except Exception as e:
            self.logger.error(f"Error in join handler: {e}")

    @event_handler
    def on_player_quit(self, event: PlayerQuitEvent) -> None:
        """Clean up on disconnect."""
        try:
            self.zone_handler.cleanup_player(event.player.name)
        except Exception:
            pass

    @event_handler
    def on_block_place(self, event: BlockPlaceEvent) -> None:
        """Block blacklisted items."""
        try:
            player = event.player
            area_id = self.zone_handler.get_player_area(player.name)
            if not area_id:
                return

            area = self.area_manager.get_area(area_id)
            if not area:
                return

            block_type = str(event.block.type).replace("minecraft:", "").lower()
            blocked_lower = [b.lower().replace("minecraft:", "") for b in area.blocked_items]
            if block_type in blocked_lower:
                event.cancelled = True
                player.send_message(f"§c{block_type} is not allowed in this area")

        except Exception as e:
            self.logger.error(f"Error in block place handler: {e}")

    @event_handler
    def on_player_interact(self, event: PlayerInteractEvent) -> None:
        """Block container access for non-operators."""
        try:
            if event.block is None:
                return

            player = event.player
            if player.is_op:
                return

            block_type = str(event.block.type).lower()
            containers = ["chest", "barrel", "hopper", "dispenser", "dropper",
                         "furnace", "blast_furnace", "smoker", "shulker"]

            if any(c in block_type for c in containers):
                area = self.area_manager.get_area_at(event.block.location)
                if area:
                    event.cancelled = True
                    player.send_message("§cContainers are operator-only in build areas")

        except Exception as e:
            self.logger.error(f"Error in interact handler: {e}")

    @event_handler
    def on_item_held(self, event: PlayerItemHeldEvent) -> None:
        """Block blacklisted items when held in hand."""
        try:
            player = event.player
            if player.is_op:
                return
            
            area_id = self.zone_handler.get_player_area(player.name)
            if not area_id:
                return
            
            area = self.area_manager.get_area(area_id)
            if not area or not area.blocked_items:
                return
            
            # Check currently held item (API 0.11: item_in_main_hand replaces item_in_hand)
            try:
                held_item = player.inventory.item_in_main_hand
                if held_item:
                    item_type = str(held_item.type).replace("minecraft:", "").lower()
                    blocked_lower = [b.lower().replace("minecraft:", "") for b in area.blocked_items]
                    if item_type in blocked_lower:
                        # Remove the item from hand (API 0.11: writable property)
                        player.inventory.item_in_main_hand = None
                        player.send_message(f"§c{item_type} is not allowed in this area")
            except Exception as ex:
                self.logger.warning(f"Error checking held item: {ex}")
                
        except Exception as e:
            self.logger.error(f"Error in item held handler: {e}")

    # ─────────────────────────────────────────────────────────────────
    # SCHEDULED TASKS
    # ─────────────────────────────────────────────────────────────────

    def _start_tag_validation_task(self) -> None:
        """Periodically verify players still have required tags and scan for blacklisted items."""
        def check_players():
            try:
                for player in self.server.online_players:
                    if player.is_op:
                        continue  # Operators bypass restrictions
                    
                    area_id = self.zone_handler.get_player_area(player.name)
                    if not area_id:
                        continue

                    area = self.area_manager.get_area(area_id)
                    if not area:
                        continue

                    # Check if player still has required tags
                    if area.type == "tag" and not self.zone_handler.has_required_tags(player, area):
                        self.zone_handler.eject_player(player, area, "tag_removed")
                        continue
                    
                    # Scan inventory for blacklisted items and remove them
                    if area.blocked_items:
                        self._scan_and_remove_blacklisted_items(player, area)
            except Exception as e:
                self.logger.error(f"Error in player validation: {e}")

        # 10 ticks = 0.5 seconds for responsive blacklist detection
        self.server.scheduler.run_task(self, check_players, delay=10, period=10)

    def _scan_and_remove_blacklisted_items(self, player: Player, area) -> None:
        """Scan player's inventory and remove any blacklisted items."""
        try:
            inventory = player.inventory
            # Strip minecraft: prefix from blocked items for comparison
            blocked_lower = [b.lower().replace("minecraft:", "") for b in area.blocked_items]
            
            for slot in range(inventory.size):
                try:
                    item = inventory.get_item(slot)
                    if item:
                        item_type = str(item.type).replace("minecraft:", "").lower()
                        if item_type in blocked_lower:
                            inventory.set_item(slot, None)
                            player.send_message(f"§c{item_type} was removed (blacklisted)")
                except Exception:
                    continue
        except Exception as e:
            self.logger.warning(f"Error scanning inventory: {e}")

    def _reload_areas(self) -> None:
        """Reload areas from database (used by dashboard).
        
        Uses scheduler to ensure reload happens on main thread since
        dashboard calls this from Flask's background thread.
        """
        def do_reload():
            self.area_manager.reload()
            self.logger.info("Areas reloaded from dashboard")
        
        self.server.scheduler.run_task(self, do_reload, delay=0)
