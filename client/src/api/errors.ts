const messages = {
  unavailable: "The service is taking a break. Please try again in a moment.",
  busy: "Lots of people are asking for help right now. Please wait a moment and try again.",
  missing: "We couldn’t find that item. Go back to the list or try again.",
  invalid: "Please check the details you entered and try again.",
  forbidden: "Only the person who created this can do that.",
  conflict: "This is already in progress or done. Refresh to see the latest state.",
  tooLarge: "That file is too large. Please choose a smaller one.",
  connection:
    "Could not connect to the service. Check your connection and try again.",
  timeout: "The request timed out or was cancelled. Please try again.",
};

export function responseError(status: number): string {
  if (status === 404) return messages.missing;
  if (status === 429) return messages.busy;
  if (status === 400 || status === 422) return messages.invalid;
  if (status === 401 || status === 403) return messages.forbidden;
  if (status === 409) return messages.conflict;
  if (status === 413) return messages.tooLarge;
  return messages.unavailable;
}

// Server, provider and browser exceptions may contain technical or private details.
// Only known, user-facing guidance is allowed through to the interface.
export function friendlyError(error: string): string {
  if (
    error === "Node 'approval' raised asyncio.CancelledError" ||
    error === "Run aborted" ||
    error === "aborted by user"
  )
    return "This application was stopped. You can start again from a scheme page.";
  const safe = [
    ...Object.values(messages),
    "Voice recording is unavailable in this browser. Please type your message.",
    "Microphone permission was denied. Allow microphone access in your browser or type below.",
    "Could not access the microphone. Please type below.",
    "The answer was interrupted or timed out. You can retry.",
    "Could not read a live update. Reconnect to restore the application view.",
    "The live connection is unavailable. Wait for reconnection before continuing.",
    "This live session has ended. Your saved steps are still available. Start a new application from the scheme page when you’re ready.",
  ];
  if (safe.includes(error)) return error;
  if (
    /^Please enter a valid (age|annual income|disability percent|land acres)\.$/.test(
      error,
    )
  )
    return error;
  return messages.unavailable;
}
