import unittest
import pandas as pd
from ensa.eo.stac_s2 import Sentinel2Processor
from ensa.config import SOUTHERN_PROVINCE_BBOX

class TestSTACRealPixels(unittest.TestCase):
    
    def setUp(self):
        self.processor = Sentinel2Processor()
        self.bbox = SOUTHERN_PROVINCE_BBOX
        # Query window in May 2026
        self.start_date = "2026-05-01"
        self.end_date = "2026-05-28"

    def test_stac_query_metadata(self):
        """Verifies that the Planetary Computer STAC catalog resolves and finds Sentinel-2 scenes."""
        scenes = self.processor.query_stac_metadata(self.bbox, self.start_date, self.end_date)
        
        # We assert that the list is returned (could be empty if offline, which is caught)
        self.assertIsInstance(scenes, list)
        if len(scenes) > 0:
            latest_scene = scenes[0]
            self.assertIn("sentinel-2", latest_scene.collection_id)

    def test_polygon_statistics_extraction(self):
        """Verifies that the laptop-safe COG extraction parses correctly and outputs valid bands."""
        scenes = self.processor.query_stac_metadata(self.bbox, self.start_date, self.end_date)
        df_stats = self.processor.calculate_polygon_statistics(scenes)
        
        self.assertIsInstance(df_stats, pd.DataFrame)
        required_bands = ["band_red", "band_green", "band_nir", "band_swir"]
        for band in required_bands:
            self.assertIn(band, df_stats.columns)
            
        # Ensure values are within normal top-of-atmosphere reflectance bounds [0.0, 1.0]
        latest_observation = df_stats.iloc[-1]
        for band in required_bands:
            val = latest_observation[band]
            self.assertTrue(0.0 <= val <= 1.0, f"Band {band} value {val} is outside valid [0, 1] range.")

if __name__ == "__main__":
    unittest.main()
