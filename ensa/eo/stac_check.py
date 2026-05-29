import pystac_client
import planetary_computer
from datetime import datetime
from ensa.config import SOUTHERN_PROVINCE_BBOX

def check_live_satellite_stream():
    print("=== Querying Live Sentinel-2 STAC Feed (May 2026) ===")
    
    # 1. Connect to Microsoft Planetary Computer STAC (Free, No Auth Required)
    stac_url = "https://planetarycomputer.microsoft.com/api/stac/v1"
    catalog = pystac_client.Client.open(stac_url)
    
    # 2. Set current date search window: May 1st, 2026 to May 30th, 2026 (Now)
    start_date = "2026-05-01"
    end_date = "2026-05-30"
    datetime_range = f"{start_date}/{end_date}"
    
    print(f"Target Bounding Box: {SOUTHERN_PROVINCE_BBOX}")
    print(f"Search Horizon: {datetime_range}")

    # 3. Query Sentinel-2 L2A (Bottom of Atmosphere reflectance)
    search = catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=SOUTHERN_PROVINCE_BBOX,
        datetime=datetime_range,
        query={"eo:cloud_cover": {"lt": 15}}  # Only fetch scenes with less than 15% cloud cover
    )
    
    items = list(search.get_items())
    print(f"\n[Success] Found {len(items)} cloud-free Sentinel-2 scenes over target region for May 2026!")
    
    # Let's inspect the most recent satellite acquisition
    if items:
        latest_item = items[0]
        signed_item = planetary_computer.sign(latest_item)
        
        print("\n=== Latest Satellite Image Details ===")
        print(f"ID: {latest_item.id}")
        print(f"Acquisition Date/Time: {latest_item.properties['datetime']}")
        print(f"Cloud Cover: {latest_item.properties['eo:cloud_cover']:.2f}%")
        print("\nAvailable Spectral Bands:")
        for band in ['B04 (Red)', 'B08 (NIR)', 'B11 (SWIR)']:
            print(f"- {band}")
            
        # Get thumbnail url
        thumbnail_url = signed_item.assets.get('thumbnail', {}).href
        print(f"\nVisual Thumbnail URL:\n{thumbnail_url}")
    else:
        print("No scenes found matching the cloud cover threshold.")

if __name__ == "__main__":
    check_live_satellite_stream()
