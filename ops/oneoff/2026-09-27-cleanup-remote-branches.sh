#!/usr/bin/env bash
# One-off remote branch cleanup for jasonhorga/garmin-ai-caddie (see
# docs/operations/2026-09-27-claude-to-codex-repo-housekeeping.md).
#
# Fail-closed by design:
#   * dry-run unless --execute is given;
#   * aborts unless origin/integration/v2 is still the snapshot base SHA, the GitHub default
#     branch is still integration/v2, no open PR uses a target branch, and every target branch
#     still points at the SHA recorded in this snapshot;
#   * every branch deletion is a compare-and-delete (--force-with-lease on the snapshot SHA);
#   * archive tags are never overwritten: an existing tag must point at the same commit;
#   * each remote action is appended to an action log, and a re-run skips what the log shows
#     as done, so an interrupted run can simply be started again; the log must be writable
#     before anything is pushed, and local archive-tag conflicts are caught in preflight.
#
# Requirements: git with push rights, gh authenticated for the repo (for PR/default checks).
# Usage: ops/oneoff/2026-09-27-cleanup-remote-branches.sh [--execute] [--log FILE]
set -euo pipefail

REPO="jasonhorga/garmin-ai-caddie"
BASE_BRANCH="integration/v2"
BASE_SHA="cef291a35476f73ca4cc4b2b4d09691b2c046663"
OLD_MAIN_SHA="0f696b8817abcf589e666de6e9ef7d4fcb223b38"
OLD_MAIN_TAG="archive/main-before-v2-integration-2026-05-28"
# Never touched, whatever the lists below say. The multi-user spec remains open
# in #176; the other old-PR branches are archived below after their PRs close.
PROTECTED=("$BASE_BRANCH" "claude/code-audit-performance-17wqcv" "superpowers/multi-user-redesign-spec")

EXECUTE=0
LOG="${HOME}/garmin-ai-caddie-branch-cleanup-2026-09-27.log"
while [ $# -gt 0 ]; do
  case "$1" in
    --execute) EXECUTE=1 ;;
    --log) LOG="$2"; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

