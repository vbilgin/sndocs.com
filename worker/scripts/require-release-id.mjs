// Refuse a hand-typed production deploy that would leave RELEASE_ID at the
// BOOTSTRAP_REQUIRED sentinel, which makes the Worker fail closed with 503.
const releaseId = process.env.RELEASE_ID ?? "";

if (!/^[0-9a-f]{64}$/.test(releaseId)) {
  console.error(
    "RELEASE_ID must be a 64-character release digest.\n" +
      "Prefer: python -m sndocs.publish_cli promote --candidate candidate " +
      "--i-reviewed-preview\n" +
      "which reads the release id from the candidate manifest.",
  );
  process.exit(1);
}
