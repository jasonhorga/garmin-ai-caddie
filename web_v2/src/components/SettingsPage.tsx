import type { ProductPage } from '../navigation'
import type { ProductSettingsResponse } from '../types'
import { oauthCapabilityZh } from '../zhLabels'

interface SettingsPageProps {
  onNavigate: (page: ProductPage) => void
  settings?: ProductSettingsResponse | null
  settingsError?: string | null
}

// Closed status vocabulary emitted by server_v2/product_settings.py (data
// sources, AI providers, live apps) plus the OAuth capability-matrix states
// (connectors/garmin_oauth.py). Unknown tokens fall through raw.
const SETTINGS_STATE_ZH: Record<string, string> = {
  ready: '就绪',
  configured: '已配置',
  missing_key: '缺密钥',
  missing_config: '缺配置',
  available: '可用',
  not_syncable: '不可同步',
  contract_ready: '契约就绪',
  bounded_context: '受限上下文',
  unproven: '未验证',
  possible: '可行',
  proven: '已验证',
  needs_golf_fit_validation: '需 FIT 验证',
  not_replacement: '非替代方案',
  not_available: '不可用',
}

function settingsStateZh(raw: string): string {
  return SETTINGS_STATE_ZH[raw] ?? raw
}

export function SettingsPage({ onNavigate, settings, settingsError }: SettingsPageProps) {
  const dataSources = Array.isArray(settings?.dataSources) ? settings.dataSources : []
  const providers = Array.isArray(settings?.aiProviders?.providers) ? settings.aiProviders.providers : []
  const cnSession = dataSources.find((source) => asString(source.id) === 'garmin_cn_web_session')
  const oauth = dataSources.find((source) => asString(source.id) === 'garmin_oauth')
  const oauthProbe = asRecord(oauth?.probe)
  const oauthExchange = asRecord(oauthProbe.tokenExchange)
  const oauthResourceProbe = asRecord(oauthProbe.resourceProbe)
  const oauthMissing = asStringList(oauthProbe.missing)
  const oauthExchangeMissing = asStringList(oauthExchange.missing)
  const oauthResourceChecks = asStringList(oauthResourceProbe.checks)
  const oauthCapabilities = asRecords(oauth?.capabilityMatrix).slice(0, 3)
  const oauthSteps = asStringList(oauthProbe.manualSteps).slice(0, 3)
  const activeProvider = providers.find((provider) => asString(provider.id) === settings?.aiProviders?.activeProvider)
  const geminiCliProvider = providers.find((provider) => asString(provider.id) === 'gemini_cli_oauth')
  const ios = asRecord(settings?.liveApps?.ios)
  const watch = asRecord(settings?.liveApps?.watch)
  const privacy = asRecord(settings?.privacy)
  const iosCaptures = formatSettingList(ios.captures, ['gps', 'club', 'score'])
  const watchInputs = formatSettingList(watch.inputs, ['club', 'distance', 'score', 'putt', 'penalty'])

  return (
    <section className="settings-page" aria-label="后端配置工作区">
      <div className="section-head stats-head">
        <div>
          <p className="eyebrow">控制面</p>
          <h1>后端配置</h1>
          <p>连接器、AI 引擎、实战应用、隐私与订正控制。</p>
        </div>
        {settingsError ? <span className="semantic-chip quality-missing">{settingsError}</span> : null}
      </div>

      <div className="settings-grid">
        <article className="settings-item" aria-label="数据源配置">
          <div className="settings-item-main">
            <h2>数据源</h2>
            <div className="setting-chip-row">
              <span className="setting-chip setting-primary">CN 网页会话</span>
              <span className="setting-chip setting-secondary">OAuth 可行性</span>
              <span className="setting-chip">本地快照</span>
              {cnSession ? <span className="setting-chip setting-primary">{settingsStateZh(asString(cnSession.state) ?? '未知')}</span> : null}
              {oauth ? <span className="setting-chip setting-secondary">{settingsStateZh(asString(oauth.state) ?? '未知')}</span> : null}
            </div>
            <div className="settings-fact-grid">
              <span>记分卡</span>
              <b>会话连接器</b>
              <span>击球行</span>
              <b>标准化快照</b>
              <span>几何</span>
              <b>prodgeometry</b>
              <span>凭据策略</span>
              <b>不存储 Garmin 密码</b>
            </div>
            {oauthProbe.schema ? (
              <div className="settings-oauth-probe" aria-label="OAuth 可行性探测">
                <div>
                  <span>OAuth 探测</span>
                  <b>{asString(oauthProbe.state) === 'ready_for_manual_consent' ? '可手动授权' : '未配置'}</b>
                </div>
                {oauthMissing.length ? <p>缺失 {oauthMissing.join(', ')}</p> : <p>同意请求使用已脱敏的配置参数。</p>}
                <div className="settings-oauth-probe-grid">
                  <span>授权码交换</span>
                  <b>{asBoolean(oauthExchange.ready, false) ? '就绪' : oauthExchangeMissing.length ? `缺失 ${oauthExchangeMissing.join(', ')}` : '未就绪'}</b>
                  <span>资源检查</span>
                  <b>{oauthResourceChecks.length ? oauthResourceChecks.join(', ') : 'user_id, permissions'}</b>
                </div>
                {oauthCapabilities.length ? (
                  <div className="settings-oauth-capabilities" aria-label="OAuth 能力矩阵">
                    {oauthCapabilities.map((capability) => (
                      <span key={asString(capability.key) ?? asString(capability.label) ?? 'capability'}>
                        {oauthCapabilityZh(asString(capability.key) ?? '')?.label ?? asString(capability.label) ?? 'Capability'}: {settingsStateZh(asString(capability.state) ?? '未知')}
                      </span>
                    ))}
                  </div>
                ) : null}
                {oauthSteps.length ? (
                  <ol>
                    {oauthSteps.map((step) => (
                      <li key={step}>{step}</li>
                    ))}
                  </ol>
                ) : null}
              </div>
            ) : null}
          </div>
          <button type="button" onClick={() => onNavigate('sync-quality')}>
            查看隐私控制
          </button>
        </article>

        <article className="settings-item" aria-label="AI 引擎配置">
          <div className="settings-item-main">
            <h2>AI 引擎</h2>
            <div className="setting-chip-row">
              {activeProvider ? <span className="setting-chip setting-primary">当前:{asString(activeProvider.label) ?? settings?.aiProviders.activeProvider}</span> : null}
              <span className="setting-chip setting-primary">静态规则</span>
              <span className={providerChipClass(settings, 'nvidia_nim')}>NVIDIA NIM</span>
              <span className={providerChipClass(settings, 'gemini_api_key')}>Gemini API</span>
              <span className={providerChipClass(settings, 'gemini_cli_oauth')}>Gemini CLI OAuth</span>
              <span className="setting-chip">Anthropic</span>
              {activeProvider ? <span className="setting-chip setting-primary">{settingsStateZh(asString(activeProvider.state) ?? '未知')}</span> : null}
            </div>
            <label className="setting-check">
              <input type="checkbox" checked={settings?.aiProviders?.factBindingRequired ?? true} readOnly />
              <span>必须绑定事实</span>
            </label>
            <div className="settings-fact-grid">
              <span>报告</span>
              <b>factsUsed + missingData</b>
              <span>球童解释</span>
              <b>仅决策事实</b>
              <span>CLI OAuth 刷新</span>
              <b>{asBoolean(geminiCliProvider?.refreshRequiresClientCredential, false) ? '令牌缓存 + 刷新需客户端凭据' : '仅本地开发'}</b>
            </div>
          </div>
          <button type="button" onClick={() => onNavigate('reports')}>
            打开报告控制
          </button>
        </article>

        <article className="settings-item" aria-label="实战应用配置">
          <div className="settings-item-main">
            <h2>实战应用</h2>
            <div className="setting-chip-row">
              <span className="setting-chip setting-primary">iOS 离线包</span>
              <span className="setting-chip setting-secondary">手表桥接</span>
              <span className="setting-chip">照片/视频上下文</span>
              {asString(ios.state) ? <span className="setting-chip">iOS {settingsStateZh(asString(ios.state) ?? '')}</span> : null}
              {asString(watch.state) ? <span className="setting-chip">Watch {settingsStateZh(asString(watch.state) ?? '')}</span> : null}
            </div>
            <div className="settings-fact-grid">
              <span>开局</span>
              <b>缓存离线包</b>
              <span>场上输入</span>
              <b>{iosCaptures}</b>
              <span>手表输入</span>
              <b>{watchInputs}</b>
              <span>赛后</span>
              <b>事件对账</b>
            </div>
          </div>
          <button type="button" onClick={() => onNavigate('sync-quality')}>
            打开实战准备
          </button>
        </article>

        <article className="settings-item" aria-label="隐私配置">
          <div className="settings-item-main">
            <h2>隐私与留存</h2>
            <div className="setting-check-grid">
              <label className="setting-check">
                <input type="checkbox" checked={asBoolean(privacy.adminProtectedWrites, true)} readOnly />
                <span>管理员保护写入</span>
              </label>
              <label className="setting-check">
                <input type="checkbox" checked={asBoolean(privacy.mediaRedaction, true)} readOnly />
                <span>媒体脱敏</span>
              </label>
              <label className="setting-check">
                <input type="checkbox" checked={asBoolean(privacy.localSnapshotsSurviveReauth, true)} readOnly />
                <span>重新登录保留本地快照</span>
              </label>
              <label className="setting-check">
                <input type="checkbox" checked={asBoolean(privacy.secretFreeStatusResponses, true)} readOnly />
                <span>状态响应不含密钥</span>
              </label>
            </div>
            <div className="settings-fact-grid">
              <span>会话材料</span>
              <b>仅密钥存储</b>
              <span>媒体字节</span>
              <b>可脱敏</b>
              <span>API 响应</span>
              <b>已移除私有路径</b>
            </div>
          </div>
          <button type="button" onClick={() => onNavigate('sync-quality')}>
            打开同步控制
          </button>
        </article>

        <article className="settings-item">
          <div className="settings-item-main">
            <h2>人工订正</h2>
            <div className="setting-chip-row">
              <span className="setting-chip">问题标签</span>
              <span className="setting-chip">成绩修正</span>
              <span className="setting-chip">球童反馈</span>
              <span className="setting-chip">天气备注</span>
            </div>
            <div className="settings-fact-grid">
              <span>原始事实</span>
              <b>不可变</b>
              <span>派生统计</span>
              <b>订正感知</b>
            </div>
          </div>
          <button type="button" onClick={() => onNavigate('corrections')}>
            打开订正
          </button>
        </article>
      </div>
    </section>
  )
}

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

function asStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(asString).filter((item): item is string => Boolean(item)) : []
}

function asRecords(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => item !== null && typeof item === 'object' && !Array.isArray(item)) : []
}

function asBoolean(value: unknown, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback
}

function formatSettingList(value: unknown, fallback: string[]): string {
  const rawValues = Array.isArray(value) ? value : fallback
  return rawValues
    .map(asString)
    .filter((item): item is string => Boolean(item))
    .map((item) => (item.toLowerCase() === 'gps' ? 'GPS' : item))
    .join(', ')
}

function providerChipClass(settings: ProductSettingsResponse | null | undefined, providerId: string): string {
  const providers = Array.isArray(settings?.aiProviders?.providers) ? settings.aiProviders.providers : []
  const provider = providers.find((row) => asString(row.id) === providerId)
  return asString(provider?.state) === 'configured' ? 'setting-chip setting-primary' : 'setting-chip'
}
