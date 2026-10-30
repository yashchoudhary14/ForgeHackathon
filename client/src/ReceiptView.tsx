import { Text } from "./context";
import { safeUrl, assetUrl } from "./api/client";
import type { Receipt } from "./api/types";

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
            <a href={screenshot} target="_blank" rel="noreferrer">
              <img
                src={screenshot}
                alt="Application receipt screenshot"
                loading="lazy"
              />
            </a>
          )}
        </li>
      </ol>
    </div>
  );
}
