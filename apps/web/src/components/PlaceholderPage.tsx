export function PlaceholderPage({ title }: { title: string }) {
  return (
    <div>
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="mt-1 text-xs text-txtDim">
        Coming soon. This area lights up once its backend endpoints ship.
      </p>
      <div className="mt-4 rounded-lg border border-dashed border-[#2a3647] bg-accent/5 p-3 text-[11px] text-txtDim">
        Placeholder â€” see <code>mocks/index.html</code> for the target design of this screen.
      </div>
    </div>
  )
}