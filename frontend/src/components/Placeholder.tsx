interface Props {
  title: string;
  description: string;
  milestone: string;
}

/** Marks a screen area whose content lands in a later milestone (AGENTS.md §2.9). */
export function Placeholder({ title, description, milestone }: Props) {
  return (
    <>
      <div className="page-header">
        <h1>{title}</h1>
        <p className="muted">{description}</p>
      </div>
      <div className="placeholder">This screen is built in {milestone}. See docs/jadassure-build-plan.md.</div>
    </>
  );
}
