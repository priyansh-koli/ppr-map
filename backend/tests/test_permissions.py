"""docs/permissions.md and app/auth/permissions.py must describe the same matrix."""

import re

from app.auth.permissions import (
    EXPORT_ROWS_PER_EXPORT,
    ROLE_PERMISSIONS,
    Perm,
    Role,
    permissions_for,
)
from tests.conftest import REPO_ROOT

DOC = (REPO_ROOT / "docs" / "permissions.md").read_text()
DOC_ROLE_COLUMNS = [Role.ANONYMOUS, Role.USER, Role.PRO, Role.ADMIN]


def _section(title: str) -> str:
    match = re.search(rf"^## {title}\n(.*?)(?=^## |\Z)", DOC, re.S | re.M)
    assert match, f"section '{title}' missing from permissions.md"
    return match.group(1)


def _table_rows(section: str) -> list[list[str]]:
    rows = []
    for line in section.splitlines():
        if line.startswith("|") and not re.match(r"^\|[\s:|-]+\|$", line):
            rows.append([cell.strip() for cell in line.strip("|").split("|")])
    return rows[1:]  # drop the header row


def test_permission_codes_match_doc() -> None:
    doc_codes = {row[0].strip("`") for row in _table_rows(_section("Permission codes"))}
    assert doc_codes == {p.value for p in Perm}


def test_role_matrix_matches_doc() -> None:
    doc_matrix: dict[Role, set[str]] = {role: set() for role in DOC_ROLE_COLUMNS}
    for row in _table_rows(_section("Matrix")):
        codes = [c.strip() for c in row[0].split(",")]
        for role, cell in zip(DOC_ROLE_COLUMNS, row[1:], strict=True):
            if cell.startswith("✅"):
                doc_matrix[role].update(codes)
    for role in DOC_ROLE_COLUMNS:
        assert doc_matrix[role] == {p.value for p in ROLE_PERMISSIONS[role]}, role


def test_export_caps_match_doc() -> None:
    matrix = _section("Matrix")
    assert "500 rows / export" in matrix and EXPORT_ROWS_PER_EXPORT[Role.USER] == 500
    assert "50,000 rows" in matrix and EXPORT_ROWS_PER_EXPORT[Role.PRO] == 50_000


def test_everyone_gets_public_permissions_and_admin_is_not_pro() -> None:
    assert Perm.MAP_READ in permissions_for(set())
    admin = permissions_for({Role.ADMIN})
    assert Perm.ADMIN_USERS in admin
    assert Perm.API_ACCESS not in admin
    assert Perm.ADMIN_USERS not in permissions_for({Role.USER, Role.PRO})
