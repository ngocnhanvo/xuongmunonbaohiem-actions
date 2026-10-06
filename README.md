# xuongmunonbaohiem-actions

Public GitHub Actions / CI/CD hub for **xuongmunonbaohiem.com**.

Source repositories stay private and contain application code only:

- `ngocnhanvo/xuongmunonbaohiem-astro`
  - `github` = development / test
  - `master` = production source
- `ngocnhanvo/xuongmunonbaohiem-php`
  - WordPress/PHP backend
- `ngocnhanvo/xuongmunonbaohiem-actions`
  - CI/CD workflows, verification, deployment and E2E orchestration

Production flow:

```text
WordPress Build Website
  -> repository_dispatch: wp_trigger_build
  -> xuongmunonbaohiem-actions
  -> checkout xuongmunonbaohiem-astro@master
  -> build
  -> FTP
  -> remote unzip
  -> production smoke test
```

Required repository secrets:

- `SOURCE_REPO_PAT`
- `ENV_FILE`
- `FTP_SERVER`
- `FTP_USERNAME`
- `FTP_PASSWORD`
- `WP_ADMIN_URL`
- `WP_ADMIN_USERNAME`
- `WP_ADMIN_PASSWORD`

The source repositories must not own production deployment workflows after migration is completed.
