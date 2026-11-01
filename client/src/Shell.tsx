import { Suspense, lazy, useEffect, useState } from "react";
import { Navigate, Outlet, Route, Routes, useLocation, Link } from "react-router-dom";
import { listNotifications } from "./api/alerts";
import { useApp, Text } from "./context";
import { Loading } from "./components";
import { BottomNav, PillNav } from "./nav";
import { EmptyState } from "./ui";
import { tt } from "./ui-strings";
import BuddyWelcome from "./buddy/BuddyWelcome";
import BuddyDock from "./buddy/BuddyDock";
import { BuddyProvider } from "./buddy/context";
import Home from "./pages/Home";

const Schemes = lazy(() => import("./pages/Schemes"));
const Scheme = lazy(() => import("./pages/Scheme"));
const Explain = lazy(() => import("./pages/Explain"));
const Ask = lazy(() => import("./pages/Ask"));
const Run = lazy(() => import("./pages/Run"));
const Runs = lazy(() => import("./pages/Runs"));
const Alerts = lazy(() => import("./pages/Alerts"));
const Locker = lazy(() => import("./pages/Locker"));
const Talk = lazy(() => import("./pages/Talk"));
const Civic = lazy(() => import("./pages/Civic"));
const CivicNew = lazy(() => import("./pages/CivicNew"));
const CivicTrack = lazy(() => import("./pages/CivicTrack"));

export function useUnread(profileId: string) {
  const [unread, setUnread] = useState(0);
  useEffect(() => {
    if (!profileId) return;
    const c = new AbortController();
    listNotifications(profileId, c.signal)
      .then((out) => setUnread(out.unread_count ?? 0))
      .catch(() => setUnread(0));
    return () => c.abort();
  }, [profileId]);
  return unread;
}

function Layout() {
  const { profileId, mode, lang } = useApp();
  const unread = useUnread(profileId);
  const { pathname } = useLocation();
  // Talk mode is a full-screen conversation, so the page itself provides its chrome.
  const bare = pathname === "/talk";
  if (!mode) return <Navigate to="/welcome" replace />;
  return (
    <>
      {!bare && <PillNav unread={unread} />}
      <main
        className={
          bare
            ? "p-0"
            : "mx-auto max-w-6xl px-4 pb-32 pt-5 md:px-8 md:pb-12"
        }
      >
        <Suspense fallback={<Loading message="Opening your page…" />}>
          <Outlet />
        </Suspense>
        {!bare && (
          <footer className="py-8 text-xs text-ink-soft">
            <Text
              value={
                "Adhikaar helps you understand and apply. Eligibility and final decisions belong to the official authority."
              }
            />
          </footer>
        )}
      </main>
      {!bare && <BottomNav unread={unread} />}
      <span hidden>{lang}</span>
    </>
  );
}

function NotFound() {
  const { lang } = useApp();
  return (
    <EmptyState
      title="404"
      action={<Link to="/">{tt(lang, "navForYou")}</Link>}
    >
      <Text value={"Page not found"} />
    </EmptyState>
  );
}

export default function AppRoutes() {
  return (
    <BuddyProvider>
    <Routes>
      <Route path="/welcome" element={<BuddyWelcome />} />
      <Route element={<Layout />}>
        <Route path="/" element={<Home />} />
        <Route path="/talk" element={<Talk />} />
        <Route path="/profile" element={<BuddyWelcome profile />} />
        <Route path="/locker" element={<Locker />} />
        <Route path="/civic" element={<Civic />} />
        <Route path="/civic/new" element={<CivicNew />} />
        <Route path="/civic/:id" element={<CivicTrack />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/schemes" element={<Schemes />} />
        <Route path="/schemes/:slug" element={<Scheme />} />
        <Route path="/explain" element={<Explain />} />
        <Route path="/ask" element={<Ask />} />
        <Route path="/runs/:id" element={<Run />} />
        <Route path="/runs" element={<Runs />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
    <BuddyDock />
    </BuddyProvider>
  );
}
