class RadarError(Exception):
    """Falha conhecida, segura para exibir ao usuário."""


class ValidationError(RadarError):
    pass


class SourceError(RadarError):
    pass


class BusyError(RadarError):
    pass
