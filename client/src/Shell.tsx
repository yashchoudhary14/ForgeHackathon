import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { Navigate, Outlet, Route, Routes, useLocation, Link } from "react-router-dom";
import { listNotifications } from "./api/alerts";
import { useApp, Text } from "./context";
import { Loading } from "./components";
import { BottomNav, MobileHeader, PillNav } from "./nav";
import { EmptyState } from "./ui";
import { tt } from "./ui-strings";
import BuddyWelcome from "./buddy/BuddyWelcome";
import BuddyDock from "./buddy/BuddyDock";
import { BuddyProvider } from "./buddy/context";
import Home from "./pages/Home";

// first visit: ask "voice or form" before anything else; skipping sets a mode, so home shows after that
function HomeOrWelcome() {
  const { profileId, mode } = useApp();
  return !profileId && !mode ? <Navigate to="/welcome" replace /> : <Home />;
}

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
const Profile = lazy(() => import("./pages/Profile"));

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
  const { profileId, lang } = useApp();
  const unread = useUnread(profileId);
  const { pathname } = useLocation();
  const path = pathname.replace(/\/+$/, "") || "/";
  // Talk mode is a full-screen conversation, so the page itself provides its chrome.
  const bare = path === "/talk";
  const mainRef = useRef<HTMLElement>(null);
  useEffect(() => {
    mainRef.current?.scrollTo(0, 0);
  }, [path]);
  return (
    <div className={bare ? undefined : "app-layout"}>
      {!bare && <MobileHeader unread={unread} />}
      {!bare && <PillNav unread={unread} />}
      <main
        ref={mainRef}
        className={
          bare
            ? "p-0"
            : "app-page mx-auto w-full max-w-6xl px-4 pb-6 pt-5 md:px-8"
        }
      >
        <Suspense fallback={<Loading message="Opening your page…" />}>
          <Outlet />
        </Suspense>
        {!bare && (
          <footer className="py-8 text-xs text-ink-soft">
            {tt(lang, "brandFooter")}
          </footer>
        )}
      </main>
      {!bare && <BottomNav unread={unread} />}
      <span hidden>{lang}</span>
    </div>
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
        <Route path="/" element={<HomeOrWelcome />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/talk" element={<Talk />} />
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
