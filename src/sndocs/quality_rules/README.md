# sndocs.com Site Quality Rules

Each file in `rules/` is one stable quality requirement. YAML frontmatter supplies the machine-readable identity and policy; the Markdown body explains what the rule means to contributors.

To contribute a rule:

1. Choose the next unused ID in the appropriate category and create `rules/ID-kebab-case-title.md`.
2. Complete every required frontmatter field and prose section. Begin new rules as `draft`.
3. Run `sndocs quality validate` and inspect the definition with `sndocs quality show ID`.
4. If the assessment is automated, register a tested detector before changing the rule to `active`.
5. Never reuse an ID. Retain obsolete definitions as `deprecated` or `retired`.

Executable selectors, regular expressions, and recovery logic belong in Python detectors, not rule files. Rule definitions state the requirement, applicability, examples, limitations, and preferred remediation.
