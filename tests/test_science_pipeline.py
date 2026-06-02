import unittest
import numpy as np
import pandas as pd
from ensa.math.indices import calculate_ndvi, calculate_ndwi, calculate_vci
from ensa.math.meteorology import calculate_spi3, calculate_spei
from ensa.math.pdsi import calculate_pdsi_forecast
from ensa.core.gatekeeper import calculate_forecast_confidence, should_trigger_cloud_review, derive_dynamic_correlation_weights

class TestENSASciencePipeline(unittest.TestCase):
    
    def test_vegetation_indices(self):
        """Verifies Rouse 1974 NDVI & McFeeters 1996 NDWI mathematical correct boundaries."""
        nir = 0.45
        red = 0.08
        green = 0.12
        
        ndvi = calculate_ndvi(nir, red)
        ndwi = calculate_ndwi(green, nir)
        
        # Expected NDVI: (0.45 - 0.08) / (0.45 + 0.08) = 0.37 / 0.53 = 0.6981
        self.assertAlmostEqual(ndvi, 0.6981132, places=4)
        
        # Expected NDWI: (0.12 - 0.45) / (0.12 + 0.45) = -0.33 / 0.57 = -0.5789
        self.assertAlmostEqual(ndwi, -0.5789473, places=4)

    def test_kogan_vci(self):
        """Verifies Kogan 1995 VCI normalized range scaling with floating point tolerance."""
        ndvi_series = pd.Series([0.10, 0.20, 0.30, 0.40, 0.50])
        vci = calculate_vci(ndvi_series)
        
        self.assertAlmostEqual(vci.iloc[0], 0.0, places=3)    # Min value
        self.assertAlmostEqual(vci.iloc[-1], 100.0, places=3) # Max value
        self.assertAlmostEqual(vci.iloc[2], 50.0, places=3)   # Median value

    def test_pdsi_forecaster(self):
        """Verifies Palmer 1965 PDSI accumulation thresholds."""
        # Moderate dry anomaly
        out_mod = calculate_pdsi_forecast(precip_anomaly_pct=-25.0, temp_anomaly_c=1.5, antecedent_pdsi=-1.0)
        self.assertEqual(out_mod["alert_level"], "Moderate Stress")
        
        # Extreme dry anomaly (lower antecedent PDSI to cross -3.0 threshold)
        out_ext = calculate_pdsi_forecast(precip_anomaly_pct=-55.0, temp_anomaly_c=3.5, antecedent_pdsi=-3.2)
        self.assertEqual(out_ext["alert_level"], "Extreme Drought")

    def test_gatekeeper_routing(self):
        """Verifies confidence score thresholds triggers cloud calibration review."""
        # High confidence (agreeing wet signals)
        c_high = calculate_forecast_confidence(spei_val=1.2, vci_val=85.0, cloud_free_fraction=0.95)
        self.assertFalse(should_trigger_cloud_review(c_high))
        
        # Low confidence (conflicting indicators - dry forecast but high vegetation greenness)
        c_low = calculate_forecast_confidence(spei_val=-2.2, vci_val=90.0, cloud_free_fraction=0.90)
        self.assertTrue(should_trigger_cloud_review(c_low))

    def test_correlation_weight_fusion(self):
        """Verifies dynamic correlation weighting fusion vs ensemble fallback."""
        # Case 1: Strong correlation agreement (r > 0.65)
        w_strong = derive_dynamic_correlation_weights(0.72, 0.68, 0.40)
        self.assertEqual(w_strong["fusion_type"], "Correlation-Weighted Fusion")
        self.assertAlmostEqual(sum([w_strong["precipitation"], w_strong["vegetation"], w_strong["soil_moisture"]]), 1.0, places=1)
        
        # Case 2: Poor correlation agreement (r <= 0.65)
        w_poor = derive_dynamic_correlation_weights(0.40, 0.35, 0.12)
        self.assertEqual(w_poor["fusion_type"], "Ensemble Average Fallback")
        self.assertEqual(w_poor["precipitation"], 0.33)

    def test_point_to_bbox(self):
        """Verifies that point coordinates are converted to correct tiny bounding boxes."""
        from ensa.eo.stac_s2 import point_to_bbox
        point = (-16.25, 27.65)
        bbox = point_to_bbox(point, offset=0.015)
        
        # Expected: [27.65 - 0.015, -16.25 - 0.015, 27.65 + 0.015, -16.25 + 0.015]
        self.assertAlmostEqual(bbox[0], 27.635, places=4)
        self.assertAlmostEqual(bbox[1], -16.265, places=4)
        self.assertAlmostEqual(bbox[2], 27.665, places=4)
        self.assertAlmostEqual(bbox[3], -16.235, places=4)

if __name__ == "__main__":
    unittest.main()
