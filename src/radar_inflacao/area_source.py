"""Coleta regional em lotes limitados, conservando cada resposta original."""

from .areas import area_data_url, bundle_bytes, parse_area_response, windows
from .errors import SourceError
from .model import MAX_BYTES, periods
from .source import GROUP_API, Download, IbgeSource


class AreaSource(IbgeSource):
    api = GROUP_API

    def observations(self, start, end):
        parts = []
        for begin, finish in windows(start, end):
            part = self.fetch(area_data_url(begin, finish))
            parse_area_response(part.raw, periods(begin, finish))
            if sum(len(p.raw) for p in parts) + len(part.raw) > MAX_BYTES:
                raise SourceError("As respostas regionais excedem o limite total de 2 MiB.")
            parts.append(part)
        return Download(bundle_bytes(parts), area_data_url(start, end))
