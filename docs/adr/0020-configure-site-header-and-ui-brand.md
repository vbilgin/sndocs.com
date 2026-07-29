# ADR-0020: Configure the site header and UI brand

- **Status:** Accepted
- **Date:** 2026-07-28
- **Decision owner:** Victor Bilgin
- **Related commit:** Pending

## Context

Generated family sites previously used `sndocs.com` as the visible base name and did not identify the repository that builds and operates the mirror. The only configured repository was `ServiceNow/ServiceNowDocs`, which is the upstream content source and must not be conflated with the independent site's own repository.

The fixed header also occupied vertical space while readers navigated long documentation pages. Material already provides an automatic-hiding header and a responsive repository component that appears beside search on larger screens and in the navigation drawer on smaller screens.

## Decision

Use `sndocs` as the visible base brand throughout generated site UI while retaining each release family in the MkDocs site name, such as `sndocs — Australia`. Apply the base brand to the footer disclaimer, root redirect title, and web-app manifest. Keep `sndocs.com` as the public domain and repository-facing project identity.

Configure the site's repository URL and display name independently from the upstream documentation repository. Link the standard Material repository component to `https://github.com/vbilgin/sndocs.com`, label it `vbilgin/sndocs.com`, and use Material's bundled GitHub icon in every production and smoke family build. Continue using `ServiceNow/ServiceNowDocs` exclusively as the upstream content source.

Enable Material's `header.autohide` feature for every family build. Preserve the existing custom header integration for family-scoped Pagefind search and rely on Material's standard responsive behavior for the repository component and automatic hiding.

## Consequences

- The generated UI uses the shorter `sndocs` brand without changing public URLs or broader project terminology.
- Release context remains visible in page titles and the header.
- Readers can reach the independent site's source repository from desktop and mobile navigation.
- Material may request public GitHub repository metadata, including stars and forks, when rendering the standard source component.
- Site repository settings become part of the pipeline fingerprint, so changing them rebuilds selected current families.
- The custom Material header must continue to preserve the standard header and source-component hooks during theme upgrades.

## Alternatives considered

- **Keep `sndocs.com` in all generated UI:** Rejected because the shorter visible brand was selected while the domain remains unchanged.
- **Rename every project-facing `sndocs.com` reference:** Rejected because README, CLI, quality-rule, and domain references describe the project or public host rather than the generated UI brand.
- **Link the header to `ServiceNow/ServiceNowDocs`:** Rejected because that repository supplies mirrored content but does not contain the independent site implementation.
- **Build a custom GitHub link or scroll handler:** Rejected because Material's maintained repository component and `header.autohide` feature provide the required responsive behavior.

## Related decisions

- [ADR-0003](0003-mkdocs-material-content-processing.md) defines the independent MkDocs Material site and its branding constraints.
- [ADR-0019](0019-pagefind-static-search.md) defines the custom Pagefind integration in the Material header.
