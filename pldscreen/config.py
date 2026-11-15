"""Configuración por variables de entorno (ver .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: str = ".env") -> None:
    """Carga un archivo .env simple (CLAVE=valor) sin pisar variables ya definidas."""
    f = Path(path)
    if not f.is_file():
        return
    for line in f.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


@dataclass
class Settings:
    db_path: str = field(default_factory=lambda: _env("PLD_DB", "data/pld.db"))
    raw_dir: str = field(default_factory=lambda: _env("PLD_RAW_DIR", "data/raw"))
    inbox_dir: str = field(default_factory=lambda: _env("PLD_INBOX_DIR", "data/inbox"))

    # Umbrales de coincidencia (0-100)
    th_alta: float = field(default_factory=lambda: float(_env("PLD_TH_ALTA", "93")))
    th_media: float = field(default_factory=lambda: float(_env("PLD_TH_MEDIA", "85")))
    th_baja: float = field(default_factory=lambda: float(_env("PLD_TH_BAJA", "78")))
    # Nivel mínimo que genera alerta formal (BAJA queda solo como informativo)
    alert_min_level: str = field(default_factory=lambda: _env("PLD_ALERT_MIN_LEVEL", "MEDIA"))

    # Plazos internos de atención (horas). VALIDAR con su oficial de cumplimiento / asesor legal.
    sla_critica_hours: int = field(default_factory=lambda: int(_env("PLD_SLA_CRITICA_H", "24")))
    sla_revision_hours: int = field(default_factory=lambda: int(_env("PLD_SLA_REVISION_H", "72")))

    # Actualización automática
    org_name: str = field(default_factory=lambda: _env("PLD_ORG_NAME", ""))  # aparece en las constancias (p. ej. «Notaría Pública No. 12»)
    tz_offset_hours: float = field(default_factory=lambda: float(_env("PLD_TZ_OFFSET_H", "-6")))  # CDMX = -6 (sin horario de verano)
    update_interval_hours: float = field(default_factory=lambda: float(_env("PLD_UPDATE_EVERY_H", "6")))
    min_shrink_ratio: float = field(default_factory=lambda: float(_env("PLD_MIN_SHRINK_RATIO", "0.5")))

    # URLs de descarga (configurables: las fuentes oficiales cambian de dirección)
    url_ofac_sdn: str = field(default_factory=lambda: _env(
        "PLD_URL_OFAC_SDN", "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV,"
        "https://www.treasury.gov/ofac/downloads/sdn.csv"))
    url_ofac_alt: str = field(default_factory=lambda: _env(
        "PLD_URL_OFAC_ALT", "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ALT.CSV,"
        "https://www.treasury.gov/ofac/downloads/alt.csv"))
    url_un: str = field(default_factory=lambda: _env(
        "PLD_URL_UN", "https://scsanctions.un.org/resources/xml/en/consolidated.xml"))
    url_sat_69b: str = field(default_factory=lambda: _env(
        "PLD_URL_SAT_69B", "https://wu1agsprosta001.blob.core.windows.net/agsc-publicaciones/Datos_abiertos/"
                           "Documents_AGAFF/Listado_completo_69-B.csv"))
    url_sat_69b_bis: str = field(default_factory=lambda: _env(
        "PLD_URL_SAT_69B_BIS", "https://wu1agsprosta001.blob.core.windows.net/agsc-publicaciones/Datos_abiertos/"
                               "Documents_AGGC/Listado_69_B_Bis_Completo.csv"))
    ext_provider: str = field(default_factory=lambda: _env("PLD_EXT_PROVIDER", "none"))
    ext_api_key: str = field(default_factory=lambda: _env("PLD_EXT_API_KEY", ""))
    ext_base_url: str = field(default_factory=lambda: _env("PLD_EXT_BASE_URL", ""))
    ext_timeout: float = field(default_factory=lambda: float(_env("PLD_EXT_TIMEOUT", "20")))
    # Código secreto (≥16 caracteres) que permite al ADMIN recuperar su acceso desde la pantalla de inicio. Vacío = desactivado.
    recovery_code: str = field(default_factory=lambda: _env("PLD_RECOVERY_CODE", ""))
    # Demo para prospectos (registro público)
    registro_abierto: bool = field(default_factory=lambda: _env("PLD_REGISTRO_ABIERTO", "1") == "1")
    demo_dias: float = field(default_factory=lambda: float(_env("PLD_DEMO_DIAS", "2")))
    demo_consultas: int = field(default_factory=lambda: int(_env("PLD_DEMO_CONSULTAS", "20")))
    contacto_ventas: str = field(default_factory=lambda: _env("PLD_CONTACTO_VENTAS", ""))
    country_risk_path: str = field(default_factory=lambda: _env("PLD_COUNTRY_RISK", "data/country_risk.csv"))

    def ensure_dirs(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.raw_dir).mkdir(parents=True, exist_ok=True)
        Path(self.inbox_dir).mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    return Settings()
