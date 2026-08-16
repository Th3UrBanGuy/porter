"use client";

import { SignIn } from "@clerk/nextjs";
import Link from "next/link";

export default function SignInPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[#09090b] px-4">
      <div className="w-full max-w-md">
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-sm text-zinc-400 hover:text-white mb-8 transition-colors"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M10 12L6 8L10 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          Back to home
        </Link>

        <div className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center">
            <span className="text-black font-bold text-lg">P</span>
          </div>
          <div>
            <h1 className="text-xl font-bold">Welcome back</h1>
            <p className="text-sm text-zinc-500">Sign in to Porter</p>
          </div>
        </div>

        <SignIn
          routing="path"
          path="/sign-in"
          signUpUrl="/sign-up"
          appearance={{
            elements: {
              rootBox: "w-full",
              card: "w-full bg-transparent border-0 shadow-none p-0",
              header: "hidden",
              socialButtonsBlockButton: "w-full bg-[#09090b] border border-white/10 text-white hover:bg-[#18181b] hover:border-white/20 rounded-lg h-11 text-sm font-medium transition-all mb-2",
              socialButtonsProviderIcon: "size-4",
              dividerLine: "bg-white/10",
              dividerText: "text-zinc-500 text-xs",
              formFieldLabel: "text-zinc-400 text-sm",
              formFieldInput: "bg-[#09090b] border border-white/10 text-white rounded-lg h-11 focus:border-orange-500 focus:ring-2 focus:ring-orange-500/20",
              formButtonPrimary: "bg-orange-500 hover:bg-orange-600 text-black font-semibold rounded-lg h-11 text-sm transition-colors shadow-none",
              footerActionLink: "text-orange-500 hover:text-orange-400 text-sm",
              footerActionText: "text-zinc-500 text-sm",
              identityPreviewEditButton: "text-orange-500",
              formResendCodeLink: "text-orange-500",
              otpCodeFieldInput: "bg-[#09090b] border border-white/10 text-white",
            },
          }}
        />

        <p className="mt-6 text-center text-sm text-zinc-500">
          Don&apos;t have an account?{" "}
          <Link href="/sign-up" className="text-orange-500 hover:text-orange-400 font-medium">
            Sign up
          </Link>
        </p>
      </div>
    </div>
  );
}
