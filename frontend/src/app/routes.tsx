import type { ReactElement } from "react";

import { Placeholder } from "../components/Placeholder";
import { DataSetupPage } from "../features/data-setup/DataSetupPage";
import { FindingsPage } from "../features/findings/FindingsPage";
import { OverviewPage } from "../features/overview/OverviewPage";
import { RecoveryPage } from "../features/recovery/RecoveryPage";

/** Page element per nav path. Each feature replaces its placeholder when its task lands. */
export const PAGES: Record<string, ReactElement> = {
  "/overview": <OverviewPage />,
  "/data-setup": <DataSetupPage />,
  "/agreements": (
    <Placeholder
      title="Rules & agreements"
      description="Confirmed commercial terms, versions, effective dates and approval status."
      milestone="M4 (FE-007)"
    />
  ),
  "/findings": <FindingsPage />,
  "/recovery": <RecoveryPage />,
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
