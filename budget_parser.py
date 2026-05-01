"""
Parse Union Budget–style SBE Excel exports (SBEDataWithoutNote layout).

Detects period headers (Actuals / BE / RE) and flattens line items into a tidy table
for analytics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import pandas as pd


PERIOD_HEADER_RE = re.compile(
    r"(Actuals|Budget Estimates|Revised Estimates)\s+(\d{4}-\d{4})",
    re.IGNORECASE,
)


def _extract_demand_banner(df: pd.DataFrame, header_row: int) -> str:
    """SBE files usually put Ministry / Demand No. / Department in column B above the grid."""
    best = ""
    for i in range(min(header_row, 15)):
        for j in (1, 3):
            if j < len(df.columns):
                t = _cell_str(df.iloc[i, j]).replace("\xa0", " ")
                if "Demand No." in t and len(t) > len(best):
                    best = t
    return best.strip()


def parse_demand_banner(raw: str) -> tuple[str, str, str]:
    """
    Split banner cell into (lead organisation line, demand number, trailing organisation line).

    Example lines: Ministry of X | Demand No. 5 | Department of Y
    """
    raw = raw.replace("\xa0", " ").strip()
    m = re.search(r"Demand No\.\s*(\d+)", raw, re.IGNORECASE)
    demand_no = m.group(1) if m else ""
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    rest = [ln for ln in lines if not re.match(r"Demand No\.", ln, re.IGNORECASE)]
    head = rest[0] if rest else ""
    dept = rest[1] if len(rest) > 1 else ""
    return head, demand_no, dept


def _cell_str(v: Any) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).strip()


def _to_number(v: Any) -> float | None:
    s = _cell_str(v)
    if not s or s in {"...", "...", "..", "-", "—"}:
        return None
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _find_period_header_row(df: pd.DataFrame) -> int:
    for i in range(min(20, len(df))):
        row = df.iloc[i]
        for j in range(len(row)):
            m = PERIOD_HEADER_RE.search(_cell_str(row.iloc[j]))
            if m:
                return i
    raise ValueError(
        "Could not find a period header row (expected text like 'Actuals 2024-2025')."
    )


def _period_starts_and_labels(df: pd.DataFrame, header_row: int) -> list[tuple[int, str]]:
    row = df.iloc[header_row]
    out: list[tuple[int, str]] = []
    for j in range(len(row)):
        raw = _cell_str(row.iloc[j])
        m = PERIOD_HEADER_RE.search(raw)
        if m:
            label = f"{m.group(1)} {m.group(2)}"
            out.append((j, label))
    if len(out) < 2:
        raise ValueError("Expected at least two period columns in the header row.")
    return out


def _verify_subheader_row(df: pd.DataFrame, row_idx: int, starts: list[int]) -> None:
    r = df.iloc[row_idx]
    for s in starts:
        if s + 4 >= len(r):
            continue
        if _cell_str(r.iloc[s]) != "Revenue":
            raise ValueError(
                f"Subheader row {row_idx}: column {s} expected 'Revenue', "
                f"got {_cell_str(r.iloc[s])!r}."
            )


@dataclass
class ParsedSBE:
    """Tidy line-item frame plus file metadata."""

    tidy: pd.DataFrame
    ministry: str
    unit_note: str
    sheet_name: str
    demand_banner: str
    demand_ministry: str
    demand_no: str
    demand_department: str


def parse_sbe_excel(
    path_or_buffer: str | bytes,
    sheet_name: str | int | None = 0,
) -> ParsedSBE:
    """
    Load one SBE sheet and return a long-form table:

    Columns: section, code, description, period, component, value_cr, row_kind
    """
    xl = pd.ExcelFile(path_or_buffer)
    sn = sheet_name
    if sn is None:
        sn = 0
    if isinstance(sn, int):
        sheet = xl.sheet_names[sn]
    else:
        sheet = sn
    df = pd.read_excel(path_or_buffer, sheet_name=sheet, header=None)

    header_row = _find_period_header_row(df)
    demand_banner = _extract_demand_banner(df, header_row)
    demand_ministry, demand_no, demand_department = parse_demand_banner(demand_banner)
    ministry = demand_banner
    unit_note = ""
    for i in range(min(header_row, 12)):
        for j in (1, 3, 5):
            if j < len(df.columns):
                t = _cell_str(df.iloc[i, j])
                if not demand_banner and ("Ministry" in t or "Department" in t):
                    ministry = t.replace("\xa0", " ").strip()
                if "Crores" in t or "crores" in t:
                    unit_note = t
    period_cols = _period_starts_and_labels(df, header_row)
    starts = [c for c, _ in period_cols]

    sub_row = header_row + 1
    if sub_row >= len(df):
        raise ValueError("Missing subheader row after period headers.")
    _verify_subheader_row(df, sub_row, starts)

    data_start = sub_row + 1
    current_section = ""

    records: list[dict[str, Any]] = []

    for ri in range(data_start, len(df)):
        row = df.iloc[ri]
        c3, c5, c7, c9 = (
            _cell_str(row.iloc[3]) if len(row) > 3 else "",
            _cell_str(row.iloc[5]) if len(row) > 5 else "",
            _cell_str(row.iloc[7]) if len(row) > 7 else "",
            _cell_str(row.iloc[9]) if len(row) > 9 else "",
        )

        # Section / heading rows: text in col 3, little or no numeric block
        num_any = False
        for s in starts:
            for off in (0, 2, 4):
                if _to_number(row.iloc[s + off]) is not None:
                    num_any = True
                    break
            if num_any:
                break

        is_total_line = (c3.lower().startswith("total") if c3 else False) or (
            c5.lower().startswith("total") if c5 else False
        )

        # Section heading: narrative in col 3, no line code, no figures in the grid.
        if (
            c3
            and not c5
            and not c7
            and not num_any
            and len(c3) > 3
            and not c3[0].isdigit()
        ):
            current_section = c3
            continue

        code = ""
        c3_strip = c3.strip() if c3 else ""

        if c5 and (
            re.match(r"^\d+\.\d+", c5.strip())
            or re.match(r"^\d+[\s.]", c5)
            or re.match(r"^\d+\s*\.\s*$", c5.strip())
        ):
            code = c5.strip()
            desc = c7 or c9 or c3
        elif c3_strip and re.match(r"^\d+\s*\.\s*$", c3_strip):
            code = c3_strip
            desc = c5 or c7 or c9
        else:
            desc = c7 or c5 or c9 or c3

        if not desc and not code and not num_any:
            continue

        row_kind = "detail"
        if is_total_line:
            row_kind = "subtotal" if "Total -" in (desc + c3) else "total"
        elif not num_any and c3 and not code:
            row_kind = "note"

        for start, plabel in period_cols:
            for off, comp in ((0, "Revenue"), (2, "Capital"), (4, "Total")):
                col_idx = start + off
                if col_idx >= len(row):
                    continue
                val = _to_number(row.iloc[col_idx])
                if val is None:
                    continue
                records.append(
                    {
                        "section": current_section,
                        "code": code,
                        "description": desc[:500] if desc else "",
                        "period": plabel,
                        "component": comp,
                        "value_cr": val,
                        "row_kind": row_kind,
                    }
                )

    tidy = pd.DataFrame.from_records(records)
    if tidy.empty:
        raise ValueError("No numeric budget cells were extracted; check file layout.")

    tidy["ministry"] = ministry
    tidy["demand_banner"] = demand_banner
    tidy["demand_ministry"] = demand_ministry
    tidy["demand_no"] = demand_no
    tidy["demand_department"] = demand_department

    return ParsedSBE(
        tidy=tidy,
        ministry=ministry,
        unit_note=unit_note,
        sheet_name=sheet,
        demand_banner=demand_banner,
        demand_ministry=demand_ministry,
        demand_no=demand_no,
        demand_department=demand_department,
    )


def load_folder_tidy(folder: str, pattern: str = "*.xlsx") -> pd.DataFrame:
    """Load all matching xlsx files in a folder and add source_file column."""
    from pathlib import Path

    paths = sorted(Path(folder).glob(pattern))
    parts: list[pd.DataFrame] = []
    for p in paths:
        if p.name.startswith("~$"):
            continue
        try:
            parsed = parse_sbe_excel(p)
            t = parsed.tidy.copy()
            t["source_file"] = p.name
            parts.append(t)
        except Exception:
            continue
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)
