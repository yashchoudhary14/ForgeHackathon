import { Text, useApp } from "./context";
import { useState } from "react";
import { safeUrl, assetUrl } from "./api/client";
import type { Receipt } from "./api/types";

function ReceiptScreenshot({ src }: { src: string }) {
  const { lang } = useApp();
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  return failed ? (
    <div className="empty" role="status">
      <p>
        <Text value="The receipt image is unavailable. Your reference and official link are still shown above." />
      </p>
      <button
        className="secondary"
        onClick={() => {
          setAttempt((value) => value + 1);
          setFailed(false);
        }}
      >
        <Text value="Retry receipt image" />
      </button>
    </div>
  ) : (
    <a href={src} target="_blank" rel="noreferrer">
      <img
        key={attempt}
        src={src}
        alt={
          lang === "hi"
            ? "आवेदन की रसीद की तस्वीर"
            : "Application receipt screenshot"
        }
        loading="lazy"
        onError={() => setFailed(true)}
      />
    </a>
  );
}

export function ReceiptView({ receipt }: { receipt: Receipt }) {
  const url = safeUrl(receipt.url);
  const screenshot = receipt.screenshot
    ? assetUrl(receipt.screenshot)
    : undefined;
  return (
    <div className="receipt">
      <h2>
        <Text value={"Application receipt"} />
      </h2>
      <ol className="citations receipt-citations">
        <li>
          {receipt.reference_no && (
            <p>
              <Text value={"Reference number:"} />{" "}
              <strong>{receipt.reference_no}</strong>
            </p>
          )}
          {receipt.summary && <blockquote>{receipt.summary}</blockquote>}
          {url && (
            <p>
              <a href={url} target="_blank" rel="noreferrer">
                <Text value={"View application ↗"} />
                <small className="receipt-url">{url}</small>
              </a>
            </p>
          )}
          {screenshot && (
            <ReceiptScreenshot key={screenshot} src={screenshot} />
          )}
        </li>
      </ol>
    </div>
  );
}
