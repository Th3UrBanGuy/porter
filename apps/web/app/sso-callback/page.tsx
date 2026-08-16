"use client";

import { useClerk } from "@clerk/nextjs";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function SSOCallback() {
  const { handleRedirectCallback } = useClerk();
  const router = useRouter();

  useEffect(() => {
    handleRedirectCallback({}).then(() => {
      router.push("/dashboard");
    }).catch(() => {
      router.push("/sign-in");
    });
  }, [handleRedirectCallback, router]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#09090b]">
      <div className="flex items-center gap-3 text-zinc-400">
        <div className="w-5 h-5 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
        <span className="text-sm">Completing sign in...</span>
      </div>
    </div>
  );
}
