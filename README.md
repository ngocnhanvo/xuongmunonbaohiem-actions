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


## ESC Table preview images

Workflow: `.github/workflows/tablepress-previews.yml`

The workflow captures the real Astro frontend section marked with
`data-tablepress-preview="<table-id>"`, converts the screenshot to WebP, uploads it
to the WordPress Media Library folder `tablepress`, and writes the resulting image
back to the ESC Table preview-image field.

Modes:
- `missing`: update only tables without a preview image.
- `single`: update one table ID.
- `selected`: update the requested comma/newline-separated table IDs.
- `force=true`: replace an existing preview.

The capture runtime is `automation/tablepress/previews.mjs` in
`ngocnhanvo/xuongmunonbaohiem-php@master`.

Astro preview markers are developed on `ngocnhanvo/xuongmunonbaohiem-astro@github`.
The preview workflow targets the production frontend, so those markers must reach
production before production screenshots can be generated.
