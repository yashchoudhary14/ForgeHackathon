import { Text } from "../context";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../api/client";
import type { RunOut } from "../api/types";
import { Empty, ErrorBox, Loading } from "../components";
import { useApp } from "../context";
import { ReceiptView } from "../ReceiptView";
export default function Runs() {
  const { t } = useApp();
  const [runs, setRuns] = useState<RunOut[]>([]),
    [busy, setBusy] = useState(true),
    [error, setError] = useState("");
  async function load() {
    setBusy(true);
    setError("");
    try {
      setRuns(await request<RunOut[]>("/agent/runs"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    void load();
  }, []);
  return (
    <>
      <div className="page-heading">
        <span className="eyebrow">
          <Text value={"YOUR PROGRESS / आपके आवेदन"} />
        </span>
        <h1>{t.runs}</h1>
        <p className="muted">
          <Text
            value={
              "Follow your applications and keep your receipts in one place."
            }
          />
        </p>
        <button className="secondary" disabled={busy} onClick={load}>
          <Text value={"Refresh"} />
        </button>
      </div>
      {busy ? (
        <Loading />
      ) : error ? (
        <ErrorBox error={error} retry={load} />
      ) : runs.length ? (
        <div className="cards">
          {runs.map((run) => (
            <article className="panel" key={run.id}>
              <div className="card-top">
                <h2>
                  <Link to={"/runs/" + encodeURIComponent(run.id)}>
                    {run.goal}
                  </Link>
                </h2>
                <span className={"badge " + run.status}>
                  <Text value={run.status.replaceAll("_", " ")} />
                </span>
              </div>
              <p className="muted">{run.portal_url}</p>
              {run.error && <p className="error">{run.error}</p>}
              {run.receipt && <ReceiptView receipt={run.receipt} />}
              <Link to={"/runs/" + encodeURIComponent(run.id)}>
                <Text value={"Open application →"} />
              </Link>
            </article>
          ))}
        </div>
      ) : (
        <Empty>
          <p>
            <Text
              value={
                "No applications yet. Choose a scheme to start an assisted application."
              }
            />
          </p>
          <Link to="/schemes">
            <Text value={"Explore schemes →"} />
          </Link>
        </Empty>
      )}
    </>
  );
}
