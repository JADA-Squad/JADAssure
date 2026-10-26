import type { ReactElement } from "react";

import { Placeholder } from "../components/Placeholder";
import { DataSetupPage } from "../features/data-setup/DataSetupPage";

/** Page element per nav path. Each feature replaces its placeholder when its task lands. */
export const PAGES: Record<string, ReactElement> = {
  "/overview": (
    <Placeholder
      title="Overview"
      description="Financial outcomes, open findings, trends and recurring causes."
      milestone="M3 (FE-006)"
    />
  ),
  "/data-setup": <DataSetupPage />,
  "/agreements": (
    <Placeholder
      title="Rules & agreements"
      description="Confirmed commercial terms, versions, effective dates and approval status."
      milestone="M4 (FE-007)"
    />
  ),
  "/findings": (
    <Placeholder
      title="Findings"
      description="Prioritized findings with evidence, calculation and next action."
      milestone="M2 (FE-003)"
    />
  ),
  "/recovery": (
    <Placeholder
      title="Recovery tracker"
      description="Correction status, invoice reference, payment status and verified outcome."
      milestone="M3 (FE-005)"
    />
  ),
  "/pricing": (
    <Placeholder
      title="Pricing opportunities"
      description="Future pricing decisions supported by cost and margin data, kept separate from billing errors."
      milestone="M5 (FE-008)"
    />
  ),
  "/settings": (
    <Placeholder
      title="Access & settings"
      description="Users and roles, approvals, integration permissions and audit history."
      milestone="M4 (FE-009)"
    />
  ),
};
