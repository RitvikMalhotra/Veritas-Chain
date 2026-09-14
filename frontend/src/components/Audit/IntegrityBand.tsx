import { useState } from "react";
import { formatCount, formatUtcTime, hashGroups, parseDifferences, type Difference } from "../../lib/format";
import { lastResult, type VerifyState } from "../../state/hooks";
import { Button, Chip } from "../ui/controls";
import { Icon, type IconName } from "../ui/Icon";
import { ChainStrip } from "./ChainStrip";
import styles from "./IntegrityBand.module.css";

export interface StripSubject {
  /** Who the ticks belong to, e.g. "Rahul Sharma". */
  name: string;
  total: number | null;
  ticks: number[];
}

export function IntegrityBand({
  verify,
  onVerify,
  anchorAvailable,
  subject,
  highlight,
  onInspect,
}: {
  verify: VerifyState;
  onVerify: () => void;
  anchorAvailable: boolean | null;
  subject: StripSubject | null;
  highlight: number | null;
  onInspect: (difference: Difference) => void;
}) {
  const [copied, setCopied] = useState(false);
  const result = lastResult(verify);
  const running = verify.status === "running";
  const ok = result ? result.chain.ok && result.served_graph_matches_log : null;
  const tone = running ? "idle" : verify.status === "failed" ? "bad" : ok === null ? "idle" : !ok ? "bad" : result!.chain.anchor_checked ? "ok" : "warn";

  let icon: IconName = "shieldIdle";
  let title = "Chain not verified";
  let detail = "Nothing has been checked in this session";
  if (running) {
    title = "Verifying…";
    detail = "Re-hashing every block and replaying the log against the graph";
  } else if (verify.status === "failed") {
    icon = "warn";
    title = "Verification failed to run";
    detail = verify.message;
  } else if (result && ok === false) {
    icon = "shieldBad";
    title = "Tampering detected";
    const parts = [];
    if (result.chain.problem_count) parts.push(`${result.chain.problem_count} ${result.chain.problem_count === 1 ? "block fails" : "problems fail"} a check`);
    if (!result.served_graph_matches_log) parts.push(result.replay_error ? "the log no longer replays" : "the served graph no longer matches the log");
    detail = parts.join(" · ");
  } else if (result && !result.chain.anchor_checked) {
    icon = "warn";
    title = "Verified, no anchor";
    detail = "Blocks are consistent, but with no anchor file a full rewrite would also pass";
  } else if (result) {
    icon = "shieldOk";
    title = "Chain verified";
    detail = `${formatCount(result.chain.blocks_checked)} blocks re-hashed · anchor matched · graph matches the log`;
  }

  const total = result?.chain.head?.idx ?? null;
  const problems = result && ok === false ? result.chain.problems.map((p) => p.idx) : [];
  const differences = result ? parseDifferences(result.differences) : [];

  let stripHead = <span>Chain length is unknown until it is verified</span>;
  if (running && !result) stripHead = <span>Checking every block against the one before it</span>;
  else if (result && problems.length) {
    stripHead = (
      <span>
        <b>Block #{formatCount(problems[0])}</b> of {formatCount(result.chain.blocks_checked)} · {result.chain.problems[0].check} check
      </span>
    );
  } else if (result && subject?.ticks.length) {
    stripHead = (
      <span>
        <b>{subject.name}</b> recorded in {formatCount(subject.total ?? subject.ticks.length)} {subject.total === 1 ? "block" : "blocks"}
        {subject.total && subject.total > subject.ticks.length ? `, first ${subject.ticks.length} marked` : ""}
      </span>
    );
  } else if (result) {
    stripHead = <span>{formatCount(result.chain.blocks_checked)} blocks · select anything to mark the blocks that recorded it</span>;
  }

  const findings = result && ok === false ? findingLines(result) : [];
  const copy = async () => {
    await navigator.clipboard.writeText(findings.join("\n"));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  return (
    <section className={styles.band} data-tone={tone} aria-label="Audit chain integrity" aria-busy={running}>
      <div className={styles.state} role="status" aria-live="polite">
        <Icon name={icon} className={styles.stateIcon} />
        <strong>{title}</strong>
        <span>{detail}</span>
      </div>

      <div className={styles.strip}>
        <div className={styles.stripHead}>
          {stripHead}
          {result && !running ? <span>checked {formatUtcTime(result.checked_at).slice(0, 8)} UTC</span> : null}
        </div>
        <div className={running ? styles.scanning : undefined}>
          <ChainStrip
            total={total}
            ticks={subject?.ticks ?? []}
            highlight={highlight}
            problems={problems}
            label={total ? `Audit chain of ${total} blocks${problems.length ? `, failing at block ${problems.join(", ")}` : ""}` : "Audit chain, not yet verified"}
          />
        </div>
      </div>

      <div className={styles.head}>
        <div className={styles.headRow}>
          {result?.chain.head ? <span className={styles.label}>Head #{formatCount(result.chain.head.idx)}</span> : <span className={styles.label}>{anchorAvailable === false ? "No anchor file" : "Anchor file present"}</span>}
          {result ? (
            result.chain.anchor_checked ? (
              <Chip tone="ok" icon="anchor" title="The saved anchor's hash matches the block it points at">
                anchor matched
              </Chip>
            ) : (
              <Chip tone="warn" icon="warn">
                no anchor
              </Chip>
            )
          ) : null}
          <Button variant={result ? "default" : "primary"} icon={result ? undefined : "shieldOk"} onClick={onVerify} disabled={running}>
            {running ? "Verifying" : result ? "Verify again" : "Verify chain"}
          </Button>
        </div>
        <div className={styles.hash} title={result?.chain.head?.hash}>
          {result?.chain.head ? hashGroups(result.chain.head.hash, 4) : "head —"}
        </div>
      </div>

      {findings.length && result ? (
        <div className={styles.findings}>
          <table>
            <thead>
              <tr>
                <th scope="col">Where</th>
                <th scope="col">Check</th>
                <th scope="col">Finding</th>
              </tr>
            </thead>
            <tbody>
              {result.chain.problems.map((p) => (
                <tr key={`${p.idx}-${p.check}`}>
                  <td className="mono">#{formatCount(p.idx)}</td>
                  <td>{p.check} check</td>
                  <td>{p.detail}</td>
                </tr>
              ))}
              {result.chain.problem_count > result.chain.problems.length ? (
                <tr>
                  <td className="mono">…</td>
                  <td>chain</td>
                  <td>{formatCount(result.chain.problem_count - result.chain.problems.length)} more problems not listed</td>
                </tr>
              ) : null}
              {result.differences.map((d) => (
                <tr key={d}>
                  <td className="mono">replay</td>
                  <td>graph comparison</td>
                  <td>{d}</td>
                </tr>
              ))}
              {result.replay_error ? (
                <tr>
                  <td className="mono">replay</td>
                  <td>log replay</td>
                  <td>{result.replay_error}</td>
                </tr>
              ) : null}
            </tbody>
          </table>
          <div className={styles.actions}>
            {differences.slice(0, 1).map((d) => (
              <Button key={d.id} icon="arrow" onClick={() => onInspect(d)}>
                Inspect the changed {d.kind === "edge" ? "link" : "node"}
              </Button>
            ))}
            <Button variant="ghost" icon={copied ? "check" : "copy"} onClick={copy}>
              {copied ? "Copied" : "Copy findings"}
            </Button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function findingLines(result: NonNullable<ReturnType<typeof lastResult>>): string[] {
  return [
    `Veritas-Chain verification at ${result.checked_at}: ${result.chain.blocks_checked} blocks checked, anchor ${result.chain.anchor_checked ? "checked" : "not available"}`,
    ...result.chain.problems.map((p) => `Block ${p.idx}, ${p.check} check: ${p.detail}`),
    ...result.differences.map((d) => `Graph differs: ${d}`),
    ...(result.replay_error ? [`Log could not be replayed: ${result.replay_error}`] : []),
  ];
}
