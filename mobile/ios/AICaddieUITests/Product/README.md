# C16e Product native suite

`project.yml` recursively collects the new Swift directories. It explicitly copies the authoritative
`tee_result.json` into AICaddieDomainTests, `loop_map.json` / `caddie_golden.json` into AICaddieTests,
and the small synthetic `native_product.json` into AICaddieUITests. No golden is duplicated.
SwiftPM host tests use a repository-relative path anchored at `#filePath`.

The caddie adapter follows C16c's `golden_context` in `tests/product/_support_c16c.py`:
it supplies the same opening choices, profile carries/dispersion/sample sizes, risk scores,
ball/pin evidence, candidate IDs and measured green/hazard facts. Native profiles additionally
carry their dictionary key as `clubName`, and factual line risks are also supplied as typed
`planningHazards`. Only shared rows with measured green facts enable prep green distances;
inventing a middle-only green would trigger seed augmentation and replace the stock opening.
The water hole's package par comes from the input row. Expected routes and avoid zones are
never sent to either evaluator. Both tests assert whole-route `plannedStrokes`; the measured
green row also checks structured `shotsToGreen` in the offline response.

UI 测试自带 9000 假后端，运行时不要再起 Python fixture。它也提供附近 / 名称搜索（不带坐标的 82001 行）
和只在 ready 覆盖下返回的 topo 图。没有定位的测试按产品路径搜 "Example" 开局；有定位（第 1 洞发球台）时
附近发现会显示 Example 快捷球场，测试点 `home-quick-course-82001` 进入球场页，再由「开始」进入备战洞屏。

The UI class shares one lazily initialized loopback HTTP server for the test process. Its listener
binds port 9000 with `allowLocalEndpointReuse = true`; each test resets only input state and request
records, without rebinding or stopping the listener. Run this class serially because its tests share
the simulator app and backend state. The listener is Sendable, request state is queue-confined, and
startup errors cross queues under a lock. Port binding/startup failures fail setup. All launches use
fixture markers and synthetic credentials. The one-hole input template expands into nine physical
holes and contains no expected test result. Product fixture-origin validation remains at its baseline.

After XcodeGen, select available iOS destinations and run:

```sh
xcodegen generate --spec mobile/ios/project.yml --project-root .
xcodebuild test -project AICaddieNative.xcodeproj -scheme AICaddie \
  -destination 'platform=iOS Simulator,id=<simulator-id>' \
  -only-testing:AICaddieDomainTests/ProductNineLoopTests \
  -only-testing:AICaddieDomainTests/ProductTeeResultTests \
  -only-testing:AICaddieTests/ProductLoopMapTests \
  -only-testing:AICaddieTests/ProductPhoneStateTests \
  -only-testing:AICaddieTests/ProductMapAndPackageTests \
  -only-testing:AICaddieTests/ProductCaddieGoldenTests \
  -only-testing:AICaddieTests/ProductWatchHandoffTests
xcodebuild test -project AICaddieNative.xcodeproj -scheme AICaddieUITests \
  -destination 'platform=iOS Simulator,id=<simulator-id>' \
  -only-testing:AICaddieUITests/ProductPhoneUITests -parallel-testing-enabled NO
```

The current `agenthub-native-mutant` workflow runs AICaddie and Watch unit schemes. UI-only mutations
also require the second command, with the individual method selectable after the class. Running the
unit workflow alone is not evidence that a UI mutant survived or was killed.

UI checks assert visible boundaries, enabled/selected states, data, navigation and gestures. They do
not compare screenshots or colours. A restart with a changed synthetic GPS point exercises live
post-tee range recomputation against explicit tee and moved-position numbers.

## Promise inventory

Names below omit only the common `test_` prefix. Each promise has one primary test; additional tests
with the same promise number are complementary UI or phone-adapter checks. Counts describe input
rows/sequences, not XCTest assertion counts. J2.2 checks invariants for the observed enabled/disabled
states, without prescribing a legality matrix. Its missing range control gates the four-range checks;
each selected range has the same three available synthetic rounds, and the server records the app's
requested window and served sample IDs. Grain changes must preserve both the range and that sample.
There are 26 promise primaries and seven companion tests (33 total).

