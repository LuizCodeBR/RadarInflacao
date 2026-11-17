"""Série nacional INPC: IDs próprios, mesmas regras mensais de publicação."""

from .model import parse_observations, periods, validate_metadata
from .pipeline import Pipeline
from .source import IbgeSource

INPC_API = "https://servicodados.ibge.gov.br/api/v3/agregados/1736"
INPC_VARIABLES = {"44": "monthly", "68": "year_to_date", "2292": "twelve_month"}


def inpc_data_url(start, end):
    sequence = "|".join(p.replace("-", "") for p in periods(start, end))
    return f"{INPC_API}/periodos/{sequence}/variaveis/44|68|2292?localidades=N1[all]"


def validate_inpc_metadata(raw):
    return validate_metadata(raw, table=1736, variable_map=INPC_VARIABLES)


def parse_inpc_observations(raw, expected):
    return parse_observations(raw, expected, variable_map=INPC_VARIABLES)


class InpcSource(IbgeSource):
    api = INPC_API

    def observations(self, start, end):
        return self.fetch(inpc_data_url(start, end))


class InpcPipeline(Pipeline):
    dataset = "inpc"
    run_table = "inpc_ingestion"
    source_type = InpcSource
    metadata_validator = staticmethod(validate_inpc_metadata)
    parser = staticmethod(parse_inpc_observations)

    def current_rows(self, db):
        return self.repository.inpc_rows(db)

    def publish(self, db, rows, run_id):
        return self.repository.upsert(db, rows, run_id, table="inpc_observation")
