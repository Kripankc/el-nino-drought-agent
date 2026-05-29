from abc import ABC, abstractmethod
import pandas as pd

class BaseIngestor(ABC):
    """
    Abstract Base Class for all external data Ingestors.
    Inherit from this class to add new climate models, indices, or weather APIs.
    """
    @abstractmethod
    def fetch(self, bbox, start_date, end_date) -> pd.DataFrame:
        """
        Fetches data from the remote API for a target bounding box and timeframe.
        Must return a pandas DataFrame with structured time-series metrics.
        """
        pass

    @abstractmethod
    def validate(self, data: pd.DataFrame) -> bool:
        """
        Validates the structure and data quality of the fetched DataFrame.
        """
        pass


class BaseEOProcessor(ABC):
    """
    Abstract Base Class for Earth Observation processors (e.g. Sentinel-2, Landsat).
    Inherit from this class to add new satellites, radar, or drone variables.
    """
    @abstractmethod
    def query_stac_metadata(self, bbox, start_date, end_date) -> list:
        """
        Queries STAC catalogs to retrieve scene items matching cloud cover thresholds.
        """
        pass

    @abstractmethod
    def calculate_polygon_statistics(self, items, geom) -> pd.DataFrame:
        """
        Calculates downscaled, lightweight spatial average statistics over a target polygon geometry
        instead of downloading massive multi-gigabyte raw GeoTIFF grids.
        """
        pass