# Snapshot taken 2026-09-27 at integration/v2 = BASE_SHA: "<branch> <sha>".
# ARCHIVE: work not contained in BASE_SHA -> tag archive/<branch> first, then delete.
ARCHIVE_SNAPSHOT=$(cat <<'LIST'
codex/backend-ci-32689037776-20260824 b32cb116bb3a57665d12a8f37f05e8758a09708f
codex/ios07-20260731 3cc8e9b09c7019c024efe4756fd588f2a77f7b0f
codex/native-reorder-fix-20260825 ef5261d24a95a3683aef4ec5e644046212744ad0
codex/native-search-keyboard-fix-20260825 44ba73fbbdc22b9b9c35c5cba4d86e000682ccfb
codex/native-tee-flow-20260829 c28a93158d5f4d57ec5557ef7564e76070a80da5
codex/p0-round-watch-review-20260813 75f276df5ef527ec36295abf1c089856ab4d8049
codex/p1-strategy-sort-20260824 45555867f1e32a1dbd804e2fb163085fdfea5496
codex/product-results-integrated-20260812 10bdb9a9b189ced7306d0a54114fefcc17e3c0db
codex/tee-meta-fix-20260829 d41a818e1fc4dc100672a6ded91028f654c21e55
codex/topo-mask-cleanup-b65128c 165da8198a4f9f7ada1a3501c57f814f0f119b23
codex/topov4-postdeploy-visual-4cb548a fa945a7036c3f0c5dbda6403c310123baa74da75
codex/visual-parity-approved-renders-fa945a7 b65128c7a1e190d344944b09c2fbe27d604b7f06
codex/visual-parity-club-red-7703cea c036e436143e82b9cc3311ede193fa1dc9b9cfca
codex/visual-parity-watch-489ed38 489ed3898222442ac8f231a140fcf593f85655b3
codex/w12-watch-state-20260824 a23028eaa0fec9a3131ce474bb3d2287e398b2cd
codex/watch-club-carry-green-20260731 0798b1d3b86ebc1eb663b714af4e6893b7a245db
codex/watch-club-carry-red-20260731 315816c41b7c3aa7ed6c440deb022dc44b78cc0d
codex/watch-club-prompt-density-green-20260731 5f3c67b1339fe048b91a82fe71ec170182c6e89a
codex/watch-club-prompt-density-red-20260731 cd96e961d28c630781ba84b2345e3cdc939f5cb5
codex/watch-club-prompt-safeheight-green-20260731 d19c43f74b120f8cec9b6b42921d6bc2575b9db4
codex/watch-club-prompt-safeheight-red-20260731 fe539d30ed1dbb70313082aa7728152eeae6190d
codex/watch-gps-truth-green-20260731 339b57eb1638e7c89c89242d9484b5dacca8321f
codex/watch-gps-truth-red-20260731 7d3cbac16eec72cb4812a46f6e300892840ce291
codex/watch-search-results-green-20260731 3c21d571de7dfa809a6d82a9320c5dc358edbe0e
codex/watch-search-results-red-20260731 2a25a347709ad6872d7faa8015db82706546a046
codex/watch-setup-cta-20260731 e5431137647342993bab1562aae797918344d750
codex/watch-shot-list-20260731 6c10f8fa63993a8efbb52a2ee6ac1f94e3d585d4
codex/watch-shot-list-container-20260731 402706777b9ec89ddc36d4c11c192503ea1dbdde
codex/watch-timing-20260913 ed879184d164060046509ec209887a053f38ecd7
evidence/plan1-task4-green-20260724-a3 43ebefd7efe85da3a93373a568672bec2d893a31
evidence/plan1-task4-green-20260724-a4 83c91675c629d938bc7f653b125093e1564a66d8
evidence/plan1-task4-red-media-rewrite-7dbe2bb a87aae6e07b2c0c9a497b26071f92838b3d4d658
evidence/plan1-task4-red-review-regressions-1d94f4e 36c18c658dcd4ca7d635934ec6417f00d1d902c0
evidence/plan1-task4-red-strengthened-1d94f4e bcd24ce9d0fa1cac54c73a2a588d10301845f9be
evidence/plan1-task5a-artifact-boundary-green-343e9a2 343e9a227494889956d3135ba9f93382fc4a58c4
evidence/plan1-task5a-artifact-boundary-red-1fa1160 1fa116001ef60621cb555dc8220831872d13650f
evidence/plan1-task5a-finding-b-green-fe7d506 fe7d506af454936b4c5afe31b8f5b60c6b1b77ae
evidence/plan1-task5a-quality-boundaries-c66d345 c66d345f965112ac6582618639a806c92e84a4f3
evidence/plan1-task5a-quality-probe-addf79b addf79b1d99e26f8a326d1c5f05d637871221494
evidence/plan1-task5a-quality-red-609cb66 609cb66e89fee3e3b88071b417b8372958206a8a
evidence/plan1-task5b1-generated-bdb7d8a94773fcf79e65843b856291a61ad1581a-da3b15e95648cf1d 486d2e354c43c1a4754b18c8dbdf76eeca7f4657
evidence/plan1-task5b1-generator-input-bdb7d8a94773fcf79e65843b856291a61ad1581a bdb7d8a94773fcf79e65843b856291a61ad1581a
evidence/plan1-task5b1-green-486d2e354c43c1a4754b18c8dbdf76eeca7f4657 486d2e354c43c1a4754b18c8dbdf76eeca7f4657
evidence/plan1-task5b1-literals-red-behavior 3eeca293a47484ac350474baa0845eba74f7f1f0
evidence/plan1-task5b1-literals-red-tests a7810317f8f8f5554a042863e729a21811f4f72b
evidence/plan1-task5b2ar-erratum-green-2a8beb162a0791c3442f9201033ac0716f349342 2a8beb162a0791c3442f9201033ac0716f349342
evidence/plan1-task5b2ar-fixture-red-5f55a57a9e4b9176e309eda70664692b5d4d2038 5f55a57a9e4b9176e309eda70664692b5d4d2038
evidence/plan1-task5b2ar-green-ce009bf333aa0bbc0e06101fe6521f366c6a45c1 ce009bf333aa0bbc0e06101fe6521f366c6a45c1
evidence/plan1-task5b2ar-red1-c0fac8d06244eebb5f6c9f27959bba67a2f83f20 c0fac8d06244eebb5f6c9f27959bba67a2f83f20
evidence/plan1-task5b2ar-red2-3dc3e123f161a8174fafcec431555e2bde4e6967 3dc3e123f161a8174fafcec431555e2bde4e6967
evidence/plan1-task5b2as-codegen-green-70332765ffb09890913697c03441a1e6716f1734 70332765ffb09890913697c03441a1e6716f1734
evidence/plan1-task5b2as-codegen-red-6f0368b36ecbd5999b6a7a7553be7dc53b24666d 6f0368b36ecbd5999b6a7a7553be7dc53b24666d
evidence/plan1-task5b2as-runtime-green-1c25a1f0be9ec31149b0dc6d6164042288c69a71 1c25a1f0be9ec31149b0dc6d6164042288c69a71
evidence/plan1-task5b2as-runtime-green-cb8452bb5423e4823d66a0d26edab4b1d53a3be1 cb8452bb5423e4823d66a0d26edab4b1d53a3be1
evidence/plan1-task5b2as-runtime-red-a584e3ba2c4c3775cda60cdaa4166d0e80c1143b a584e3ba2c4c3775cda60cdaa4166d0e80c1143b
evidence/plan1-task5b2as-runtime-red-ddde4aab5c58ab6bf1c9df1347a31df850416116 ddde4aab5c58ab6bf1c9df1347a31df850416116
feature/execute-all-frozen-plans 4ed014121ea47bb72d54eff6bfac13030c50801d
feature/lean-product-delivery b5d64f2d4904a742764c543e5a0878c17822f5b5
superpowers/hole-render-frame ff152a798213f6ddeb69492582c5c4b3102a506d
superpowers/spec-maint 2af4be1cc0ce3a2f41cb24c23702fa5138995dee
superpowers/topo-tee-notch 48ea1bf45b6c7fbc91d33dccd225a0f18eb8b772
superpowers/unified-tri-surface-spec 696a728e775bfcbece95db5511f2e8fb2f80d2eb
superpowers/watch-holeview-redesign 5e8438b99d0c53431a7ff6da3be27081f89512bf
superpowers/fix-offline-driver-carry a752eb17e3b0a24be64058f15d6880a72013d8a4
superpowers/watch-hero-distances ed8f626ee9dd0428bb98478fb62663f834f93ed5
superpowers/watch-render-all afb9d6ec51dd1d02a26ba826475dd2628cceee1c
superpowers/watch-shell-combined 21d994c21bbe989edc70fb0fb25b6550c506074a
LIST
)
# MERGED: already contained in BASE_SHA -> delete only.
MERGED_SNAPSHOT=$(cat <<'LIST'
codex/fastlane-syntax-fix-20260829 1af378b811cd25edae12285c5745aef1b57d7faf
codex/p0-p1-p2-checkpoint-20260823 d26feaba91a81e66ba3ff8a6d293a37d563a926a
codex/results-merged-20260812 7dec4b0a5a047bf853a5c94e4926008b94bb1bed
fix/cache-fingerprint-singleflight c5235b9f8eeb043f774728fd4351aaa4c4780c01
fix/course-prep-hazard-geometry-precision bf084bb5e7027f9ffa8fda500c374074482be061
fix/mobile-clientid-contract 005d2b8158525fc1074357dda78086c6dda9773e
integration/map1-reconcile-20260904 a331281acb78aec7def0e68d111f6d9cc941b249
review/ios-native-redesign-20260924 6bfa6165120afa8f8abb74b4598eb7105d085528
review/phone-ux7-game-ui-20260920 890792c9363b5dbdac838f7028baa3380c12980b
superpowers/apple-multi-audience 43df77a94cf9e51eb87156e1883444899cb85ea9
superpowers/backend-hardening f38d15356879a0db39ff67242f57043586f31800
superpowers/board-sync 621a4bbc676808e7c425f1ed44266f4dffe95e9e
superpowers/board-update 594a81aa3467f714feb645629f641cdb76a4da91
superpowers/board-watch-phase1 4fe1d24eaecbb2f47bbfbb7aec6bdc0e3ca283d8
superpowers/club-bag-ios 4510b3819b0ab98dfe5105a4f92ac90341cf2967
superpowers/club-bag-manual-backend 89967b2ae43ada3f4d71e3ecc457f19f3d29972d
superpowers/club-bag-names 0b804227e00cb91ff030023b8b715857f97a4522
superpowers/club-bag-settings 0a4aac199bba994e71e837314cd89ef9e63b9096
superpowers/club-bag-web 1dc343241976aca2cca60143f00d2f06993e2c9f
superpowers/compose-apple-env fb5614cf5fbfd4909b4074c79139ffb1e4b70c01
superpowers/cross-review-remediation e9509dc71d1cfdea650a497c82f4a0f5e1e676fc
superpowers/data-green-slope 6776df7f96e5186262461ce927b74aaacc84284e
superpowers/data-green-slope-arrow e0912d987baecc964dc54eddfec62c07faa31eea
superpowers/demo-skill 68ba3e7b02b337ace795a0b642f47b7b215ad90a
superpowers/fast-start-nine-loop caf7b80a171b0bb0a99a74c5713b1317d36e777e
superpowers/fast-start-stats-cache 8b6885d9bde3d686a723924bb53010d25810cac7
superpowers/fix-p0-auth 289a8cf98578f695665c9e1fe80c996ae163b875
superpowers/fix-p0-ios-state-restore 09e89d052e6dd863f920790ff696db2a5cb48d61
superpowers/fix-p0-jsonl b6bdd27360759e3506549e321ef22aab9e0fd806
superpowers/fix-p0-jsonloads a4ca43fb1ab4f2b05b897c512d1f0da40b2914e3
superpowers/fix-p0-web-roundid a5ee8e2d9303e0dca9246d54df2db079ef3c16d3
superpowers/fix-p1-backend-hardening 365db7265b4b66b50c72942672005d0b1c027831
superpowers/fix-p1-ci-gate 1ae5150ab1d60fc6eca8e0be2e3fdc3f37f18a98
superpowers/fix-p1-ios-observability 28a1e38c7cf1b18f2108800ff007d2a355b0df9c
superpowers/fix-p1-ios-round-integrity 4963cd65c3c355bdd9838e69f7972e20c58e36d3
superpowers/fix-p1-llm-providers 9a5d0f4c1a7cd170979fd7f891883420b6a2f948
superpowers/fix-p1-sync-parity e75aaed38c1256d2821e9d1d79e1c38a1814ec7e
superpowers/fix-p1-watch-dirty-merge 07fc15b5c3effafaed0023e76ead2a981af0b9bd
superpowers/fix-p1-web-admin-token-memory 9b78a24d1217c4279633d2d82b9b119e051361e9
superpowers/fix-p1-web-geometry-token c52d7f4fa41131f19438c451029dcb793e919d8d
superpowers/fix-p2-backend-correctness 88f2941ce0e4a10d7082e52b6eb323c35d820ba0
superpowers/fix-p2-pending-media-jsonl 0bcbe669fbbde4c88dce0c1365aa8458f73959c3
superpowers/fix-p2-schema-nine d584519b18bbbb23a0ad3fdbfe42a97d9a7a5d88
superpowers/fix-p2-scorestrip-aria 1fec7c77fe41b2761dac9530bfc4228e6b8c2e73
superpowers/fix-p2-tools-root 57fb0eb1f8908cc04728c80aedc77ff9524e49aa
superpowers/g4-club-bag-isolation 77dc250a1fd10d7ae0843bf43714f78b1d134fdd
superpowers/garmin-member-bind ea4cdf6380d2524741091df6c9f7bcb2ef027632
superpowers/garmin-self-bind 72437bfa931ea882c9b3ae059676354d05d81bc1
superpowers/geometry-date-fallback c7c35c3b94283615e847b1e1f697bafbe40a9f93
superpowers/geometry-mount 4951144cab1edeaa98af63977c382816ba216d50
superpowers/geometry-revert 983b397d15c466079f3c46f593c8a0a7e5a3da0b
superpowers/holemap-labels 29229117137a6810b2db1df0c3ab819111993e92
superpowers/home-clean-unauth 3633a788c338d5752c0a736c86f10492c445a77f
superpowers/instant-open-backend ef041b421dc2a6a285d61025e5d465c6910a9cfd
superpowers/ios-apple-signin b1ab0a73c6cfc906c893a670d10a04d18f1c3a72
superpowers/ios-bag-ladder 44cbcfb95a53fa0781ba1567032a0c4d3b4921c9
superpowers/ios-demo-tight efda9a3c3a2b441cd16470f5f039f776f8d4d26b
superpowers/ios-firstrun-copy 2fbf955f498ee78f0064eb7de37ed464f67300cd
superpowers/ios-garmin-connect fa92e47af88e901a3e4b44f4765f589c8df4d0a5
superpowers/ios-lastround-preview 2dcc9320249f764833eb724fa09b833e6dfb7cac
superpowers/ios-r11 2bf65305171bc692c7a3cb81805399e370440f99
superpowers/ios-watch-deeng fd926d2e2d9490c203f44e627f1ac2f4d4ffccb6
superpowers/label-declutter 788f5c5ca7a40a7d0a360de468ced43ea3d6dbc0
superpowers/live-hole-ux-batch-a d9e24894deda4a473972d7aa1cf7db4efde4799f
superpowers/loop-name-cleanup e13470abfc8445fb2dd1372515be35c6bd58f8b7
superpowers/map-line-loading-fix dc86b94dff3e89757dbd8acf03a9478374899e94
superpowers/member-data-scope 0d49c33b305360221a3e03ab3f4455f01be14786
superpowers/member-evidence-writes c5a78d74e6e94a17c962bbf92bf26ecac5f1a32a
superpowers/member-media-partition 574f0e9bc0562ef3f2674b38b95896393db2f950
superpowers/member-onboarding-apple 4b9a2f1f71f5a70b38c3208a31863aa4ad733690
superpowers/member-route-scope 2e635a601004963c35bdb271d6ea51c41c1c5ebd
superpowers/mobile-stats-endpoint 3806b8727586ac8f75efa91feb500453075db74b
superpowers/mobile-stats-trim-refs 8879d5cf1a61d579f50baa93bcce1a51522f4d8a
superpowers/multiplayer-foundation fd52bf3de64c1c2ffcc70f61b83361aed1cfbbc5
superpowers/native-admin-hardening 59a4b57d5768b5b92265e1317c72f5f581b2cc9b
superpowers/ondemand-geometry b21eab4fddaa3ed1b3f9f312b541dccf057615e0
superpowers/open-aggregator-routes 887e9e8bc898935f4716d530fad921a0a45b8309
superpowers/owner-admin-token-persist 7253fa1396a89356938c858d015e2e9ae5fec9ae
superpowers/phase1a-db-identity-foundation 354decdf92fb2d8970afd1c1cadb28fa1b5fa83a
superpowers/phase1b-apple-auth ee8560294b748d793b753b98c0ee9046c23b5269
superpowers/phase1c-idor f49d02017b8567261af14bb0df63d398b88d6d0a
superpowers/phase2-data-partition 0d5691a254fe767f749b2f790e0451037d5d1758
superpowers/product-manual 814d020a04a1ac5ecc15a1ba715bb412f24ee62d
superpowers/r10-caddie-backend 7d8d889cc5e57e069c84424d8a8c2a17c2f80721
superpowers/r10-ios-ux c190447fc78904d61c70a4caa703fc453bdf10da
superpowers/r10-stats-backend d0314f80c4e2863fcf9c4421a9868d3e56ad18e2
superpowers/r10-stats-perf 256d95457e92122de12bb982ff752398e0d92bcd
superpowers/r12-correctness 9f98ef2f7b0ce5d264c16eb40b68e9cd4381b92c
superpowers/r12-ios-pull 273941a8c29415e409442f11ec554f9a7a98e725
superpowers/r12-phone-config 59da6b3580ec6e2a2584459ff9e991561452f3d4
superpowers/r12-round-state 56ffb1a6825024dcf0b103312605611b30c07917
superpowers/r12-sync-spine 0550b0541dd24fa3df914acc3ffdcfb5ae70b5ec
superpowers/r12-watch-client e25dee9d37b69a9a6b05ebc395205701c687cff3
superpowers/r12-watch-config 025b1b2feb4139fe6407a0337da052b99dbb4be9
superpowers/r12-watch-container b228897a3c2c2ea77add5a27d32366f04333ae0d
superpowers/r12-watch-finish 1c442318c8654312f6b798887a3a282f8cdff245
superpowers/r12-watch-home 3eef259045a36436f3eb11a8d22ce14c528670de
superpowers/r12-watch-live 73848ba2f37c303add46313e69a861bb95fb5523
superpowers/r12-watch-model 228c1b98e81054de704e70e5411dec06a702120c
superpowers/r12-watch-score 19cfa18a6ba3ee96f8b33a4ab8ec56f5f59e3e19
superpowers/r12-watch-snapshots fbcce566caa188358f06a502f3b1e26b780c6608
superpowers/r12-watch-store b4ce2fccf4fd060a1839ad9c604e01bd8f94ed50
superpowers/r13-club-cleanup fd153e539f3b089d04ca52452ce75d41d285e1dc
superpowers/r13-codex-sec1 156797944bc76e21fdb11785c73c445942095d4f
superpowers/r13-codex-sec2 553b501b77f00e01fe3b64c551e11b7060c6a40f
superpowers/r13-decision-audit-aliases 18b417656cf6eadb39e6539347663e0c24d68c37
superpowers/r13-elevation d98a994763b5afdbcda26e266e4f8b57b91d0255
superpowers/r13-golflive-stats 57accd174923af8ece706b8206fb69a365baf4de
superpowers/r13-green-distances 0b35e1549357f1803e987f9863707c89b05e47e8
superpowers/r13-ios-golflive-stats c0f5e67d44b42bc72b99ca2ca2705209cf83bf80
superpowers/r13-iphone-live c2fdf5e28d5df49c244ddb5076a3a5a5f13cfbb0
superpowers/r13-live-screens 915313d9156799a6461a93e181d36b048d565c5d
superpowers/r13-mobile-window 624a39256f2c590e03b3c067ec852881149797eb
superpowers/r13-prep-cache 2e22b198d1e3e01fe1d66f354d71d10d3fc7f147
superpowers/r13-prep-cache-bound d3564631759cf38542a25eb2c31927844a4d34f8
superpowers/r13-prep-elevation 2ed6347deb7cfff941fe5c44832b72938cfdc89f
superpowers/r13-prep-nav-fix 1c50bd9c6cae76561833e714c55be8d9fe6b3b01
superpowers/r13-real-simulator 9c9cea51e7eb93c52fa4ac35ecc8ae3fbfa78c87
superpowers/r13-repo-tidy 3d4cd7b89b95fe46a633811095ef02fd6f6d5e2c
superpowers/r13-tidy3 b671ff96eef6a17f94cb386e279eb9f4cee7a6bc
superpowers/r13-tools-reorg 1fce894780da9dc1abfb69db35d7285b312ab7ef
superpowers/r13-user-guide c80e8941a36fdca5905b8255bd4f514ac35f5542
superpowers/r13-watch-hazard-caddie 9fcf14fcc45761ee74b922bc4415eb82ac906626
superpowers/r13-watch-ring e3822ba382f0543cde31b7e39d69a6d54aa971c0
superpowers/r13-watch-screens e60ef320e1195ed79c00bf2ea195312aeee101fa
superpowers/r13-watch-spec 3b3db854ca36c2b14962532ae667b071803afea0
superpowers/r13-watch-state-fields 10f7496621b4446c43acf705874f244a3c419669
superpowers/r13-web-fixes 82f117b8f228977b704120bf9278b0def17956ba
superpowers/r13-web-golflive de886c518e2f2c087545026c48b22296bd5234b9
superpowers/r13-windowed-shotref 44f8d1745b9b587ab9b9dfa907090f2d74192795
superpowers/repo-reorg-phase1 5d4176e5db944b4430fc4fa600fd9483c88a7bf0
superpowers/repo-reorg-phase2 24bd5048a558f6d2f0b6e3e07a4fb578e9c36fac
superpowers/review-edit-backend a3852aaf9e5c467f9df03cd6413436815edfba22
superpowers/review-edit-ios d644219119a5db3e32d8fc8115bd77194eeeb053
superpowers/review-edit-pr2 651a6791129bb77a8a267735a9e1c6a19e842a9a
superpowers/review-provenance-web bdaec04f83c0f7731efa39a96d499f7b042fa000
superpowers/review-v2-corrections 5c1448ab5b625ad9a4e5ee1f9b5f1874d607f471
superpowers/round-detail-zh a9fc1bc7c71a4e42f44e92671201ef83a27ee27f
superpowers/round-review-screen 99d47855b2ee0e9c1d4c6d5e4dfbbb82c00eec57
superpowers/round-shot-map-backend 35fe424872c31dee513e6c2c44ffa3a615f189bb
superpowers/round-shot-map-ios a5fb9435347ea0f2c11beca422daf9f82db985b4
superpowers/session-persistence 9c66f0a4a89803a22d3471e2355fd2369b5b60da
superpowers/shared-topo-frame-club 37444edbc4a5a621ef9605f44d70d8731e719e9b
superpowers/start-second-nine-exclude-self a21a56b63fa051cc87483c71a8e6832c7e488a39
superpowers/stats-screen c6d9cc08e17cdd4aadaa99bc0c92f29496805302
superpowers/sync-completed-only 9e4fe2e5df6a9c4555588e2ab2859420bf6e49ba
superpowers/sync-drop-inprogress dc5def7369cd46d0bccecdd30b5adfed8dc1c2de
superpowers/sync-image-club-refresh 012da6ea434b0c501f548634a91fba32b774eb31
superpowers/sync-reconcile dec544d871b4cf5f0a10f46b0c64f48ac77a4b97
superpowers/syncpanel-probe-guard 164da9dbb913d5208780e72fd4a8b7ba25ce0f3f
superpowers/tee-dedup d59c625989ed05b678784ebe8ace2cf94bdebcd6
superpowers/tee-marker 48767677cb70559f78a18d2a37d412c48733622b
superpowers/ux-r10-continue 886195b8cd0c65d3b8a9351bfe9cce953945a514
superpowers/ux-r9-caddie d47c1f8ddc5c8be3afb4e570fa5a8fceefd4a91a
superpowers/ux-r9-hub-declutter 869a44b75801f12ac81b7c503f376da4804d9e19
superpowers/ux-r9-review 3daedbc6e1db2175734205ab41bbaf483a3515b6
superpowers/ux-r9-shotmap 3e82e4791e61175e492156a6c2ea54a3ea1405d3
superpowers/ux-r9-stats-api 52041a3be6dc4fcef7b34bc32e94a01042f8bdfc
superpowers/ux-r9-stats-ios 641a6ba2d03805389093b07baf4e80d2a48fd6ed
superpowers/ux-r9-trend-fix 1aa86c37acc51efede3928252431137dafb9bad0
superpowers/v2-latest cebad271ec194511330758b5e15aa4093e074b1c
superpowers/video-harness 9171690b7c1c1b582c3ff16c40f3786b7357f095
superpowers/warm-on-startup b221fac9edb175a80d7b58478c27e64d98fc084d
superpowers/watch-edge-ticks 7082cea0b9f85acebdc32adbb65e14cc795be38a
superpowers/watch-livegps-video 000e5af405ae7822319c2f30cec641018292b43a
superpowers/watch-localize-caddie e0d41325548205015cf809bdcd90d55002e2489c
superpowers/watch-p0-hazards b5e2276f5c01b42bc759c999f5eb88f75a293bb6
superpowers/watch-p0-model 5c58c471ede85cf18484ded9ff3af591d290c16a
superpowers/watch-p0-offlineimg b81fb6ba8a58c963b1c3636f0f6379c30c6b0f9f
superpowers/watch-p0-projection 1f0e080eb45f32c69ca5b65c4e802b687fd0984f
superpowers/watch-p1-holemap fa09057b6ba89361a43a1058bf64fe28dbb8477a
superpowers/watch-p1b-holemap-wire b94aedad7931d65ae9d0442767c629cfb13b5b86
superpowers/watch-p1c-live-you 2e7107561fe5779e1be0d364302a16ea93f481f7
superpowers/watch-p1d-live-greens 314786b26e27ef7019821892a32aa9592026e7a3
superpowers/watch-p1f-bigtext-fallback 21b7fdf84b2443bd7afa64c496a074978a66557c
superpowers/watch-p2-green-slope-arrow a9351548dcec618d473d7f2aee318ed13bb691ac
superpowers/watch-p2-map-interactions 06a19107b089d535d98f9838a69efbadb7207502
superpowers/watch-p3-native-gps 6e94c85261b2a0ef40b372c9c47bd575e4f44ac6
superpowers/watch-plan a69d96777211565d5ed63222356a4844ebbf53a8
superpowers/watch-plan-fallback dbeab8b21fb9c3903a7f9fb24b2fce5373c776ee
superpowers/watch-session-auth af1988904497af91198ac730c980e24af5100f53
superpowers/watch-touch-single-session d9af1db597853c8f9879b3fc5ede30e8b9653db5
superpowers/watch-touch-xcuitest e0ff6b9a2900b4c9cd03123ae429d9ca4b74a689
superpowers/watch-uitest-gps-route a09223db639a72aeddaaf6c0241dbfde15c1ff62
superpowers/watch-yards cbac37545080d181177e3d6b92b9412aad9eab18
superpowers/web-admin-hardening 2b3031a1fac2d35458864c6015000a53a5d11787
superpowers/web-apple-signin d28f7cef6730dfb6b044dd1b9298b4dce54316af
superpowers/web-auth-cleanup e95a6897c20a4c97c4ba93e16b93231fb3af5e13
superpowers/web-deeng-provenance 7b2b049ab58c4924f0824eb60081f08cb3f4c8bf
superpowers/web-distribution-declutter 3f891c6bca071187a579f4ccc9465d271ebe02dd
superpowers/web-flow-video a860f69730e70a886a9e09f0094cdfa63bb6edc2
superpowers/web-mobile-fixes ed93fd347843c3f2648ce940a7ce06107aa386f2
superpowers/web-prod-audit 673ee1d29c73c4a3c8217395b2091d2c4738df69
superpowers/web-prod-audit-2 baf8c125a8806d38ffdc1b99800ae94d3cc41c52
superpowers/web-prod-audit-3 77d14f37bc549bcc720e38e2eccd58341a5d81ee
superpowers/web-redesign-w1a a8e0f3e45d0d8000f7ab4a3a35cb825dd661a55d
superpowers/web-redesign-w1b 2b94b23765296d3bae3924b936a7e80977f7fe75
superpowers/web-redesign-w2-prep aa0aac5c722c832e0f387e854b8a5a850e75eb0c
superpowers/web-redesign-w3-live 7a463046feddae511f91e2a48942b57ad12608a7
superpowers/web-screenshot-harness 5f31d8fad863d1d7971289457dd81bed8cf8ce1e
superpowers/web-zh-polish 4b2c6e57ce45a5ec842db8d1655b5158be687cbf
LIST
)

