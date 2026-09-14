import { ApiError } from "../../api/client";
import type { BootStep } from "../../state/hooks";
import { Button } from "../ui/controls";
import styles from "./BootLog.module.css";

/** The loading state reports the actual requests it is waiting on, not a spinner. */
export function BootLog({ steps, error, onRetry }: { steps: BootStep[]; error: Error | null; onRetry: () => void }) {
  const unreachable = error instanceof ApiError && error.unreachable;
  return (
    <div className={styles.wrap}>
      <ol className={styles.log} aria-live="polite" aria-label="Loading the graph">
        {steps.map((step) => (
          <li key={step.request} data-state={step.state}>
            <span>{step.request}</span>
            <span>
              {step.state === "done" ? <b>ok</b> : step.state === "failed" ? <b>failed</b> : step.state === "loading" ? <b>waiting</b> : null}
              {step.detail ? ` · ${step.detail}` : ""}
              {step.state === "loading" && step.request === "GET /api/graph" ? <i className={styles.cursor} aria-hidden="true" /> : null}
            </span>
          </li>
        ))}
      </ol>
      {error ? (
        <div className={styles.error} role="alert">
          <p>
            {unreachable
              ? "The API isn't answering. Start the API and this page together with npm run dev from the repository root, then try again."
              : `The API answered with an error: ${error.message}`}
          </p>
          <Button onClick={onRetry}>Try again</Button>
        </div>
      ) : null}
    </div>
  );
}
