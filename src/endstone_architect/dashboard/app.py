"""Aurora-themed Flask web dashboard for Architect zones."""
import threading
from flask import Flask, render_template_string, jsonify, request

from endstone_architect.models import BuildArea


DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Architect Dashboard</title>
    <style>
        :root {
            --bg-primary: #0a0e17;
            --bg-secondary: #111827;
            --bg-card: rgba(17, 24, 39, 0.8);
            --accent-cyan: #06b6d4;
            --accent-purple: #8b5cf6;
            --accent-green: #10b981;
            --accent-red: #ef4444;
            --accent-yellow: #f59e0b;
            --text-primary: #f9fafb;
            --text-secondary: #9ca3af;
            --border-color: rgba(6, 182, 212, 0.2);
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, var(--bg-primary) 0%, #0f172a 100%);
            color: var(--text-primary);
            min-height: 100vh;
            padding: 2rem;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 {
            font-size: 2rem;
            background: linear-gradient(90deg, var(--accent-cyan), var(--accent-purple));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 2rem;
        }
        .card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 1rem;
            backdrop-filter: blur(10px);
        }
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
        }
        .card-title { font-size: 1.25rem; font-weight: 600; }
        .badge {
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 500;
            margin-left: 0.5rem;
        }
        .badge-enabled { background: rgba(16, 185, 129, 0.2); color: var(--accent-green); }
        .badge-disabled { background: rgba(239, 68, 68, 0.2); color: var(--accent-red); }
        .badge-tag { background: rgba(139, 92, 246, 0.2); color: var(--accent-purple); }
        .badge-team { background: rgba(6, 182, 212, 0.2); color: var(--accent-cyan); }
        .meta { color: var(--text-secondary); font-size: 0.875rem; margin-bottom: 0.5rem; }
        .btn {
            padding: 0.5rem 1rem;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.875rem;
            transition: all 0.2s;
            margin-right: 0.5rem;
        }
        .btn-danger { background: var(--accent-red); color: white; }
        .btn-primary { background: var(--accent-cyan); color: black; }
        .btn-secondary { background: var(--accent-purple); color: white; }
        .btn-warning { background: var(--accent-yellow); color: black; }
        .btn:hover { opacity: 0.8; }
        .section-title { font-size: 1.5rem; margin: 2rem 0 1rem; color: var(--text-primary); }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 0.75rem; text-align: left; border-bottom: 1px solid var(--border-color); }
        th { color: var(--text-secondary); font-weight: 500; }
        .empty { text-align: center; color: var(--text-secondary); padding: 2rem; }
        
        /* Form styles */
        .form-group { margin-bottom: 1rem; }
        .form-group label { display: block; margin-bottom: 0.5rem; color: var(--text-secondary); font-size: 0.875rem; }
        .form-group input, .form-group select {
            width: 100%;
            padding: 0.75rem;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            background: var(--bg-secondary);
            color: var(--text-primary);
            font-size: 0.875rem;
        }
        .form-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1rem; }
        .form-row-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
        
        /* Modal styles */
        .modal {
            display: none;
            position: fixed;
            top: 0; left: 0;
            width: 100%; height: 100%;
            background: rgba(0,0,0,0.8);
            z-index: 1000;
            align-items: center;
            justify-content: center;
        }
        .modal.active { display: flex; }
        .modal-content {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 2rem;
            width: 90%;
            max-width: 600px;
            max-height: 90vh;
            overflow-y: auto;
        }
        .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; }
        .modal-close { background: none; border: none; color: var(--text-secondary); font-size: 1.5rem; cursor: pointer; }
        .btn-actions { display: flex; gap: 0.5rem; margin-top: 0.5rem; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚡ Architect Dashboard</h1>
        
        <!-- Create Area Form -->
        <div class="card">
            <div class="card-title" style="margin-bottom: 1rem;">➕ Create New Area</div>
            <form id="createForm">
                <div class="form-row-2">
                    <div class="form-group">
                        <label>Area ID</label>
                        <input type="text" name="id" placeholder="hub_expansion" required>
                    </div>
                    <div class="form-group">
                        <label>Type</label>
                        <select name="type">
                            <option value="tag">Tag-Gated</option>
                            <option value="team">Team-Based</option>
                        </select>
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>Min X</label>
                        <input type="number" name="min_x" required>
                    </div>
                    <div class="form-group">
                        <label>Min Y</label>
                        <input type="number" name="min_y" required>
                    </div>
                    <div class="form-group">
                        <label>Min Z</label>
                        <input type="number" name="min_z" required>
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>Max X</label>
                        <input type="number" name="max_x" required>
                    </div>
                    <div class="form-group">
                        <label>Max Y</label>
                        <input type="number" name="max_y" required>
                    </div>
                    <div class="form-group">
                        <label>Max Z</label>
                        <input type="number" name="max_z" required>
                    </div>
                </div>
                <div class="form-row-2">
                    <div class="form-group">
                        <label>Dimension</label>
                        <select name="dimension">
                            <option value="overworld">Overworld</option>
                            <option value="nether">Nether</option>
                            <option value="the_end">The End</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Tag Mode</label>
                        <select name="tag_mode">
                            <option value="ANY">ANY (at least one)</option>
                            <option value="ALL">ALL (must have all)</option>
                        </select>
                    </div>
                </div>
                <div class="form-group">
                    <label>Required Tags (comma-separated)</label>
                    <input type="text" name="required_tags" placeholder="architect, builder">
                </div>
                <div class="form-group">
                    <label>Blocked Items (comma-separated)</label>
                    <input type="text" name="blocked_items" placeholder="tnt, lava_bucket, flint_and_steel">
                </div>
                <div class="form-group">
                    <label>Given Items on Entry (comma-separated, add :count for quantity)</label>
                    <input type="text" name="given_items" placeholder="diamond_pickaxe, oak_planks:64, ninjos:custom_tool">
                </div>
                <button type="submit" class="btn btn-primary">Create Area</button>
            </form>
        </div>
        
        <h2 class="section-title">Existing Areas</h2>
        <div id="areas"></div>
        
        <h2 class="section-title">Recent Sessions</h2>
        <div class="card">
            <table>
                <thead>
                    <tr>
                        <th>Player</th>
                        <th>Area</th>
                        <th>Type</th>
                        <th>Tag Used</th>
                        <th>Duration</th>
                        <th>Reason</th>
                    </tr>
                </thead>
                <tbody id="sessions"></tbody>
            </table>
        </div>
    </div>
    
    <!-- Edit Modal -->
    <div class="modal" id="editModal">
        <div class="modal-content">
            <div class="modal-header">
                <span class="card-title">Edit Area</span>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <form id="editForm">
                <input type="hidden" name="id">
                <div class="form-row-2">
                    <div class="form-group">
                        <label>Type</label>
                        <select name="type">
                            <option value="tag">Tag-Gated</option>
                            <option value="team">Team-Based</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Enabled</label>
                        <select name="enabled">
                            <option value="true">Yes</option>
                            <option value="false">No</option>
                        </select>
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>Min X</label>
                        <input type="number" name="min_x" required>
                    </div>
                    <div class="form-group">
                        <label>Min Y</label>
                        <input type="number" name="min_y" required>
                    </div>
                    <div class="form-group">
                        <label>Min Z</label>
                        <input type="number" name="min_z" required>
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>Max X</label>
                        <input type="number" name="max_x" required>
                    </div>
                    <div class="form-group">
                        <label>Max Y</label>
                        <input type="number" name="max_y" required>
                    </div>
                    <div class="form-group">
                        <label>Max Z</label>
                        <input type="number" name="max_z" required>
                    </div>
                </div>
                <div class="form-row-2">
                    <div class="form-group">
                        <label>Dimension</label>
                        <select name="dimension">
                            <option value="overworld">Overworld</option>
                            <option value="nether">Nether</option>
                            <option value="the_end">The End</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Tag Mode</label>
                        <select name="tag_mode">
                            <option value="ANY">ANY</option>
                            <option value="ALL">ALL</option>
                        </select>
                    </div>
                </div>
                <div class="form-group">
                    <label>Required Tags (comma-separated)</label>
                    <input type="text" name="required_tags">
                </div>
                <div class="form-group">
                    <label>Blocked Items (comma-separated)</label>
                    <input type="text" name="blocked_items">
                </div>
                <div class="form-group">
                    <label>Given Items on Entry (comma-separated, add :count for quantity)</label>
                    <input type="text" name="given_items">
                </div>
                <button type="submit" class="btn btn-primary">Save Changes</button>
            </form>
        </div>
    </div>
    
    <script>
        // Create area
        document.getElementById('createForm').onsubmit = async (e) => {
            e.preventDefault();
            const form = e.target;
            const data = {
                id: form.id.value,
                type: form.type.value,
                dimension: form.dimension.value,
                min_x: parseInt(form.min_x.value),
                min_y: parseInt(form.min_y.value),
                min_z: parseInt(form.min_z.value),
                max_x: parseInt(form.max_x.value),
                max_y: parseInt(form.max_y.value),
                max_z: parseInt(form.max_z.value),
                enabled: true,
                tag_mode: form.tag_mode.value,
                required_tags: form.required_tags.value.split(',').map(s => s.trim()).filter(s => s),
                blocked_items: form.blocked_items.value.split(',').map(s => s.trim()).filter(s => s),
                given_items: form.given_items.value.split(',').map(s => s.trim()).filter(s => s)
            };
            await fetch('/api/areas', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            form.reset();
            loadAreas();
        };
        
        // Edit form submit
        document.getElementById('editForm').onsubmit = async (e) => {
            e.preventDefault();
            const form = e.target;
            const data = {
                id: form.id.value,
                type: form.type.value,
                dimension: form.dimension.value,
                min_x: parseInt(form.min_x.value),
                min_y: parseInt(form.min_y.value),
                min_z: parseInt(form.min_z.value),
                max_x: parseInt(form.max_x.value),
                max_y: parseInt(form.max_y.value),
                max_z: parseInt(form.max_z.value),
                enabled: form.enabled.value === 'true',
                tag_mode: form.tag_mode.value,
                required_tags: form.required_tags.value.split(',').map(s => s.trim()).filter(s => s),
                blocked_items: form.blocked_items.value.split(',').map(s => s.trim()).filter(s => s),
                given_items: form.given_items.value.split(',').map(s => s.trim()).filter(s => s)
            };
            await fetch('/api/areas/' + form.id.value, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            closeModal();
            loadAreas();
        };
        
        function openEdit(area) {
            const form = document.getElementById('editForm');
            form.id.value = area.id;
            form.type.value = area.type;
            form.enabled.value = area.enabled.toString();
            form.dimension.value = area.dimension;
            form.min_x.value = area.min_x;
            form.min_y.value = area.min_y;
            form.min_z.value = area.min_z;
            form.max_x.value = area.max_x;
            form.max_y.value = area.max_y;
            form.max_z.value = area.max_z;
            form.tag_mode.value = area.tag_mode;
            form.required_tags.value = area.required_tags.join(', ');
            form.blocked_items.value = area.blocked_items.join(', ');
            form.given_items.value = (area.given_items || []).join(', ');
            document.getElementById('editModal').classList.add('active');
        }
        
        function closeModal() {
            document.getElementById('editModal').classList.remove('active');
        }
        
        let areasCache = [];
        
        async function loadAreas() {
            const res = await fetch('/api/areas');
            areasCache = await res.json();
            const container = document.getElementById('areas');
            
            if (areasCache.length === 0) {
                container.innerHTML = '<div class="card empty">No areas defined</div>';
                return;
            }
            
            container.innerHTML = areasCache.map((area, idx) => `
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">${area.id}</span>
                        <div>
                            <span class="badge badge-${area.type}">${area.type}</span>
                            <span class="badge ${area.enabled ? 'badge-enabled' : 'badge-disabled'}">
                                ${area.enabled ? 'Enabled' : 'Disabled'}
                            </span>
                        </div>
                    </div>
                    <div class="meta">
                        <strong>Dimension:</strong> ${area.dimension} | 
                        <strong>Bounds:</strong> (${area.min_x}, ${area.min_y}, ${area.min_z}) to (${area.max_x}, ${area.max_y}, ${area.max_z})
                    </div>
                    <div class="meta">
                        <strong>Tag Mode:</strong> ${area.tag_mode} | 
                        <strong>Tags:</strong> ${area.required_tags.length > 0 ? area.required_tags.join(', ') : 'None'}
                    </div>
                    <div class="meta">
                        <strong>Blocked Items:</strong> ${area.blocked_items.length > 0 ? area.blocked_items.join(', ') : 'None'}
                    </div>
                    <div class="meta">
                        <strong>Given Items:</strong> ${(area.given_items || []).length > 0 ? area.given_items.join(', ') : 'None'}
                    </div>
                    <div class="btn-actions">
                        <button class="btn btn-secondary" onclick="openEdit(areasCache[${idx}])">✏️ Edit</button>
                        <button class="btn btn-warning" onclick="toggleArea('${area.id}', ${!area.enabled})">${area.enabled ? '⏸️ Disable' : '▶️ Enable'}</button>
                        <button class="btn btn-danger" onclick="deleteArea('${area.id}')">🗑️ Delete</button>
                    </div>
                </div>
            `).join('');
        }
        
        async function loadSessions() {
            const res = await fetch('/api/sessions');
            const sessions = await res.json();
            const tbody = document.getElementById('sessions');
            
            if (sessions.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="empty">No sessions recorded</td></tr>';
                return;
            }
            
            tbody.innerHTML = sessions.map(s => {
                const duration = s.end_time && s.start_time 
                    ? Math.round((s.end_time - s.start_time) / 60) + 'm'
                    : 'Active';
                return `
                    <tr>
                        <td>${s.player_name}</td>
                        <td>${s.area_id}</td>
                        <td>${s.access_type}</td>
                        <td>${s.tag_used || '-'}</td>
                        <td>${duration}</td>
                        <td>${s.close_reason || '-'}</td>
                    </tr>
                `;
            }).join('');
        }
        
        async function deleteArea(id) {
            if (!confirm('Delete area ' + id + '?')) return;
            await fetch('/api/areas/' + id, { method: 'DELETE' });
            loadAreas();
        }
        
        async function toggleArea(id, enabled) {
            const area = areasCache.find(a => a.id === id);
            if (!area) return;
            area.enabled = enabled;
            await fetch('/api/areas/' + id, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(area)
            });
            loadAreas();
        }
        
        loadAreas();
        loadSessions();
        setInterval(loadSessions, 30000);
    </script>
</body>
</html>
"""



class ArchitectDashboard:
    """Flask web dashboard for architect zone management."""

    def __init__(self, plugin, host: str = "0.0.0.0", port: int = 8090):
        self.plugin = plugin
        self.host = host
        self.port = port
        self.app = Flask(__name__)
        self._thread = None
        self._setup_routes()

    def _setup_routes(self):
        @self.app.route("/")
        def index():
            return render_template_string(DASHBOARD_HTML)

        @self.app.route("/api/areas")
        def get_areas():
            areas = self.plugin.db.get_all_areas()
            return jsonify([{
                "id": a.id,
                "type": a.type,
                "dimension": a.dimension,
                "min_x": a.min_x, "min_y": a.min_y, "min_z": a.min_z,
                "max_x": a.max_x, "max_y": a.max_y, "max_z": a.max_z,
                "enabled": a.enabled,
                "required_tags": a.required_tags,
                "tag_mode": a.tag_mode,
                "blocked_items": a.blocked_items,
                "given_items": a.given_items
            } for a in areas])

        @self.app.route("/api/areas", methods=["POST"])
        def create_area():
            try:
                data = request.json
                area = BuildArea(
                    id=data["id"],
                    type=data.get("type", "tag"),
                    dimension=data.get("dimension", "overworld"),
                    min_x=data["min_x"], min_y=data["min_y"], min_z=data["min_z"],
                    max_x=data["max_x"], max_y=data["max_y"], max_z=data["max_z"],
                    enabled=data.get("enabled", True),
                    required_tags=data.get("required_tags", []),
                    tag_mode=data.get("tag_mode", "ANY"),
                    blocked_items=data.get("blocked_items", []),
                    given_items=data.get("given_items", [])
                )
                self.plugin.db.save_area(area)
                self.plugin._reload_areas()
                return jsonify({"status": "ok"})
            except Exception as e:
                return jsonify({"status": "error", "message": str(e)}), 400

        @self.app.route("/api/areas/<area_id>", methods=["DELETE"])
        def delete_area(area_id):
            try:
                self.plugin.db.delete_area(area_id)
                self.plugin._reload_areas()
                return jsonify({"status": "ok"})
            except Exception as e:
                return jsonify({"status": "error", "message": str(e)}), 400

        @self.app.route("/api/areas/<area_id>", methods=["PUT"])
        def update_area(area_id):
            try:
                data = request.json
                area = BuildArea(
                    id=area_id,
                    type=data.get("type", "tag"),
                    dimension=data.get("dimension", "overworld"),
                    min_x=data["min_x"], min_y=data["min_y"], min_z=data["min_z"],
                    max_x=data["max_x"], max_y=data["max_y"], max_z=data["max_z"],
                    enabled=data.get("enabled", True),
                    required_tags=data.get("required_tags", []),
                    tag_mode=data.get("tag_mode", "ANY"),
                    blocked_items=data.get("blocked_items", []),
                    given_items=data.get("given_items", [])
                )
                self.plugin.db.save_area(area)
                self.plugin._reload_areas()
                return jsonify({"status": "ok"})
            except Exception as e:
                return jsonify({"status": "error", "message": str(e)}), 400

        @self.app.route("/api/sessions")
        def get_sessions():
            sessions = self.plugin.db.get_recent_sessions(100)
            return jsonify(sessions)

    def start(self):
        """Start dashboard in background thread."""
        self._thread = threading.Thread(
            target=lambda: self.app.run(
                host=self.host,
                port=self.port,
                debug=False,
                use_reloader=False
            ),
            daemon=True
        )
        self._thread.start()
        return self._thread
