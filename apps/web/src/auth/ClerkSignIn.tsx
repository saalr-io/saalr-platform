import { SignIn } from '@clerk/clerk-react'
import { Logo } from '../components/Logo'

export function ClerkSignIn() {
  return (
    <div className="grid min-h-screen place-items-center" data-testid="clerk-signin">
      <div className="w-[360px] rounded-xl border border-line bg-gradient-to-b from-panel to-[#0b1018] p-6">
        <Logo size={24} descriptor />
        <div className="mt-6">
          <SignIn />
        </div>
      </div>
    </div>
  )
}
