import type { Meta } from "../../api/types";
import { formatCount, formatUtcTime } from "../../lib/format";
import { Button } from "../ui/controls";
import { Icon } from "../ui/Icon";
import styles from "./TopBar.module.css";

export function TopBar({ meta, welcomeOpen, onToggleWelcome }: { meta: Meta | null; welcomeOpen: boolean; onToggleWelcome: () => void }) {
  return (
    <header className={styles.bar}>
      <h1 className={styles.wordmark}>
        <Icon name="mark" />
        Veritas-Chain
      </h1>
      <p className={styles.capture}>
        {meta ? (
          <>
            <span className="mono">{formatCount(meta.graph.nodes)}</span> nodes · <span className="mono">{formatCount(meta.graph.edges)}</span> edge records · loaded{" "}
            <span className="mono">{formatUtcTime(meta.loaded_at).slice(0, 5)} UTC</span>
          </>
        ) : (
          "Connecting to the API"
        )}
      </p>
      <span className={styles.spacer} />
      <span className={styles.badge} title={meta?.notice ?? "All data is synthetic."}>
        <Icon name="flask" />
        Synthetic data
      </span>
      <Button variant="ghost" icon="info" aria-expanded={welcomeOpen} aria-controls="welcome" onClick={onToggleWelcome}>
        About
      </Button>
    </header>
  );
}
