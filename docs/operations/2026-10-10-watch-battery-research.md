# Watch battery and location research — 2026-10-10

Status: research only; no code change is proposed by this report. Sources were
read on 2026-10-10 UTC. Marketing pages and support articles are quoted as
public claims, not as independent battery measurements.

## Findings that matter for this app

The public material does not show a commercial golf app promising a fixed GPS
sample rate or a percentage consumed per 18 holes. The consistent pattern is
more useful: keep course data and the map local, keep the workout/location
session alive only for the round, separate raw sensor collection from what
causes a UI redraw, and offer a lower-power source or mode when a user values
battery over live precision.

Garmin's own product page says the Approach S70 has 43,000+ preloaded courses
and, for the 47 mm model, up to 20 hours in GPS mode with the display always on
while golfing. That is a materially different cold path from downloading and
rendering a course at the first tee. The same page advertises performance-based
club suggestions and pairing with the Garmin Golf app, but does not disclose
the app's sampling interval, map refresh interval, or round battery percentage.

Our current post-#410/#411/#412 baseline is: the watch keeps an outdoor
`HKWorkoutSession`; Core Location is requested with no distance filter; a fix
is published after a 2 m move, a 3 m accuracy change, a 1 m/s speed or speed
accuracy change, or every 5 s; heading is enabled only on the flag-direction
page; and the hole map is a pre-rendered image delivered by the phone. The
remaining weakness is architectural: each published fix can still invalidate
the whole SwiftUI round tree, including the map image.

## Commercial products

| Product | Publicly confirmed behavior | What is not published | Design implication |
|---|---|---|---|
| Garmin Approach S70 / Garmin Golf | S70 product page advertises 43,000+ preloaded courses, performance-based club suggestions, Garmin Golf pairing, and GPS mode up to 20 h on 47 mm (15 h on 42 mm). | No public fixed GPS cadence, map redraw cadence, or percentage per 18 holes for the client/watch. | Preloaded/local course data and a watch-side round path explain much of the instant start. Treat Garmin's fast path as a data-availability property before treating it as a rendering optimization. |
| Golfshot | Its wearable page advertises Apple Watch real-time front/center/back distances, hazards/targets on 47,000+ courses, scoring and automatic shot tracking. Its GPS page advertises local course maps and real-time distances. | No interval, wrist-down policy, or battery percentage in the public pages reviewed. | Keep the map/course package local and update the small distance/shot state independently from the map. |
| Hole19 | The Apple device page describes phone + Apple Watch synchronized play. The GPS page says previously downloaded courses work offline and distances update as the player walks; it exposes front/center/back and a draggable target. | No fixed sampling interval or battery percentage. | A pre-round download and a local package are part of the expected UX; the live loop should not wait on a server. |
| 18Birdies | Wearables documentation says watch distances use the location available to the watch; non-cellular watches need the phone nearby. Apple Watch Map View requires a nearby paired iPhone and GPS on both devices. GPS settings include an explicit Low Battery Mode that can reduce refresh rates. Smart Tracking uses watch motion sensors and can start a round on the watch. | No public GPS rate or measured %/18 holes. | A user-selectable low-power policy is normal. Map and shot tracking can have different freshness requirements. |
| Arccos | The Apple Watch page says Series 6+ is optimized for watch GPS. It explicitly says watch GPS has the largest battery impact and can be turned off so distances come from the phone; phone GPS requires the phone nearby. It also supports watch shot tracking and rangefinder modes. | No public percentage per round or fixed cadence. | Phone-GPS fallback is a proven, understandable battery tradeoff. It must be explicit about phone proximity and stale-link behavior. |
| SwingU | Support says the phone must remain within Bluetooth range for the Apple Watch. It advises caching course images on Wi-Fi (18–30 MB for a course; another support page says about 30–45 s for all 18 holes). Its battery article identifies the screen as the largest contributor and recommends turning it off between shots. | No GPS interval or round percentage. | The “prime before leaving” flow is a direct model for our course package prefetch; display time matters as much as GPS. |

The absence of a public number is itself important: no vendor source found in
this pass supports claiming that a particular app consumes a known percentage
per round. Device model, screen brightness/always-on, cellular, temperature,
GPS sky view, map use, shot sensors and phone proximity dominate the result.

## Platform guidance

