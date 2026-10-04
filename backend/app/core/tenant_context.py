"""Central tenant context and isolation primitives.

Defines the ContextVars and helpers that govern multi-tenant ORM filtering
and PostgreSQL Row Level Security (RLS) enforcement.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Generator, Optional

from sqlalchemy import event, text
from sqlalchemy.orm import Session, with_loader_criteria

# Request/task-scoped context variables
_current_tenant_id: ContextVar[Optional[str]] = ContextVar("current_tenant_id", default=None)
_is_system_context: ContextVar[bool] = ContextVar("is_system_context", default=False)
_is_strict_context: ContextVar[bool] = ContextVar("is_strict_context", default=False)


class MissingTenantContextError(Exception):
    """Raised when a tenant-scoped query is executed without tenant or system context in strict mode."""


def get_current_tenant_id() -> Optional[str]:
    """Return the active organization ID for the current execution context, if any."""
    return _current_tenant_id.get()


def is_system_context() -> bool:
    """Return True if the current execution context is marked as system/unscoped."""
    return _is_system_context.get()


def is_strict_context() -> bool:
    """Return True if strict context checking is active."""
    return _is_strict_context.get()


def set_tenant_context(organization_id: Optional[str]) -> Token[Optional[str]]:
    """Explicitly set the active tenant context for the current task/thread."""
    return _current_tenant_id.set(organization_id)


def reset_tenant_context(token: Optional[Token[Optional[str]]] = None) -> None:
    """Reset the tenant context using a token, or clear it if no token provided."""
    if token is not None:
        _current_tenant_id.reset(token)
    else:
        _current_tenant_id.set(None)


@contextmanager
def tenant_context(organization_id: Optional[str]) -> Generator[None, None, None]:
    """Context manager to run a block within a specific tenant context."""
    token = _current_tenant_id.set(organization_id)
    try:
        yield
    finally:
        _current_tenant_id.reset(token)


@contextmanager
def system_context() -> Generator[None, None, None]:
    """Context manager to run a block with system privileges (bypassing tenant filter/RLS)."""
    token = _is_system_context.set(True)
    try:
        yield
    finally:
        _is_system_context.reset(token)


@contextmanager
def strict_context(enabled: bool = True) -> Generator[None, None, None]:
    """Context manager to enforce strict tenant context (raises MissingTenantContextError on unscoped tenant queries)."""
    token = _is_strict_context.set(enabled)
    try:
        yield
    finally:
        _is_strict_context.reset(token)


def _desired_rls_org_id() -> str:
    if is_system_context():
        return "__SYSTEM__"
    return get_current_tenant_id() or "__NONE__"


def sync_pg_rls_context(conn, statement: str) -> None:
    """Make `app.current_organization_id` on `conn` match the current context before a statement.

    Never swallows errors: if the setting cannot be synchronised, the statement must not run
    under a previous organization's (or `__SYSTEM__`) context, so the exception propagates and
    aborts the operation.
    """
    if conn.dialect.name != "postgresql":
        return
    if "set_config" in statement:
        return
    desired_org = _desired_rls_org_id()
    if conn.info.get("rls_org_id") == desired_org:
        return
    # Forget the cached value first so a failure can never leave a stale "in sync" marker.
    conn.info.pop("rls_org_id", None)
    with conn.connection.cursor() as cur:
        cur.execute("SELECT set_config('app.current_organization_id', %s, true)", (desired_org,))
    conn.info["rls_org_id"] = desired_org


def register_tenant_listeners(
    session_factory_or_engine: type[Session] | Session = Session,
    db_engine = None,
) -> None:
    """Register ORM query filter and PostgreSQL RLS event listeners."""

    @event.listens_for(session_factory_or_engine, "do_orm_execute")
    def _enforce_orm_tenant_filter(execute_state):
        if not execute_state.is_select:
            return

        # Explicit bypass for internal operations
        if execute_state.execution_options.get("skip_tenant_filter", False):
            return

        # System operations bypass tenant scoping
        if is_system_context():
            return

        from backend.app.models.base import TenantMixin

        tenant_id = get_current_tenant_id()
        if tenant_id:
            execute_state.statement = execute_state.statement.options(
                with_loader_criteria(
                    TenantMixin,
                    lambda cls: cls.organization_id == tenant_id,
                    include_aliases=True,
                )
            )
        else:
            if is_strict_context():
                descriptions = getattr(execute_state.statement, "column_descriptions", None) or []
                for desc in descriptions:
                    entity = desc.get("entity")
                    if entity and isinstance(entity, type) and issubclass(entity, TenantMixin):
                        raise MissingTenantContextError(
                            f"Query on tenant entity '{entity.__name__}' executed without tenant or system context."
                        )

            # Fail closed: no tenant and no system context must never return tenant rows.
            execute_state.statement = execute_state.statement.options(
                with_loader_criteria(
                    TenantMixin,
                    lambda cls: cls.organization_id == "__NO_TENANT_CONTEXT__",
                    include_aliases=True,
                )
            )

    @event.listens_for(session_factory_or_engine, "after_begin")
    def _enforce_pg_rls_context(session, transaction, connection):
        if connection.dialect.name != "postgresql":
            return
        connection.info.pop("rls_org_id", None)
        if is_system_context():
            org_id = "__SYSTEM__"
        else:
            org_id = get_current_tenant_id() or "__NONE__"

        connection.execute(
            text("SELECT set_config('app.current_organization_id', :org_id, true)"),
            {"org_id": org_id},
        )
        connection.info["rls_org_id"] = org_id

    if db_engine is not None:
        @event.listens_for(db_engine, "before_cursor_execute")
        def _sync_pg_rls_before_cursor(conn, cursor, statement, parameters, context, executemany):
            sync_pg_rls_context(conn, statement)

        @event.listens_for(db_engine, "rollback")
        def _clear_rls_on_rollback(conn):
            conn.info.pop("rls_org_id", None)

        @event.listens_for(db_engine, "commit")
        def _clear_rls_on_commit(conn):
            conn.info.pop("rls_org_id", None)