die() { echo "ABORT: $*" >&2; exit 1; }
say() { echo "$*"; }
logged() { [ -f "$LOG" ] && grep -qxF "$1" "$LOG"; }
record() { echo "$1" >> "$LOG"; }

# Remote refs are read in one ls-remote per phase (not one round trip per branch or tag).
REMOTE_REFS=""
refresh_remote() { REMOTE_REFS=$(git ls-remote origin 'refs/heads/*' 'refs/tags/*'); }
remote_heads() { echo "$REMOTE_REFS" | awk '$2 ~ /^refs\/heads\// {sub("refs/heads/","",$2); print $2" "$1}'; }
remote_tag_commit() { # peeled commit of a remote tag in the cached refs, empty if absent
  echo "$REMOTE_REFS" | awk -v r="refs/tags/$1" '$2==r {t=$1} $2==r"^{}" {p=$1} END {if (p) print p; else if (t) print t}'
}
is_protected() { local b; for b in "${PROTECTED[@]}"; do [ "$b" = "$1" ] && return 0; done; return 1; }

check_log_writable() { # before any remote change: a push must never outrun its log line
  local dir; dir=$(dirname -- "$LOG")
  [ -d "$dir" ] || die "log directory $dir does not exist; nothing was changed"
  if [ "$EXECUTE" = 1 ]; then
    { : >> "$LOG"; } 2>/dev/null || die "cannot write log $LOG; nothing was changed"
  else
    [ -w "$dir" ] || [ -w "$LOG" ] || die "log $LOG would not be writable; nothing was changed"
  fi
}