| Promise | Primary class / method | Rows | Complement |
|---|---|---|---|
| J2.1 | ProductPhoneUITests / j2_1_results_entries_remain_enabled_for_zero_one_and_many_rounds | 3 home states × 5 entries | — |
| J2.2 | ProductPhoneUITests / j2_2_range_and_grain_disable_illegal_combinations_without_changing_range | 4 ranges × 4 observed grain states; 3 exact sample IDs each | No legality matrix; missing range is strict known-red |
| J2.3 | ProductPhoneUITests / j2_3_quarter_drilldown_opens_only_its_two_real_rounds_then_review | 1 quarter, 2 included + 1 excluded rounds | — |
| J2.6 | ProductPhoneUITests / j2_6_course_sections_fit_and_keep_ordered_combinations_separate | 1 course, 2 ordered combos, 2 hardest-hole sample cases | — |
| J2.7 | ProductPhoneStateTests / j2_7_distance_ladder_flags_only_abnormal_gaps | 4 gap boundaries + 1 ladder | — |
| J2.8 | ProductPhoneUITests / j2_8_review_cards_missing_metrics_and_share_fit_for_three_round_shapes | 3 round shapes | Missing metrics / share / loop identity |
| J2.9 | ProductPhoneUITests / j2_9_landing_labels_hole_switch_zoom_pan_and_visibility | 1 gesture sequence over 2 holes | 2 full shots + putt count |
| J2.11 | ProductPhoneUITests / j2_11_provider_failure_leaves_results_and_review_usable | 1 provider failure sequence | Explicit 503, results → archive → review |
| J3.2 | ProductPhoneStateTests / j3_2_insert_guess_reorder_delete_keeps_continuous_shots | 1 insert/reorder/delete/cancel sequence | — |
| J4.1 | ProductPhoneStateTests / j4_1_course_sources_merge_into_one_list | 2 location/source combinations | — |
| J4.2 | ProductMapAndPackageTests / j4_2_cached_package_lifecycle_and_revision_adoption | 3 time boundaries + 1 lifecycle sequence + 3 invalid keys | Partial/complete, revision, job restart, unavailable server, corrupt/v1 |
| J4.3 | ProductLoopMapTests / j4_3_offline_composition_matches_shared_hole_tables | 13 shared vectors | Projecting + composing at turn |
| J4.5 | ProductMapAndPackageTests / j4_5_map_degradation_and_upgrade_preserve_physical_points | 5 live + 4 prep states, 2 points, 3 refreshes, 3 hazard matches | UI: 3 map states |
| J4.6 | ProductCaddieGoldenTests / j4_6_prep_and_live_select_same_independent_plan_for_both_tees | 5 shared vectors, 2 viewport sizes, 2 tee selections, 1 no-seed case | Plan selection / hole reset |
| J5.1 | ProductNineLoopTests / j5_1_first_loop_turn_defaults_and_lock | 6 course/default rows + 1 reset sequence | Phone: 3 default sources + 4 orders × 8 event kinds at lock boundary |
| J5.2 | ProductPhoneStateTests / j5_2_home_hero_priorities_with_and_without_downloads | 4 priorities + 2 downloaded states | UI: active card, leave/resume |
| J5.3 | ProductPhoneStateTests / j5_3_home_weather_and_latest_round_strip_are_factual | 3 bad weather + 1 good, 3 archive matches, 1 recent-eight, 1 longest-club | UI: secondary tile boundaries with missing weather/archive |
| J5.4 | ProductMapAndPackageTests / j5_4_green_edges_and_live_position_ranges | 3 green shapes, 2 GPS positions, 1 flag clamp + missing facts | UI: target/hazard/green layout + post-tee movement |
| J5.5 | ProductMapAndPackageTests / j5_5_saved_gps_and_accuracy_or_unknown_score_position | 2 accuracies + 2 no-GPS score cases | UI: 2 GPS/save states |
| J5.6 | ProductPhoneStateTests / j5_6_score_preselection_and_edit_sequence | 4 source rows × edit sequence | — |
| J5.8 | ProductTeeResultTests / j5_8_tee_results_match_shared_vectors | 14 shared vectors | — |
| J5.9 | ProductPhoneStateTests / j5_9_queue_survives_restart_replay_and_round_discard | 1 restart/replay/ACK/discard sequence with 2 rounds | — |
| J5.10 | ProductPhoneStateTests / j5_10_summary_uses_recorded_holes_and_updates_edits | 3 score rows + 1 physical back/front card | UI: finish 9 recorded par fours = Par36 |
| J5.11 | ProductCaddieGoldenTests / j5_11_offline_plans_and_projected_landings_match_shared_golden | 5 shared vectors × 3 routes, 1 factual water zone | Full chain / planned strokes / projected landing; safe and missing response zone scoped known-red |
| J6.2 | ProductWatchHandoffTests / j6_2_phone_snapshots_replace_hole_ranges_and_clear_absent_advice | 1 populated advice + 3 replacement snapshots | Phone wire scope; Watch expiry/fallback belongs to Watch tests |
| J8.3 | ProductMapAndPackageTests / j8_3_optional_sections_old_and_future_data_decode_without_losing_facts | 3 prep shapes + 1 malformed optional stats section | — |

KNOWN-RED details: `tests/product/known-red/C16e.md`.
Mutation patches and validation status: `tests/product/faults/C16e.md`.
This revision's native baseline, Swift parsing and mutant execution have not run on Linux;
Swift/Xcode tooling is unavailable here.
