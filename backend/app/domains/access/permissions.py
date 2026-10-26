"""Role permission matrix (FR-03, design §3.7). The single place roles map to capabilities."""

from enum import StrEnum

from fastapi import Depends, HTTPException, status

from app.core.tenancy import TenantContext, current_context


class Cap(StrEnum):
    MANAGE_USERS_SETTINGS = "manage_users_settings"
    MANAGE_DATA = "manage_data"
    MANAGE_CONTRACTS = "manage_contracts"
    VIEW_AGREEMENTS = "view_agreements"
    EDIT_RULES = "edit_rules"
    RUN_CHECKS = "run_checks"
    VIEW_FINDINGS = "view_findings"
    COMMENT_ASSIGN = "comment_assign"
    PROPOSE_REJECT = "propose_reject"
    APPROVE = "approve"
    VIEW_RECOVERY = "view_recovery"
    EXPORT_CORRECTIONS = "export_corrections"
    VIEW_REPORTS = "view_reports"
    VIEW_AUDIT = "view_audit"


ROLE_CAPS: dict[str, frozenset[Cap]] = {
    "admin": frozenset({
        Cap.MANAGE_USERS_SETTINGS, Cap.MANAGE_DATA, Cap.MANAGE_CONTRACTS, Cap.VIEW_AGREEMENTS, Cap.EDIT_RULES,
        Cap.RUN_CHECKS, Cap.VIEW_REPORTS, Cap.VIEW_AUDIT,
    }),
    "analyst": frozenset({
        Cap.VIEW_AGREEMENTS, Cap.RUN_CHECKS, Cap.VIEW_FINDINGS, Cap.COMMENT_ASSIGN, Cap.PROPOSE_REJECT,
        Cap.VIEW_RECOVERY, Cap.EXPORT_CORRECTIONS, Cap.VIEW_REPORTS,
    }),
    "approver": frozenset({
        Cap.VIEW_AGREEMENTS, Cap.VIEW_FINDINGS, Cap.COMMENT_ASSIGN, Cap.APPROVE, Cap.VIEW_RECOVERY,
        Cap.EXPORT_CORRECTIONS, Cap.VIEW_REPORTS, Cap.VIEW_AUDIT,
    }),
    "commercial": frozenset({
        Cap.MANAGE_CONTRACTS, Cap.VIEW_AGREEMENTS, Cap.VIEW_FINDINGS, Cap.COMMENT_ASSIGN, Cap.PROPOSE_REJECT,
        Cap.VIEW_REPORTS,
    }),
    "executive": frozenset({Cap.VIEW_RECOVERY, Cap.VIEW_REPORTS}),
}


def has_cap(role: str, cap: Cap) -> bool:
    return cap in ROLE_CAPS.get(role, frozenset())


def require(cap: Cap):
    """FastAPI dependency: authenticated caller whose role holds `cap`, else 403."""

    def dependency(ctx: TenantContext = Depends(current_context)) -> TenantContext:
        if not has_cap(ctx.role, cap):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role does not permit this action")
        return ctx

    dependency.required_cap = cap  # type: ignore[attr-defined]  (read by the route-coverage test)
    return dependency


def require_any(*caps: Cap):
    """Like `require`, but any one of `caps` suffices."""

    def dependency(ctx: TenantContext = Depends(current_context)) -> TenantContext:
        if not any(has_cap(ctx.role, c) for c in caps):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role does not permit this action")
        return ctx

    return dependency