preflight() {
  command -v gh >/dev/null || die "gh CLI is required for the open-PR and default-branch checks"
  git fetch --prune --quiet origin
  local url; url=$(git remote get-url origin)
  case "$url" in *"$REPO"*) ;; *) die "origin is $url, expected $REPO" ;; esac

  refresh_remote
  local base; base=$(remote_heads | awk -v b="$BASE_BRANCH" '$1==b {print $2}')
  [ "$base" = "$BASE_SHA" ] || die "$BASE_BRANCH is ${base:-missing}, snapshot was $BASE_SHA; regenerate the lists"

  local def; def=$(gh api "repos/$REPO" --jq .default_branch)
  [ "$def" = "$BASE_BRANCH" ] || die "default branch is $def, expected $BASE_BRANCH"

  OPEN_HEADS=$(gh pr list --repo "$REPO" --state open --limit 500 --json headRefName --jq '.[].headRefName')
  HEADS=$(remote_heads)

  local name sha now problems=0
  while read -r name sha; do
    [ -n "$name" ] || continue
    is_protected "$name" && { echo "  target is protected: $name" >&2; problems=1; }
    echo "$OPEN_HEADS" | grep -qxF "$name" && { echo "  target has an open PR: $name" >&2; problems=1; }
    now=$(echo "$HEADS" | awk -v n="$name" '$1==n {print $2}')
    if [ -z "$now" ]; then
      logged "deleted $name $sha" || { echo "  target missing on origin and not in the log: $name" >&2; problems=1; }
    elif [ "$now" != "$sha" ]; then
      echo "  target moved: $name is $now, snapshot $sha" >&2; problems=1
    fi
  done <<< "$ARCHIVE_SNAPSHOT
