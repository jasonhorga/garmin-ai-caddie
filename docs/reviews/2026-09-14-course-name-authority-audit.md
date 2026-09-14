# Course Name Authority Audit

Date: 2026-09-14  
Scope: `PHONE-UX5`, IMG_8061 course-name feedback

## Finding

The Chinese course names that prompted the IMG_8061 feedback were not entered
by Garmin as a separate translation table. They were hard-coded presentation
aliases in the iOS client. Git identifies the commit author as
`jasonhorga <jasonhe@gmail.com>`; Git cannot prove whether the author typed
each literal personally, but it does establish who introduced the literals
into the repository and why the code said it did so. This is separate from a
`source=manual` phone round: a player may still record a one-off round name,
but that value is not allowed to relabel the Garmin catalogue.

The aliases were added as a short-term workaround after CourseView rows were
observed returning English (and, for global id `31793`, a provider label that
did not match the player's verified Beijing course). The intent was to make the
Chinese app show familiar names while keeping the provider payload unchanged.
That workaround was too broad: an English spelling can identify a different
physical venue, and a global-id map is not Garmin localization evidence.

## Git history

| Commit | Author/date (UTC) | What was hard-coded | Stated purpose |
|---|---|---|---|
| `8fe38011` | Jason He, 2026-09-08 16:11 | Six English-to-Chinese venue aliases: Beijing Riverside Resort, Beijing Huanggang International, Beijing Black Knight (two spellings), Nicklaus Club Beijing, and Beijing Orient Tianxing. Also a special `globalId == 31793` override to `北京丽宫体育公园高尔夫俱乐部`. | “Apply build 53 phone UX feedback”; make the Chinese UI readable when CourseView returned English and repair the observed 31793 provider mismatch. |
| `9c37858a` | Jason He, 2026-09-09 05:11 | `stableCourseAliases` for ids `31790–31796` (奥园、翡翠湖、金色河畔、北京丽宫、黑骑士), plus English aliases such as Black Knight, Jade Island/Lake, Golden Riverside, and Aoyuan. | Finish build 53 UX2 polish; keep a stable presentation name before a course package was downloaded. |
| `d41fed9e` | Jason He, 2026-09-13 16:54 | Red Flag Valley, West Park, and Bangchuidao English variants mapped to 红旗谷、西郊、棒棰岛. | Make nearby CourseView rows match names already seen in the player's history, even when the map was not downloaded yet. |

These were code constants, not Garmin fields. The current production paths no
longer contain `courseAliases`, `stableCourseAliases`, the 31793 special case,
or any English-to-Chinese course translation. The remaining `areaAliases` are
administrative-label UI translations (for example, `beijing` to `北京市`),
not course-name authority and not a mapping from one golf course to another.

## Garmin-native evidence

The remote Garmin snapshot
`garmin_cn_20260913T150358Z/normalized/history.json` contains 465 normalized
round rows. Its older rows do not have a top-level `source` or
`garminSnapshotName`; their `provenance.sourceConnector` is
`garmin_cn_web_session`. The current resolver treats that connector as Garmin
authority, while an explicit `source=manual` always wins and blocks relabeling.

Examples where Garmin already supplied Chinese (global id and exact observed
spelling):

| Global id | Garmin snapshot name |
|---:|---|
| `31790` | 奥园体育俱乐部 ~ 左 |
| `31791` | 翡翠湖高尔夫俱乐部 |
| `31792` | 金色河畔高尔夫俱乐部 |
| `31793` | 北京丽宫体育公园高尔夫俱乐部 |
| `31794` | 北京天竺黑骑士球员俱乐部 ~ A |
| `31795` | 北京天竺黑骑士球员俱乐部 ~ B |
| `31796` | 北京天竺黑骑士球员俱乐部 ~ C |
| `31718` | 大连夏丽高尔夫俱乐部 ~ 左果岭 |
| `41825` | 北京北湖九号国际高尔夫俱乐部 |
| `39270` | 北京万柳高尔夫俱乐部 |

Examples where Garmin supplied English and the app must keep English rather
than invent a Chinese translation:

| Global id | Garmin snapshot name |
|---:|---|
| `6022` / `6023` | Half Moon Bay Golf Links ~ Ocean / Old |
| `3881` | Cypress Point Club |
| `1020` | Angeles National Golf Club |
| `32235` | Sentosa Golf Club ~ Serapong |
| `30249` / `30250` | Belle Mare Plage Resort ~ Links Course / Legend Course |

The sampled CourseView responses for Red Flag Valley, West Park, and
Bangchuidao still contain English provider names and no separate localized
field. They therefore remain English until Garmin supplies a Chinese field;
the old hand-written translations are intentionally not restored.

## Current authority rules

1. A `garminSnapshotName` (or the exact nested
   `courseSnapshots[0].name`) is usable only when the row is marked as Garmin
   (`source=garmin`, `source=garmin_cn_web_session`, or the equivalent
   `provenance.sourceConnector`).
2. Legacy normalized rows are supported through
   `provenance.sourceConnector`; this preserves real Garmin Chinese names even
   though those rows predate `garminSnapshotName`.
3. A row marked `manual` can retain its own name in that round's history, but
   it cannot rename an anonymous CourseView catalogue row.
4. If Garmin has no Chinese spelling, the provider spelling is displayed
   exactly (apart from whitespace around Garmin's `~` separator).
5. Composite played routes (`A/C`, `A+B`, `AB`, `AC`, `AF`, `ABC`) remain route
   facts in history and are never presented as one selectable CourseView
   segment.

Focused regression coverage is in
`tests/test_course_name_authority.py` and
`tests/test_course_reconciliation.py`, including the legacy
`provenance.sourceConnector` shape and the manual-source rejection case.
