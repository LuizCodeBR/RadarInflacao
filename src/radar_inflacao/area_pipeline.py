"""Publicação regional: Brasil e 16 áreas confirmados juntos."""

from . import area_storage
from .area_source import AreaSource
from .areas import parse_area_bundle, validate_area_metadata
from .pipeline import Pipeline


class AreaPipeline(Pipeline):
    dataset = "areas"
    run_table = "area_ingestion"
    source_type = AreaSource
    parser = staticmethod(parse_area_bundle)
    metadata_validator = staticmethod(validate_area_metadata)

    def current_rows(self, db):
        return self.repository.area_rows(db)

    def publish(self, db, rows, run_id):
        return area_storage.upsert(db, rows, run_id)
