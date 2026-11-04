// The results UI as pieces the shells (B, C, D) arrange: each follows a ResultModel by itself.

export { useModel, Popover, Limit, Swatch, lineColor, num } from "./common";
export { ResultSummary, ResultNote, type ResultSummaryProps } from "./ResultSummary";
export { FilterBar, MoreFilters, type FilterBarProps, type MoreFiltersProps } from "./FilterBar";
export { LinesTable, type LinesTableProps } from "./LinesTable";
export { LineDetails, LinkField, appLink, lineFacts, type LineDetailsProps } from "./LineDetails";
export { ProfileDock, profileShown, type ProfileDockProps } from "./ProfileDock";
export { ProfileCard, type ProfileCardProps } from "./ProfileCard";
export { useCornersAboveCard, useCornersAboveSheet, useCornersBesidePanel } from "./corners";
export * from "./layout";
export { RunActions, ShareRun, type RunActionsProps, type ShareRunProps } from "./RunActions";
export { ResultWorkspace, runCounts, type BackAction, type ResultWorkspaceProps } from "./ResultWorkspace";
