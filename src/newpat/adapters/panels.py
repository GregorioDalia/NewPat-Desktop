"""Compatibility exports; scientific panel handling lives in one shared module."""

from newpat_scientific.panels import (
    DnpRecord, read_dnp_list, read_position_panel, read_snp_positions,
    write_dnp_list, write_position_panel, write_snp_bed,
)

__all__ = [
    "DnpRecord", "read_dnp_list", "read_position_panel", "read_snp_positions",
    "write_dnp_list", "write_position_panel", "write_snp_bed",
]
