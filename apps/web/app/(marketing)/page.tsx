import Link from "next/link";
import { SignedIn, SignedOut } from "@clerk/nextjs";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[#09090b] text-white">
      {/* Nav */}
      <nav className="fixed top-0 left-0 right-0 z-50 border-b border-white/5 bg-[#09090b]/80 backdrop-blur-xl">
        <div className="max-w-6xl mx-auto flex items-center justify-between px-6 h-16">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center">
              <span className="text-black font-bold text-sm">P</span>
            </div>
            <span className="font-bold text-lg tracking-tight">Porter</span>
          </Link>

          <div className="flex items-center gap-3">
            <Link href="/docs" className="text-sm text-zinc-400 hover:text-white transition-colors px-3 py-2">
              Docs
            </Link>
            <a href="https://github.com/Th3UrBanGuy/porter" target="_blank" rel="noopener noreferrer" className="text-sm text-zinc-400 hover:text-white transition-colors px-3 py-2">
              GitHub
            </a>
            <SignedOut>
              <Link href="/sign-in" className="text-sm font-medium text-white hover:text-zinc-300 transition-colors px-4 py-2">
                Sign in
              </Link>
              <Link href="/sign-up" className="text-sm font-semibold bg-white text-black hover:bg-zinc-200 px-4 py-2 rounded-lg transition-colors">
                Get Started
              </Link>
            </SignedOut>
            <SignedIn>
              <Link href="/dashboard" className="text-sm font-semibold bg-white text-black hover:bg-zinc-200 px-4 py-2 rounded-lg transition-colors">
                Dashboard
              </Link>
            </SignedIn>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="pt-32 pb-20 px-6">
        <div className="max-w-4xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 mb-8 text-xs font-medium text-orange-400 bg-orange-500/10 border border-orange-500/20 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-orange-500 animate-pulse" />
            Open Source &middot; Self-Hosted
          </div>

          <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight leading-[1.1] mb-6">
            Expose local services
            <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-orange-400 via-orange-500 to-orange-600">
              to the internet
            </span>
          </h1>

          <p className="text-lg md:text-xl text-zinc-400 max-w-2xl mx-auto mb-10 leading-relaxed">
            Enter a port, pick a subdomain, click Launch.
            <br className="hidden sm:block" />
            Porter creates Cloudflare Tunnels automatically — no DNS config, no API tokens, no hassle.
          </p>

          <div className="flex items-center justify-center gap-4">
            <SignedOut>
              <Link href="/sign-up" className="px-7 py-3.5 text-sm font-semibold bg-white text-black hover:bg-zinc-200 rounded-xl transition-colors">
                Get Started Free
              </Link>
            </SignedOut>
            <SignedIn>
              <Link href="/dashboard" className="px-7 py-3.5 text-sm font-semibold bg-white text-black hover:bg-zinc-200 rounded-xl transition-colors">
                Go to Dashboard
              </Link>
            </SignedIn>
            <Link href="/docs" className="px-7 py-3.5 text-sm font-medium bg-white/5 text-white hover:bg-white/10 border border-white/10 rounded-xl transition-colors">
              Read Docs
            </Link>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="py-20 px-6 border-t border-white/5">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold mb-4">How it works</h2>
            <p className="text-zinc-400 text-lg">Three steps to expose any local service</p>
          </div>

          <div className="grid md:grid-cols-3 gap-8">
            {[
              { step: "1", title: "Install Connector", desc: "Run one command on your machine. The connector links your device to Porter.", code: "npx porter-connect --token xxx" },
              { step: "2", title: "Create Tunnel", desc: "Pick a subdomain and port. Porter handles DNS, SSL, and tunnel configuration.", code: "subdomain: app / port: 3000" },
              { step: "3", title: "You're Live", desc: "Your service is accessible at https://app.kalandar.me instantly.", code: "https://app.kalandar.me" },
            ].map((item) => (
              <div key={item.step}>
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-8 h-8 rounded-lg bg-orange-500/10 border border-orange-500/20 flex items-center justify-center text-orange-500 text-sm font-bold">{item.step}</div>
                  <h3 className="text-lg font-semibold">{item.title}</h3>
                </div>
                <p className="text-zinc-400 text-sm leading-relaxed mb-4">{item.desc}</p>
                <div className="px-4 py-2.5 bg-white/5 border border-white/5 rounded-lg font-mono text-xs text-zinc-500">{item.code}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="py-20 px-6 border-t border-white/5">
        <div className="max-w-6xl mx-auto">
          <div className="grid md:grid-cols-2 gap-6">
            {[
              { title: "One-Click Deploy", desc: "Enter a port and subdomain. Porter handles DNS, SSL, and tunnel configuration automatically.", icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg> },
              { title: "Custom Connectors", desc: "Install a lightweight connector on your machine. Manage tunnels remotely from anywhere.", icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101" /><path strokeLinecap="round" strokeLinejoin="round" d="M10.172 13.828a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.102 1.101" /></svg> },
              { title: "Multi-Domain", desc: "Works with any Cloudflare zone. Connect multiple domains and manage all your tunnels.", icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945" /><path strokeLinecap="round" strokeLinejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg> },
              { title: "Real-Time Status", desc: "See tunnel and connector status in real-time. Know instantly if your service is live.", icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg> },
            ].map((feature) => (
              <div key={feature.title} className="p-6 rounded-2xl bg-white/[0.02] border border-white/5 hover:border-white/10 transition-colors group">
                <div className="w-10 h-10 rounded-xl bg-white/5 border border-white/5 flex items-center justify-center text-orange-500 mb-4 group-hover:border-orange-500/20 transition-colors">{feature.icon}</div>
                <h3 className="font-semibold mb-2">{feature.title}</h3>
                <p className="text-sm text-zinc-400 leading-relaxed">{feature.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20 px-6 border-t border-white/5">
        <div className="max-w-2xl mx-auto text-center">
          <h2 className="text-3xl md:text-4xl font-bold mb-4">Ready to expose your first service?</h2>
          <p className="text-zinc-400 text-lg mb-8">Free and open source. No credit card required.</p>
          <SignedOut>
            <Link href="/sign-up" className="inline-block px-8 py-4 text-base font-semibold bg-white text-black hover:bg-zinc-200 rounded-xl transition-colors">
              Get Started Free
            </Link>
          </SignedOut>
          <SignedIn>
            <Link href="/dashboard" className="inline-block px-8 py-4 text-base font-semibold bg-white text-black hover:bg-zinc-200 rounded-xl transition-colors">
              Go to Dashboard
            </Link>
          </SignedIn>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/5 py-8 px-6">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-zinc-500">
          <span>Built by Tect0nic</span>
          <div className="flex items-center gap-6">
            <Link href="/docs" className="hover:text-white transition-colors">Docs</Link>
            <a href="https://github.com/Th3UrBanGuy/porter" target="_blank" rel="noopener noreferrer" className="hover:text-white transition-colors">GitHub</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
