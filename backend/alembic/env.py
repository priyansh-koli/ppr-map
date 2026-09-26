from alembic import context
from sqlalchemy import engine_from_config, pool, text

from app.config import get_settings
from app.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata

# PostGIS owns these; never let autogenerate try to drop them.
POSTGIS_TABLES = {"spatial_ref_sys", "topology", "layer"}

# Filled from the live database: tables created by extensions. The postgis/postgis image
# installs postgis_tiger_geocoder into POSTGRES_DB (so in CI), adding ~30 tables we don't own.
EXTENSION_TABLES: set[str] = set()

EXTENSION_TABLES_SQL = text(
    """
    SELECT c.relname FROM pg_depend d
    JOIN pg_class c ON c.oid = d.objid AND d.classid = 'pg_class'::regclass
    WHERE d.deptype = 'e' AND c.relkind IN ('r', 'p', 'v', 'm')
    """
)


def include_object(obj, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
    ignored = POSTGIS_TABLES | EXTENSION_TABLES
    if type_ == "table":
        return name not in ignored
    if type_ == "index" and reflected and compare_to is None:
        return obj.table.name not in ignored
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        EXTENSION_TABLES.update(connection.execute(EXTENSION_TABLES_SQL).scalars())
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