$MERGED_SNAPSHOT"

  while read -r name sha; do
    [ -n "$name" ] || continue
    git merge-base --is-ancestor "$sha" "$BASE_SHA" || { echo "  merged-list branch not in base: $name" >&2; problems=1; }
  done <<< "$MERGED_SNAPSHOT"
  while read -r name sha; do
    [ -n "$name" ] || continue
    if git merge-base --is-ancestor "$sha" "$BASE_SHA"; then echo "  archive-list branch already in base (fine, still archived): $name"; fi
    local tag; tag=$(remote_tag_commit "archive/$name")
    [ -z "$tag" ] || [ "$tag" = "$sha" ] || { echo "  archive/$name exists at $tag, expected $sha" >&2; problems=1; }
    local ltag; ltag=$(git rev-parse -q --verify "refs/tags/archive/$name^{commit}" || true)
    [ -z "$ltag" ] || [ "$ltag" = "$sha" ] || { echo "  local tag archive/$name is $ltag, expected $sha" >&2; problems=1; }
  done <<< "$ARCHIVE_SNAPSHOT"

  local m; m=$(echo "$HEADS" | awk '$1=="main" {print $2}')
  [ -z "$m" ] || [ "$m" = "$OLD_MAIN_SHA" ] || { echo "  main is $m, expected $OLD_MAIN_SHA" >&2; problems=1; }
  [ "$(remote_tag_commit "$OLD_MAIN_TAG")" = "$OLD_MAIN_SHA" ] || { echo "  $OLD_MAIN_TAG does not point at old main" >&2; problems=1; }

  # branches that are neither targets nor protected are left alone; list them so nothing is a surprise
  local known; known=$({ printf '%s\n' "${PROTECTED[@]}" main; printf '%s\n%s\n' "$ARCHIVE_SNAPSHOT" "$MERGED_SNAPSHOT" | awk 'NF {print $1}'; } | grep .)
  echo "$HEADS" | awk '{print $1}' | grep -vxF -f <(echo "$known") | sed 's/^/  not in snapshot, left untouched: /' || true

  [ "$problems" = 0 ] || die "preflight failed; nothing was changed"
}

