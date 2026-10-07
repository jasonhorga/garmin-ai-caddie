HISTORICAL ARCHIVE — NON-AUTHORITATIVE

Claude restored. PR #391 is open; #387/#388/#389/#390 are merged and their
branches deleted. PR #391 exact head is **649059876e690a80fd90b9f3c896e4d0f511580b**
on `claude/live-lightweight-map-fit-20261007`. Ordinary CI **37583640893** and
automatic Native CI **37583640781** passed; design (89 iOS) and Watch (47)
artifacts were checked, with only the four expected iOS lightweight-map frames
different from the #387 baseline. Required live run **37587781499** is red:
9/10 selected iOS tests passed, but `RealFlowUITests.testCaptureRealAppFlow`
failed on three attempts with `NSURLError -1001` for
`GET /api/v2/history/rounds?hasShots=true&limit=120`; preflight/course discovery
were HTTP 200 and the origin log has no matching request. No live 09d,
b4b2-02, or b4b2-04 map frame was captured. P1 evidence-block comment
**6033977600** posted; do not merge until a successful live capture exists.
Evidence: `operations/pr391-64905987-20261007/observed-live-37587781499/`.

