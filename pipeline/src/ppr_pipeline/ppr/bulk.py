"""Flag bulk and portfolio sales (R-02; docs/DECISIONS.md D-031).

The PPR often files one total or averaged price against every unit of a portfolio, so
those per-unit prices are meaningless. Default market filters exclude flagged sales, and
users can switch them back on. Recomputed over all active sales on every run.

A group is sales on the same date at the same price, and it is flagged when:
- the price is above EUR 5M and at least 2 properties share it, in any county; or
- at least 3 properties in one county share it, and either the price is not a whole
  EUR 1,000 (apportioned prices do not happen by chance) or at least 3 of them are in
  the same locality (the last address part, skipping a trailing "Co X" or bare county
  name, so "Portlaoise, Laois" is in Portlaoise). Three unrelated homes in different parts
  of Dublin selling for EUR 400,000 on one busy day is a coincidence, not a portfolio.
"""

import sqlalchemy as sa

BIG_PRICE = 5_000_000
MIN_PROPERTIES = 3
MIN_SAME_LOCALITY = 3

CREATE_MEMBERS = """
CREATE TEMP TABLE bulk_member (id bigint, group_id bigint, group_size int) ON COMMIT DROP
"""

FIND_MEMBERS = """
INSERT INTO bulk_member (id, group_id, group_size)
WITH a AS (
    SELECT s.id, s.sale_date, s.price_eur, p.county::text AS county, s.property_id,
           CASE WHEN (x.parts[y.n] LIKE 'co %' OR x.parts[y.n] = p.county::text) AND y.n > 1
                THEN x.parts[y.n - 1]
                ELSE x.parts[y.n] END AS locality
    FROM sale s
    JOIN property p ON p.id = s.property_id
    CROSS JOIN LATERAL (SELECT string_to_array(p.address_normalised, ', ') AS parts) x
    CROSS JOIN LATERAL (SELECT array_length(x.parts, 1) AS n) y
    WHERE s.withdrawn_at IS NULL
),
big AS (
    SELECT sale_date, price_eur FROM a WHERE price_eur > :big_price
    GROUP BY 1, 2 HAVING count(DISTINCT property_id) >= 2
),
grp AS (
    SELECT sale_date, price_eur, county FROM a
    GROUP BY 1, 2, 3 HAVING count(DISTINCT property_id) >= :min_properties
),
loc AS (
    SELECT sale_date, price_eur, county, max(k) AS max_same_locality
    FROM (SELECT sale_date, price_eur, county, locality, count(DISTINCT property_id) AS k
          FROM a JOIN grp USING (sale_date, price_eur, county) GROUP BY 1, 2, 3, 4) t
    GROUP BY 1, 2, 3
),
cty AS (
    SELECT sale_date, price_eur, county FROM grp JOIN loc USING (sale_date, price_eur, county)
    WHERE price_eur % 1000 <> 0 OR max_same_locality >= :min_same_locality
),
members AS (
    SELECT a.id, a.sale_date, a.price_eur, '*' AS scope
    FROM a JOIN big USING (sale_date, price_eur)
    UNION ALL
    SELECT a.id, a.sale_date, a.price_eur, a.county
    FROM a JOIN cty USING (sale_date, price_eur, county)
    WHERE NOT EXISTS (SELECT 1 FROM big b
                      WHERE b.sale_date = a.sale_date AND b.price_eur = a.price_eur)
)
SELECT id,
       ('x' || left(md5(to_char(sale_date, 'YYYY-MM-DD') || '|' || price_eur::text
                        || '|' || scope), 15))::bit(60)::bigint AS group_id,
       count(*) OVER (PARTITION BY sale_date, price_eur, scope)::int AS group_size
FROM members
"""

APPLY = """
UPDATE sale s SET bulk_group_id = m.group_id, bulk_group_size = m.group_size
FROM bulk_member m
WHERE s.id = m.id
  AND (s.bulk_group_id, s.bulk_group_size) IS DISTINCT FROM (m.group_id, m.group_size)
"""

CLEAR = """
UPDATE sale s SET bulk_group_id = NULL, bulk_group_size = NULL
WHERE s.bulk_group_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM bulk_member m WHERE m.id = s.id)
"""


def flag_bulk_groups(conn: sa.Connection) -> dict[str, int]:
    """Set or clear bulk_group_id/size on active sales. Stable ids: a hash of the group."""
    conn.execute(sa.text(CREATE_MEMBERS))
    conn.execute(
        sa.text(FIND_MEMBERS),
        {
            "big_price": BIG_PRICE,
            "min_properties": MIN_PROPERTIES,
            "min_same_locality": MIN_SAME_LOCALITY,
        },
    )
    conn.execute(sa.text(CLEAR))
    conn.execute(sa.text(APPLY))
    row = conn.execute(sa.text("SELECT count(*), count(DISTINCT group_id) FROM bulk_member")).one()
    return {"bulk_sales": int(row[0]), "bulk_groups": int(row[1])}
