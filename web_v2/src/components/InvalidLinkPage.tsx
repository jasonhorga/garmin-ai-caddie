// Clean "needs a valid link" page (multiplayer foundation, stage 1).
//
// Shown when a visitor has no usable credential — no player token in the URL
// and no owner admin token — on a player-facing deployment, or when a player
// link is invalid/expired. It intentionally exposes nothing: no player names,
// no owner/admin controls, no navigation, and it triggers no data requests.
// The copy must not reveal whether any player exists.
export function InvalidLinkPage() {
  return (
    <div className="invalid-link-page">
      <section className="panel empty-state invalid-link-card" aria-labelledby="invalid-link-title">
        <p className="eyebrow">访问受限</p>
        <h1 id="invalid-link-title">需要有效链接</h1>
        <p>请使用你收到的专属链接打开本页面。</p>
        <p className="empty-state-hint">链接可能已失效或不完整,请向分享链接给你的人重新获取。</p>
      </section>
    </div>
  )
}
