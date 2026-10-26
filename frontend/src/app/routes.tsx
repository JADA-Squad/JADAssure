import type { ReactElement } from "react";

import { AgreementsPage } from "../features/agreements/AgreementsPage";
import { DataSetupPage } from "../features/data-setup/DataSetupPage";
import { FindingsPage } from "../features/findings/FindingsPage";
import { OverviewPage } from "../features/overview/OverviewPage";
import { PricingPage } from "../features/pricing/PricingPage";
import { RecoveryPage } from "../features/recovery/RecoveryPage";
import { SettingsPage } from "../features/settings/SettingsPage";

/** Page element per nav path. Each feature replaces its placeholder when its task lands. */
export const PAGES: Record<string, ReactElement> = {
  "/overview": <OverviewPage />,
  "/data-setup": <DataSetupPage />,
  "/agreements": <AgreementsPage />,
  "/findings": <FindingsPage />,
  "/recovery": <RecoveryPage />,
  "/pricing": <PricingPage />,
  "/settings": <SettingsPage />,
};
