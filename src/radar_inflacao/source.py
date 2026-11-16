"""Cliente de origem fixa: sem token, redirecionamento ou consulta arbitrária."""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from .errors import SourceError
from .model import MAX_BYTES, periods

API = "https://servicodados.ibge.gov.br/api/v3/agregados/1737"
METADATA_URL = API + "/metadados"


def data_url(start: str, end: str) -> str:
    sequence = "|".join(m.replace("-", "") for m in periods(start, end))
    return f"{API}/periodos/{sequence}/variaveis/63|69|2265?localidades=N1[all]"


@dataclass(frozen=True)
class Download:
    raw: bytes
    url: str


class IbgeSource:
    api = API

    def __init__(self, client: httpx.Client | None = None, sleeper=time.sleep):
        self.client = client
        self.sleeper = sleeper

    def _download(self, client: httpx.Client, url: str) -> Download:
        for attempt in range(3):
            try:
                with client.stream("GET", url, headers={"Accept": "application/json"}) as response:
                    if response.status_code == 429 or response.status_code >= 500:
                        if attempt < 2:
                            self.sleeper(attempt + 1)
                            continue
                    if response.status_code != 200:
                        raise SourceError(
                            f"IBGE respondeu HTTP {response.status_code}. Tente mais tarde."
                        )
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content) > MAX_BYTES:
                            raise SourceError("IBGE retornou resposta maior que 2 MiB.")
                    return Download(bytes(content), url)
            except httpx.TransportError as exc:
                if attempt == 2:
                    raise SourceError(
                        "Não foi possível consultar o IBGE. A base anterior foi preservada."
                    ) from exc
                self.sleeper(attempt + 1)
        raise SourceError("Não foi possível concluir a consulta ao IBGE.")

    def fetch(self, url: str) -> Download:
        if not url.startswith(self.api + "/"):
            raise SourceError("Origem de coleta não autorizada.")
        if self.client is not None:
            return self._download(self.client, url)
        with httpx.Client(timeout=httpx.Timeout(15, connect=10), follow_redirects=False) as client:
            return self._download(client, url)

    def metadata(self) -> Download:
        return self.fetch(self.api + "/metadados")

    def observations(self, start: str, end: str) -> Download:
        return self.fetch(data_url(start, end))


GROUP_API = "https://servicodados.ibge.gov.br/api/v3/agregados/7060"


def group_data_url(start: str, end: str) -> str:
    from .groups import GROUPS

    sequence = "|".join(m.replace("-", "") for m in periods(start, end))
    codes = ",".join(GROUPS)
    return (
        f"{GROUP_API}/periodos/{sequence}/variaveis/63|69|2265|66"
        f"?localidades=N1[all]&classificacao=315[{codes}]"
    )


class GroupSource(IbgeSource):
    api = GROUP_API

    def observations(self, start: str, end: str) -> Download:
        return self.fetch(group_data_url(start, end))