Apple's Energy Efficiency Guide says unnecessary location can prevent sleep,
keep location hardware powered, and drain the battery. It recommends stopping
updates when not needed, lowering accuracy when possible, using a distance
filter, and deferring background updates until a distance or time threshold.
The same guide cautions that high accuracy and continuous duration are costly.
Source: [Location Best Practices](https://developer.apple.com/library/archive/documentation/Performance/Conceptual/EnergyGuide-iOS/LocationBestPractices.html).

Apple's current `HKWorkoutSession` documentation says the session fine-tunes
watch sensors for the activity and that outdoor activities generate accurate
location data. It is the right primitive for a full outdoor round. Source:
[HKWorkoutSession](https://developer.apple.com/documentation/healthkit/hkworkoutsession)
and its machine-readable documentation data.

Apple's `isLuminanceReduced` documentation says watchOS normally sets it when
the user lowers the wrist while the display remains on, and recommends lower
brightness, stroked shapes and less bright colors while preserving contrast.
Source: [isLuminanceReduced](https://developer.apple.com/documentation/swiftui/environmentvalues/isluminancereduced).
The round should use that signal to freeze the bitmap/map layer and avoid
animations; it should not rebuild the full map just because a location arrived.

Apple's extended-runtime documentation is not a substitute for a golf workout:
the documented session types have limits (the background physical-therapy type
is one hour), and the system can suspend or cancel high-CPU work. Source:
[Using extended runtime sessions](https://developer.apple.com/documentation/watchkit/using-extended-runtime-sessions).
The existing workout session plus a watchdog is the appropriate long-round
mechanism.

Android's location battery guide identifies accuracy, frequency and latency as
the three direct battery levers. It recommends Fused Location Provider,
balanced/low-power modes where real-time high accuracy is not required, the
largest acceptable interval, and batching through `setMaxUpdateDelayMillis`
when latency permits. Source:
[About background location and battery life](https://developer.android.com/develop/sensors-and-location/location/battery).

Wear OS Health Services says its native sensor configurations are optimized for
power. `ExerciseClient` is for an active workout and can deliver rapid updates;
`PassiveMonitoringClient` is for long-lived, infrequent updates. Source:
[Health Services on Wear OS](https://developer.android.com/health-and-fitness/guides/health-services).
The equivalent product rule is to use a high-rate path only while a live
yardage/shot feature needs it, while the round/ambient path remains quiet.

## Open-source implementations inspected

These are implementation evidence, not product-quality benchmarks.

* [DeJong-Development/GolfPS-Android](https://github.com/DeJong-Development/GolfPS-Android/blob/master/app/src/main/java/com/dejongdevelopment/golfps/activity/PlayGolfActivity.kt)
  uses Android Fused Location with high accuracy, a 10 s interval and a 5 s
  fastest interval; it starts in `onResume` and removes updates in `onPause`.
  It is a useful lower-rate golf baseline, though it has no published battery
  measurement.
* [SpotGolf/SpotGolf](https://github.com/SpotGolf/SpotGolf) has a more complete
  iOS/watchOS split. Its location manager starts/stops by owner, keeps a raw
  callback separate from smoothed `lastLocation`, and uses a three-fix weighted
  smoother. Its watch services enable background location for the round, keep
  an outdoor `HKWorkoutSession`, and set the WatchConnectivity sender batch
  interval to 5 s. Its code comments explicitly distinguish “every raw fix”
  from what is persisted/sent.
* [moisesvargasjr/golf-caddie](https://github.com/moisesvargasjr/golf-caddie)
  keeps a `lastLocationReceivedAt` freshness clock independent of the fix's
  embedded timestamp, uses `distanceFilter = none` to avoid a stationary golfer
  becoming stale, and offers a precise-fix request with a 5 s timeout. Its
  watch `WorkoutKeeper` uses an outdoor golf workout to keep motion delivery
  alive. This is close to our current “no distance filter + freshness gate”
  rationale, but it still leaves UI throttling to the caller.
* [OpenTracksApp/OpenTracks](https://github.com/OpenTracksApp/OpenTracks/blob/main/src/main/java/de/dennisguse/opentracks/sensors/GpsManager.java)
  exposes user-configurable sampling and distance intervals, validates
  horizontal accuracy before recording, and keeps the location manager's raw
  status separate from stored track points. It demonstrates the value of
  separate acquisition, filtering and persistence/UI layers.
* Small open-source golf watch examples such as
  [GolfTrackerForWearOS](https://github.com/FelixLaakso/GolfTrackerForWearOS)
  and [GolfApp](https://github.com/yourmclovin/GolfApp) are scorekeeping/static
  course examples rather than measured GPS implementations; they provide no
  defensible cadence or battery number.

## Ranked recommendations for our watch

| Rank | Change | Expected battery/CPU effect | Live-yardage/AutoShot risk |
|---|---|---|---|
| 0 | Add round telemetry: battery at start/end, workout state, heading on-time, raw location count, published-fix count, map-body render count, and map-image decode count. Keep it local/opt-in for test builds. | No product drain; makes the next decision measurable instead of guessed. | None if diagnostics are passive. |
| 1 | Split `WatchRoundContainerView` into a static map/image layer and small live overlays. Make map geometry/image depend only on hole/image/target/hazard state; make distances/you/heading separate equatable views. | Highest likely CPU/display saving; every fix no longer redraws the bitmap. | Low. A missed dependency could leave an overlay stale, so add render/update tests. |
| 2 | Keep #412's 2 m/accuracy/speed/5 s publication gate for the active round, but add explicit modes: active rangefinder/shot capture, ambient/wrist-down, and no-live-feature. In the latter two, use a 5–10 m distance gate or deferred 10–15 s updates, then request an immediate fresh fix on foreground/feature entry. | Medium/high when standing, riding or waiting; GPS hardware can sleep more often. | Medium: too slow a mode can stale F/M/B or delay auto-shot/auto-hole. Keep high-rate mode for the active feature and test transitions. |
| 3 | Use `isLuminanceReduced`/Wear OS ambient callbacks to freeze the map bitmap, remove animations and lower redraw frequency. Keep the workout session and data acquisition policy independent. | Medium display/CPU saving during most wrist-down time. | Low for yardage if numeric overlay has its own freshness policy; medium if the implementation stops acquisition accidentally. |
| 4 | Add a Low Battery policy modeled on 18Birdies: prefer phone GPS via WatchConnectivity when the phone is nearby; otherwise relax location/heading and keep shot detection only if the user enabled it. Show the choice in settings, not in the live map. | High watch savings when phone GPS is used; little extra watch GPS work. | Medium/high: Bluetooth reachability and phone/watch position differ; require freshness/accuracy gates and fall back to watch GPS. |
| 5 | Prefetch the complete course package and all hole bitmaps before the round; during play, read local files and transfer only the next missing/changed image. Never make a server request part of a hole-screen render. | Removes network waits and repeated decode work; indirect battery saving. | Low; package revision/atomic activation must be tested. |
| 6 | Keep heading limited to the flag-direction page as #412 does; consider a 5–10° heading filter and discard heading updates while ambient. | Small/medium saving when the player is not aiming at the flag. | Low/medium: arrow can lag or be less stable; measure pointing error before changing 2°. |
| 7 | Keep the outdoor workout and watchdog from #410/#412, but collect failure/restart telemetry. Do not use extended runtime sessions for an 18-hole round. | Preserves background sensor delivery without an extra session. | Low; a failed workout must degrade to manual GPS rather than silently stop. |

## Proposed acceptance experiment

Run three complete 18-hole rounds on the same watch model, course and weather
as far as practical, with brightness/always-on and cellular held constant:

1. Current build (control).
2. Static-map/live-overlay split with current 5 s publication gate.
3. Split plus ambient/adaptive location policy, and a separate phone-GPS
   fallback run if the watch supports it.

Record starting/ending battery percentage, elapsed time, workout interruptions,
GPS accuracy samples, time-to-first-valid-fix, raw/published fix counts, map
render/decode counts, distance age at each shot, AutoShot candidate latency,
and missed/late hole advances. Report median and worst-case; one round cannot
establish a percentage claim. A device test is required because simulator and
server render benchmarks cannot predict watch GPS/radio/display drain.

## Source index

* Garmin: https://www.garmin.com/en-US/p/847706
* Apple location energy: https://developer.apple.com/library/archive/documentation/Performance/Conceptual/EnergyGuide-iOS/LocationBestPractices.html
* Apple `HKWorkoutSession`: https://developer.apple.com/documentation/healthkit/hkworkoutsession
* Apple reduced luminance: https://developer.apple.com/documentation/swiftui/environmentvalues/isluminancereduced
* Apple extended runtime: https://developer.apple.com/documentation/watchkit/using-extended-runtime-sessions
* Android location battery: https://developer.android.com/develop/sensors-and-location/location/battery
* Wear OS Health Services: https://developer.android.com/health-and-fitness/guides/health-services
* Golfshot wearables: https://golfshot.com/best-golf-app-apple-watch
* Golfshot GPS: https://golfshot.com/best-golf-gps-app
* Hole19 Apple devices: https://www.hole19golf.com/hole19/devices/apple
* Hole19 GPS/offline: https://www.hole19golf.com/hole19/features/gps-yardages
* 18Birdies wearables: https://help.18birdies.com/article/272-wearables-overview
* 18Birdies Apple Watch: https://help.18birdies.com/article/273-using-18birdies-on-apple-watch
* 18Birdies low-battery settings: https://help.18birdies.com/article/546-adjust-gps-settings
* 18Birdies Apple Watch map: https://help.18birdies.com/article/732-apple-watch-map-view
* Arccos Apple Watch: https://www.arccosgolf.com/pages/apple-watch
* SwingU Apple Watch setup: https://help.swingu.com/article/196-setting-up-apple-watch
* SwingU offline cache: https://help.swingu.com/article/34-do-i-need-an-active-internet-connection-while-on-the-course
* SwingU battery: https://help.swingu.com/article/4-how-do-i-conserve-battery-life-on-the-course
