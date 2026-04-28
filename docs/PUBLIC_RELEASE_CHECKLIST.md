# Public Release Checklist

Use this before making the GitHub repository public.

## Required

- Publish from a clean public repository or a history-rewritten export, not from
  the old private history.
- Exclude unrelated apps and separate products unless they are intentionally
  part of the public release.
- Run `cd web && npm run test:public`.
- Confirm no `.env` files, user registries, diagnostics logs, production
  snapshots, deployment triggers, Firebase targets, or cloud service accounts
  are tracked.
- Confirm public copy says what the product does without promising legal,
  sanctions, credit-reporting, or compliance outcomes the system does not
  provide.
- Confirm the license is intentional before publishing.

## Recommended

- Keep production deployment instructions in a private operations repository.
- Keep sales, pricing, legal drafts, and partner material in private documents.
- Use example config files with placeholders only.
- Treat test artifacts and browser reports as disposable build output.
- Re-run the smoke gate after every marketing or dashboard copy change.
