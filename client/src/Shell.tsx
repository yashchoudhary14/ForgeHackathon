import { Suspense, lazy, useEffect, useState } from "react";
import { Navigate, Outlet, Route, Routes, useLocation, Link } from "react-router-dom";
import { request } from "./api/client";
import type { NotificationOut } from "./api/types";
import { useApp, Text } from "./context";
import { Loading } from "./components";
import { BottomNav, PillNav } from "./nav";
import { EmptyState } from "./ui";
import { tt } from "./ui-strings";
import ModeChoice from "./ModeChoice";
import Intake from "./pages/Intake";

const Schemes = lazy(() => import("./pages/Schemes"));
const Scheme = lazy(() => import("./pages/Scheme"));
const Explain = lazy(() => import("./pages/Explain"));
const Ask = lazy(() => import("./pages/Ask"));
const Run = lazy(() => import("./pages/Run"));
const Runs = lazy(() => import("./pages/Runs"));

export function useUnread(profileId: string) {
  const [unread, setUnread] = useState(0);
  useEffect(() => {
    if (!profileId) return;
    const c = new AbortController();
    request<NotificationOut[]>(
      "/notifications?" + new URLSearchParams({ profile_id: profileId }),
      { signal: c.signal },
    )
      .then((list) =>
        setUnread(Array.isArray(list) ? list.filter((n) => !n.read).length : 0),
      )
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
            ? ""
            : "mx-auto max-w-6xl px-4 pb-28 pt-6 md:px-8 md:pb-10"
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
      <BottomNav unread={unread} />
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
    <Routes>
      <Route path="/welcome" element={<ModeChoice />} />
      <Route element={<Layout />}>
        <Route path="/" element={<Intake />} />
        <Route path="/schemes" element={<Schemes />} />
        <Route path="/schemes/:slug" element={<Scheme />} />
        <Route path="/explain" element={<Explain />} />
        <Route path="/ask" element={<Ask />} />
        <Route path="/runs/:id" element={<Run />} />
        <Route path="/runs" element={<Runs />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
