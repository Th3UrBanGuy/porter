import Link from "next/link";
import { SignedIn, SignedOut, SignInButton } from "@clerk/nextjs";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-950 via-gray-900 to-gray-950 text-white">
      {/* Nav */}
      <nav className="flex items-center justify-between px-6 py-4 max-w-7xl mx-auto">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center text-black font-bold text-sm">
            P
          </div>
          <span className="font-bold text-lg">Porter</span>
        </div>
        <div className="flex items-center gap-4">
          <Link href="/docs" className="text-gray-400 hover:text-white text-sm transition-colors">
            Docs
          </Link>
          <SignedOut>
            <SignInButton mode="modal">
              <button className="px-4 py-2 text-sm font-medium bg-white/10 hover:bg-white/20 rounded-lg transition-colors">
                Sign In
              </button>
            </SignInButton>
          </SignedOut>
          <SignedIn>
            <Link href="/dashboard" className="px-4 py-2 text-sm font-medium bg-orange-500 hover:bg-orange-600 text-black rounded-lg transition-colors">
              Dashboard
            </Link>
          </SignedIn>
        </div>
      </nav>

      {/* Hero */}
      <section className="max-w-7xl mx-auto px-6 pt-20 pb-32 text-center">
        <div className="inline-block px-3 py-1 mb-6 text-xs font-medium bg-orange-500/10 text-orange-400 rounded-full border border-orange-500/20">
          Open Source &middot; Self-Hosted
        </div>
        <h1 className="text-5xl md:text-7xl font-bold tracking-tight mb-6">
          Expose local services
          <br />
          <span className="bg-gradient-to-r from-orange-400 to-orange-600 bg-clip-text text-transparent">
            to the internet
          </span>
        </h1>
        <p className="text-lg text-gray-400 max-w-2xl mx-auto mb-10">
          Enter a port, pick a subdomain, click Launch. Porter creates Cloudflare Tunnels automatically — no DNS config, no API tokens, no hassle.
        </p>
        <div className="flex items-center justify-center gap-4">
          <SignedOut>
            <SignInButton mode="modal">
              <button className="px-6 py-3 text-sm font-semibold bg-orange-500 hover:bg-orange-600 text-black rounded-lg transition-colors">
                Get Started Free
              </button>
            </SignInButton>
          </SignedOut>
          <SignedIn>
            <Link href="/dashboard" className="px-6 py-3 text-sm font-semibold bg-orange-500 hover:bg-orange-600 text-black rounded-lg transition-colors">
              Go to Dashboard
            </Link>
          </SignedIn>
          <Link href="/docs" className="px-6 py-3 text-sm font-medium bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg transition-colors">
            Read Docs
          </Link>
        </div>
      </section>

      {/* Features */}
      <section className="max-w-7xl mx-auto px-6 pb-32">
        <div className="grid md:grid-cols-3 gap-6">
          {[
            {
              title: "One-Click Deploy",
              description: "Enter a port and subdomain. Porter handles DNS, SSL, and tunnel configuration automatically.",
              icon: "⚡",
            },
            {
              title: "Custom Connectors",
              description: "Install a lightweight connector on your machine. Manage tunnels remotely from anywhere.",
              icon: "🔗",
            },
            {
              title: "Multi-Cloud Ready",
              description: "Works with any Cloudflare zone. Connect multiple domains and manage all your tunnels in one place.",
              icon: "☁️",
            },
          ].map((feature) => (
            <div
              key={feature.title}
              className="p-6 rounded-2xl bg-white/5 border border-white/10 hover:border-orange-500/30 transition-colors"
            >
              <div className="text-3xl mb-4">{feature.icon}</div>
              <h3 className="font-semibold mb-2">{feature.title}</h3>
              <p className="text-sm text-gray-400">{feature.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/10 py-8 px-6">
        <div className="max-w-7xl mx-auto flex items-center justify-between text-sm text-gray-500">
          <span>Built by Tect0nic</span>
          <div className="flex items-center gap-4">
            <Link href="/docs" className="hover:text-white transition-colors">Docs</Link>
            <a href="https://github.com/Th3UrBanGuy/porter" target="_blank" rel="noopener noreferrer" className="hover:text-white transition-colors">GitHub</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
