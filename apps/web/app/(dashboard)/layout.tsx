import Link from "next/link";
import { UserButton } from "@clerk/nextjs";
import { currentUser } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

const navItems = [
  { label: "Dashboard", href: "/dashboard", icon: "◻" },
  { label: "Tunnels", href: "/tunnels", icon: "◉" },
  { label: "Connectors", href: "/connectors", icon: "◎" },
  { label: "Settings", href: "/settings", icon: "⚙" },
];

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await currentUser();
  if (!user) redirect("/sign-in");

  return (
    <div className="min-h-screen bg-gray-950 text-white flex">
      {/* Sidebar */}
      <aside className="w-64 border-r border-white/10 flex flex-col hidden md:flex">
        <div className="p-4 border-b border-white/10">
          <Link href="/dashboard" className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center text-black font-bold text-sm">
              P
            </div>
            <span className="font-bold text-lg">Porter</span>
          </Link>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="flex items-center gap-3 px-3 py-2 text-sm text-gray-400 hover:text-white hover:bg-white/5 rounded-lg transition-colors"
            >
              <span className="text-base">{item.icon}</span>
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="p-4 border-t border-white/10">
          <div className="flex items-center gap-3">
            <UserButton
              appearance={{
                elements: {
                  avatarBox: "w-8 h-8",
                },
              }}
            />
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium truncate">
                {user.firstName || user.emailAddresses[0]?.emailAddress}
              </div>
              <div className="text-xs text-gray-500 truncate">
                {user.emailAddresses[0]?.emailAddress}
              </div>
            </div>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        {/* Mobile header */}
        <header className="md:hidden flex items-center justify-between p-4 border-b border-white/10">
          <Link href="/dashboard" className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center text-black font-bold text-sm">
              P
            </div>
            <span className="font-bold">Porter</span>
          </Link>
          <UserButton />
        </header>
        <div className="p-6">{children}</div>
      </main>
    </div>
  );
}
