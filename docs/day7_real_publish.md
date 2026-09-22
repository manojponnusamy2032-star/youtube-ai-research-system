# Day-7 verification upload (real YouTube path).

This directory holds Day-7 real-publish verification artifacts.

## Real upload (ONE controlled upload, only when credentials exist)

Requires in the local environment (never commit these):

- YOUTUBE_CLIENT_ID
- YOUTUBE_CLIENT_SECRET
- YOUTUBE_REFRESH_TOKEN

YOUTUBE_API_KEY is NOT used for uploads.

Steps:

1. Copy `.env.example` to `.env` and fill the three OAuth values, or export
   them in the shell. Get them from Google Cloud Console:
   APIs & Services > Credentials > OAuth client ID (Desktop app), enable
   "YouTube Data API v3", then complete one OAuth consent flow with the
   `https://www.googleapis.com/auth/youtube.upload` scope to mint a refresh
   token.
2. Pick an existing rendered artifact (do not render a new video just for this):
   `output/<job_id>/video.mp4` with a passing `qc_report.json`.
3. Run exactly one upload against the existing artifact (no re-render; defaults to
   unlisted, public is not reachable). The dedicated entry point is
   `--publish-existing <job_id>`:

   python run_pipeline.py --publish-existing <job_id> --mock-publish   # dry run, no network
   python run_pipeline.py --publish-existing <job_id> --publish \
       --publish-visibility unlisted \
       --publish-title "YAIRS Day-7 verification upload" \
       --publish-description "Controlled Day-7 verification upload (unlisted)."

   (`python run_pipeline.py --publish` after a fresh run also works, but a
   re-render is not needed for verification.)

4. On success, record the returned `video_id` / watch URL in
   `output/day7_demo/youtube_real_publish_result.json` (machine-readable,
   credentials-free):

   {
     "job_id": "<job_id>",
     "video_id": "<real id>",
     "video_url": "https://www.youtube.com/watch?v=<real id>",
     "privacy_status": "unlisted",
     "title": "YAIRS Day-7 verification upload",
     "uploaded_at": "<iso8601>",
     "api_response": { "...": "truncated, secret-free response" }
   }

5. Optionally confirm via the API/Studio that the video exists and is unlisted.

## Gate hardening (Day-7)

`evaluate_publish_gate` now BLOCKS publishing whenever the video artifact path
is missing/empty — previously a `video_path=None` slipped through as "nothing to
validate". QC PASS with no video artifact is now a controlled block
(`publish_ready=True`, `allowed=False`, reason "Video artifact missing: no video
path provided"), enforced in application logic, not in the CLI.

## Without credentials

Do NOT fake success. Mark real YouTube verification BLOCKED, keep the mock
E2E green, and report the exact missing env vars from Step 1.
