import { test } from '@playwright/test'
import { mockApi } from './history-visual.smoke.spec'

// A PACED walkthrough of the web product for a demo SCREEN RECORDING (Playwright `video: 'on'` in the
// config captures it). Unlike the fast smoke specs (4–7s, unwatchable), each step pauses ~2.6s so the
// viewer can read the screen. Robust by design: a missing/renamed control is logged and skipped rather
// than failing the whole recording, so the video always completes.
test('paced demo walkthrough (for the web demo video)', async ({ page }) => {
  test.setTimeout(150_000)
  await mockApi(page)

  const pause = (ms = 2600) => page.waitForTimeout(ms)
  const tap = async (name: string, scopeNav = false) => {
    try {
      const root = scopeNav ? page.getByRole('navigation', { name: '辅助导航' }) : page
      const b = root.getByRole('button', { name, exact: true }).first()
      if (await b.isVisible({ timeout: 3500 })) {
        await b.click()
        await pause()
        return
      }
    } catch {
      /* fall through */
    }
    try {
      const t = page.getByText(name, { exact: false }).first()
      if (await t.isVisible({ timeout: 2000 })) {
        await t.click()
        await pause()
      }
    } catch {
      /* skip missing control — keep the recording going */
    }
  }

  // 复盘 landing = the round-review workbench (round list + hole scores + 逐洞落点图).
  await page.goto('/')
  await pause(3200)

  // 统计 → 趋势总览: KPI tiles + 差点/失误 charts + 成绩构成 + 按球场.
  await tap('统计')
  await tap('趋势总览', true)
  await pause(2000)
  await tap('强弱分析', true)

  // Back to 复盘 and open a round's 逐洞 review with the 落点图.
  await tap('复盘')
  await tap('回放 Black Knight B 05-20')

  // 备战 pre-round prep + 球童沙盘 (AI caddie), then 球包 (club bag).
  await tap('备战')
  await tap('球童沙盘')
  await tap('球包')
  await pause(2000)
})
