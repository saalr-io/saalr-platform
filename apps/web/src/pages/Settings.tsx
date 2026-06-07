import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { usePortal } from '../features/billing/hooks'
import { useOptIn, useUpdateProfile, useRequestDeletion } from '../features/account/hooks'

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-line bg-panel p-5 space-y-4">
      <h2 className="text-[13px] font-semibold uppercase tracking-widest text-txtFaint">{title}</h2>
      {children}
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] font-medium text-txtDim">{label}</span>
      {children}
    </div>
  )
}

export function Settings() {
  const { me } = useAuth()
  const portal = usePortal()
  const optIn = useOptIn()
  const updateProfile = useUpdateProfile()
  const deletionMutation = useRequestDeletion()

  const [tz, setTz] = useState(me?.preferred_tz ?? '')
  const [locale, setLocale] = useState(me?.preferred_locale ?? '')
  const [deleteConfirm, setDeleteConfirm] = useState('')

  const deletionDone = deletionMutation.isSuccess || me?.deletion_requested

  return (
    <div className="mx-auto max-w-2xl space-y-6 py-6">
      <h1 className="text-xl font-semibold text-txt">Settings</h1>

      {/* Account */}
      <Section title="Account">
        <Field label="Email">
          <span className="text-[13px] text-txt">{me?.user.email}</span>
        </Field>
        <Field label="Plan">
          <span className="text-[13px] text-txt">{me?.tier}</span>
        </Field>
        <button
          onClick={() => portal.mutate()}
          disabled={portal.isPending}
          className="mt-1 rounded-lg border border-line px-4 py-2 text-[13px] font-medium text-accent hover:bg-panel/60 disabled:opacity-50 transition-colors"
        >
          {portal.isPending ? 'Opening…' : 'Manage subscription'}
        </button>
      </Section>

      {/* Profile */}
      <Section title="Profile">
        <Field label="Timezone">
          <input
            data-testid="tz-input"
            type="text"
            value={tz}
            onChange={(e) => setTz(e.target.value)}
            placeholder="e.g. America/New_York"
            className="rounded-lg border border-line bg-canvas px-3 py-2 text-[13px] text-txt outline-none focus:border-accent"
          />
        </Field>
        <Field label="Locale">
          <input
            data-testid="locale-input"
            type="text"
            value={locale}
            onChange={(e) => setLocale(e.target.value)}
            placeholder="e.g. en-US"
            className="rounded-lg border border-line bg-canvas px-3 py-2 text-[13px] text-txt outline-none focus:border-accent"
          />
        </Field>
        <button
          onClick={() => updateProfile.mutate({ preferred_tz: tz, preferred_locale: locale })}
          disabled={updateProfile.isPending}
          className="rounded-lg bg-accent px-4 py-2 text-[13px] font-medium text-white hover:opacity-90 disabled:opacity-50 transition-opacity"
        >
          {updateProfile.isPending ? 'Saving…' : 'Save'}
        </button>
      </Section>

      {/* Email preferences */}
      <Section title="Email Preferences">
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            data-testid="optin-toggle"
            type="checkbox"
            checked={me?.marketing_opt_in ?? false}
            onChange={(e) => optIn.mutate(e.target.checked)}
            className="h-4 w-4 rounded border-line accent-accent"
          />
          <span className="text-[13px] text-txt">Receive marketing emails and product updates</span>
        </label>
      </Section>

      {/* Danger zone */}
      <Section title="Danger Zone">
        {deletionDone ? (
          <p className="text-[13px] text-neg">Deletion requested — we'll process it shortly.</p>
        ) : (
          <>
            <p className="text-[13px] text-txtDim">
              To request account deletion, type <strong className="text-txt">DELETE</strong> in the box below and confirm.
            </p>
            <Field label="Type DELETE to confirm">
              <input
                data-testid="delete-confirm-input"
                type="text"
                value={deleteConfirm}
                onChange={(e) => setDeleteConfirm(e.target.value)}
                placeholder="DELETE"
                className="rounded-lg border border-line bg-canvas px-3 py-2 text-[13px] text-txt outline-none focus:border-neg"
              />
            </Field>
            <button
              data-testid="delete-request-btn"
              onClick={() => deletionMutation.mutate()}
              disabled={deleteConfirm !== 'DELETE' || deletionMutation.isPending}
              className="rounded-lg border border-neg px-4 py-2 text-[13px] font-medium text-neg hover:bg-neg/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {deletionMutation.isPending ? 'Requesting…' : 'Request account deletion'}
            </button>
          </>
        )}
      </Section>
    </div>
  )
}