delete_branch() { # compare-and-delete on the snapshot sha
  local name="$1" sha="$2"
  logged "deleted $name $sha" && return 0
  if [ "$EXECUTE" = 1 ]; then
    git push --quiet origin --force-with-lease="refs/heads/$name:$sha" ":refs/heads/$name"
    record "deleted $name $sha"
  fi
  say "  delete $name ($sha)"
}

check_log_writable
preflight
N_ARCH=$(echo "$ARCHIVE_SNAPSHOT" | grep -c . || true); N_MERGED=$(echo "$MERGED_SNAPSHOT" | grep -c . || true)
say "preflight ok: $N_ARCH to archive+delete, $N_MERGED to delete, old main to delete. log: $LOG"
[ "$EXECUTE" = 1 ] || say "DRY RUN (pass --execute to act)"

say "== 1/3 archive tags"
while read -r name sha; do
  [ -n "$name" ] || continue
  [ "$(remote_tag_commit "archive/$name")" = "$sha" ] && { say "  tag archive/$name already on origin"; continue; }
  if [ "$EXECUTE" = 1 ]; then
    local_tag=$(git rev-parse -q --verify "refs/tags/archive/$name^{commit}" || true)
    [ -z "$local_tag" ] || [ "$local_tag" = "$sha" ] || die "local tag archive/$name points at $local_tag, expected $sha"
    [ -n "$local_tag" ] || git tag "archive/$name" "$sha"
    git push --quiet origin "refs/tags/archive/$name"
    record "tagged $name $sha"
  fi
  say "  tag archive/$name -> $sha"
done <<< "$ARCHIVE_SNAPSHOT"
if [ "$EXECUTE" = 1 ]; then
  refresh_remote
  while read -r name sha; do
    [ -n "$name" ] || continue
    [ "$(remote_tag_commit "archive/$name")" = "$sha" ] || die "archive/$name not on origin at $sha after push; no branch was deleted"
  done <<< "$ARCHIVE_SNAPSHOT"
fi

say "== 2/3 re-check before deleting"
if [ "$EXECUTE" = 1 ]; then preflight; fi

say "== 3/3 delete branches"
while read -r name sha; do [ -n "$name" ] && delete_branch "$name" "$sha"; done <<< "$ARCHIVE_SNAPSHOT"
while read -r name sha; do [ -n "$name" ] && delete_branch "$name" "$sha"; done <<< "$MERGED_SNAPSHOT"
if [ -n "$(remote_heads | awk '$1=="main"')" ]; then delete_branch main "$OLD_MAIN_SHA"; fi

git fetch --prune --quiet origin
say "done. remaining remote branches:"; git branch -r | grep -v HEAD
