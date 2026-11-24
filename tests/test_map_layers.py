import unittest
from unittest.mock import patch
import folium

from app import add_map_layers, get_draw_map_initial_location


class MapLayersTests(unittest.TestCase):
    def test_add_map_layers_registers_labeled_and_hybrid_layers(self):
        m = folium.Map(location=[28.6139, 77.2090], zoom_start=10, tiles=None)
        add_map_layers(m)

        tile_layers = [child for child in m._children.values() if isinstance(child, folium.TileLayer)]
        self.assertGreaterEqual(len(tile_layers), 7, "Should register multiple base and overlay tile layers")

        layer_names = [tl.tile_name for tl in tile_layers]

        # 1. Primary default base layer must be Satellite + Labels (Hybrid)
        self.assertIn("🛰️ Satellite + Labels (Hybrid)", layer_names)
        self.assertEqual(tile_layers[0].tile_name, "🛰️ Satellite + Labels (Hybrid)", "First layer must be Satellite + Labels")

        # 2. Detailed OpenStreetMap
        self.assertIn("🗺️ OpenStreetMap (Villages & Roads)", layer_names)

        # 3. Google Maps Standard Roadmap
        self.assertIn("📍 Google Maps (Roads & Labels)", layer_names)

        # 4. Pure optical satellite imagery
        self.assertIn("🛰️ Satellite View (Pure Optical, Sub-Meter)", layer_names)

        # 5. CartoDB Voyager colored & labeled basemap
        self.assertIn("🎨 CartoDB Voyager (Colored & Labeled)", layer_names)

        # 6. Light & Dark mode
        self.assertIn("☀️ Day / Light Mode", layer_names)
        self.assertIn("🌙 Night / Dark Mode", layer_names)

        # 7. Check overlays
        overlay_layers = [tl for tl in tile_layers if tl.overlay]
        overlay_names = [tl.tile_name for tl in overlay_layers]
        self.assertIn("🏷️ Village & Place Names Overlay", overlay_names)
        self.assertIn("🛣️ Roads & Highways Overlay", overlay_names)

        # 8. LayerControl present
        layer_controls = [child for child in m._children.values() if isinstance(child, folium.LayerControl)]
        self.assertEqual(len(layer_controls), 1, "Should have a LayerControl added")

    def test_map_renders_valid_html_with_tile_urls(self):
        m = folium.Map(location=[29.6857, 76.9905], zoom_start=14, tiles=None)
        add_map_layers(m)
        html = m._repr_html_()
        self.assertIn("mt1.google.com/vt/lyrs=y", html)
        self.assertIn("tile.openstreetmap.org", html)
        self.assertIn("arcgisonline.com", html)

    @patch("streamlit.session_state", {})
    def test_get_draw_map_initial_location_default(self):
        coords, zoom = get_draw_map_initial_location()
        self.assertAlmostEqual(coords[0], 29.6857, places=2)
        self.assertAlmostEqual(coords[1], 76.9905, places=2)
        self.assertEqual(zoom, 10)

    @patch("streamlit.session_state", {"my_location_coords": (30.9010, 75.8573, "Device GPS")})
    def test_get_draw_map_initial_location_with_gps(self):
        coords, zoom = get_draw_map_initial_location()
        self.assertAlmostEqual(coords[0], 30.9010, places=4)
        self.assertAlmostEqual(coords[1], 75.8573, places=4)
        self.assertEqual(zoom, 14)

    @patch("streamlit.session_state", {
        "draw_map_focus_target": [19.9975, 73.7898],
        "draw_map_focus_zoom": 13,
    })
    def test_get_draw_map_initial_location_with_focus_target(self):
        coords, zoom = get_draw_map_initial_location()
        self.assertAlmostEqual(coords[0], 19.9975, places=4)
        self.assertAlmostEqual(coords[1], 73.7898, places=4)
        self.assertEqual(zoom, 13)

    @patch("streamlit.session_state", {
        "map_drawings": [{
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[77.048, 29.748], [77.052, 29.748], [77.052, 29.752], [77.048, 29.752], [77.048, 29.748]]],
            },
        }]
    })
    def test_get_draw_map_initial_location_with_existing_drawing(self):
        coords, zoom = get_draw_map_initial_location()
        self.assertAlmostEqual(coords[0], 29.750, places=3)
        self.assertAlmostEqual(coords[1], 77.050, places=3)
        self.assertEqual(zoom, 15)


if __name__ == "__main__":
    unittest.main()
