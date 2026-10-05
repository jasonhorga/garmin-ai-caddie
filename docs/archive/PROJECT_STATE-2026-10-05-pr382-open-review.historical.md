HISTORICAL ARCHIVE — NON-AUTHORITATIVE

Archived from docs/operations/PROJECT_STATE.md after PR #382 was fixed and
merged. Startup recovery must use PROJECT_STATE.md instead.

PR #382 is open at exact head `df69ca9ebd1fd74f99c89aa71669193e79861f3c`.
Source CI `37271834177` and Native Mobile CI `37271834164` passed. The Native
artifact contains 89 iOS and 47 Watch snapshots; all 136 PNG hashes match the
corresponding #380 snapshots (the two prior contact sheets are the only extra
files). Review evidence is retained at
`/home/jason/garmin-ai-caddie-data/operations/pr382-native-37271834164-20261005/`.
The review found one P2 blocker: `recentRows` deduplicates by localized display
strings instead of stable `course.globalId`, so distinct courses can collapse
or localization changes can duplicate a course. Review and clarification are
posted at
`https://github.com/jasonhorga/garmin-ai-caddie/pull/382#issuecomment-5989666689`;
do not merge until the fix and regression test are reviewed.
