"""Comparações puras sobre um único retrato da base; nenhuma consulta à rede."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import (
    ROUND_HALF_UP,
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    localcontext,
)

from .errors import ValidationError
from .model import month, next_month, periods

INDICATORS = (
    (
        "Variação mensal",
        "monthly",
        "Mudança do nível de preços do mês em relação ao mês anterior, segundo o IBGE.",
    ),
    (
        "Acumulado no ano",
        "year_to_date",
        "Variação desde janeiro até o último mês selecionado. O filtro não muda esse início.",
    ),
    (
        "Acumulado em 12 meses",
        "twelve_month",
        "Variação nos 12 meses encerrados no último mês selecionado, mesmo fora do filtro.",
    ),
)
ESTIMATED_LABEL = "Acumulado estimado no período"


@dataclass(frozen=True)
class PeriodSummary:
    start: str
    end: str
    count: int
    compounded: Decimal
    monthly: Decimal
    year_to_date: Decimal
    twelve_month: Decimal


@dataclass(frozen=True)
class ComparisonMeasure:
    label: str
    a: Decimal
    b: Decimal
    difference: Decimal
    method: str


@dataclass(frozen=True)
class PeriodComparison:
    a: PeriodSummary
    b: PeriodSummary
    measures: tuple[ComparisonMeasure, ...]

    @property
    def same_length(self) -> bool:
        return self.a.count == self.b.count

    @property
    def overlap(self) -> bool:
        return max(self.a.start, self.b.start) <= min(self.a.end, self.b.end)


def reference_period(start: str, end: str, mode: str) -> tuple[str, str]:
    """Gera as datas; a cobertura disponível é verificada no resumo, sem truncar."""
    count = len(periods(start, end))
    if mode == "previous":
        return next_month(start, -count), next_month(start, -1)
    if mode == "year":
        return next_month(start, -12), next_month(end, -12)
    raise ValidationError("Modo de comparação desconhecido.")


def _context(precision: int) -> Context:
    return Context(
        prec=precision, rounding=ROUND_HALF_UP, Emin=-999999, Emax=999999,
        capitals=1, clamp=0, flags=[], traps=[InvalidOperation, DivisionByZero, Overflow],
    )


def validated_rate(value: Decimal) -> Decimal:
    if (
        not isinstance(value, Decimal)
        or not value.is_finite()
        or not -6 <= value.as_tuple().exponent <= 6
        or len(value.as_tuple().digits) > 14
        or not Decimal("-100") <= value <= Decimal("999999.999999")
    ):
        raise ValidationError("A comparação exige taxas decimais válidas, sem valores ausentes.")
    return value


def summarize_period(rows: list[dict], start: str, end: str) -> PeriodSummary:
    expected = periods(start, end)
    selected = sorted(
        (row for row in rows if start <= month(row.get("period")) <= end),
        key=lambda row: row["period"],
    )
    if [row["period"] for row in selected] != expected:
        raise ValidationError(
            f"Não há cobertura completa de {start} a {end}. "
            "É necessário ter todos os meses, sem duplicações; o intervalo não foi encurtado."
        )
    # A precisão cresce com o intervalo e comporta os decimais aceitos pelo contrato da fonte.
    with localcontext(_context(len(expected) * 16 + 32)):
        factor = Decimal(1)
        for row in selected:
            factor *= Decimal(1) + validated_rate(row.get("monthly")) / Decimal(100)
        compounded = (factor - Decimal(1)) * Decimal(100)
    last = selected[-1]
    return PeriodSummary(
        start, end, len(expected), compounded,
        *(validated_rate(last.get(key)) for _, key, _ in INDICATORS),
    )


def compare_periods(
    rows: list[dict], start_a: str, end_a: str, start_b: str, end_b: str
) -> PeriodComparison:
    a = summarize_period(rows, start_a, end_a)
    b = summarize_period(rows, start_b, end_b)
    definitions = [
        (ESTIMATED_LABEL, "compounded", "Composição das taxas mensais publicadas (estimativa)"),
        *(
            (f"{label} no último mês", key, "IBGE: valor oficial do último mês de cada período")
            for label, key, _ in INDICATORS
        ),
    ]
    with localcontext(_context(max(a.count, b.count) * 16 + 32)):
        measures = tuple(
            ComparisonMeasure(label, getattr(a, key), getattr(b, key),
                              getattr(a, key) - getattr(b, key), method)
            for label, key, method in definitions
        )
    return PeriodComparison(a, b, measures)


def _display(value: Decimal, signed: bool) -> str:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValidationError("Não é possível exibir uma taxa inválida.")
    with localcontext(_context(max(32, len(value.as_tuple().digits) + abs(value.adjusted()) + 4))):
        rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if rounded == 0:
        rounded = rounded.copy_abs()
        signed = False
    return format(rounded, "+.2f" if signed else ".2f").replace(".", ",")


def format_rate(value: Decimal) -> str:
    return _display(value, False) + "%"


def format_points(value: Decimal) -> str:
    return _display(value, True) + " p.p."
