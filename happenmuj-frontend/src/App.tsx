import { isDemo } from './lib/api';
import { Link, matchRoute, useLocation } from './lib/router';
import { useTitle } from './lib/hooks';
import { useApp } from './state/AppContext';
import { Footer } from './components/Footer';
import { Header, TabBar } from './components/Header';
import { Icon } from './components/Icon';
import { AdminPage } from './pages/Admin';
import { CalendarPage } from './pages/Calendar';
import { CommunityPage } from './pages/Community';
import { EventPage } from './pages/EventPage';
import { ExplorePage } from './pages/Explore';
import { HomePage } from './pages/Home';
import { LoginPage } from './pages/Login';
import { EventEditorPage, ManagePage } from './pages/Manage';
import { MyEventsPage } from './pages/MyEvents';
import { PostPage } from './pages/PostPage';
import { ProfilePage } from './pages/Profile';

function NotFound() {
  useTitle('Page not found');
  return (
    <div className="container page page--narrow">
      <div className="state"><div className="state__text"><p className="state__title">That page does not exist</p><p className="muted">The link may be old or mistyped.</p></div><Link to="/" className="btn btn--primary btn--sm">Go home</Link></div>
    </div>
  );
}

function DemoBanner() {
  const { demoDismissed, dismissDemo } = useApp();
  if (!isDemo || demoDismissed) return null;
  return (
    <div className="demo">
      <p>You are viewing sample data. Nothing you do here is saved to a server.</p>
      <button type="button" className="icon-btn" aria-label="Dismiss notice" onClick={dismissDemo}><Icon name="x" size={16} /></button>
    </div>
  );
}

export function App() {
  const { path } = useLocation();
  const route = matchRoute(path);
  let page;
  switch (route.name) {
    case 'home': page = <HomePage />; break;
    case 'explore': page = <ExplorePage />; break;
    case 'event': page = <EventPage key={route.id} id={route.id} />; break;
    case 'my-events': page = <MyEventsPage />; break;
    case 'calendar': page = <CalendarPage />; break;
    case 'community': page = <CommunityPage />; break;
    case 'post': page = <PostPage key={route.id} id={route.id} />; break;
    case 'login': page = <LoginPage />; break;
    case 'profile': page = <ProfilePage />; break;
    case 'manage': page = <ManagePage />; break;
    case 'manage-new': page = <EventEditorPage />; break;
    case 'manage-edit': page = <EventEditorPage key={route.id} id={route.id} />; break;
    case 'admin': page = <AdminPage />; break;
    default: page = <NotFound />;
  }
  return (
    <div className="shell">
      <a href="#main" className="skip" onClick={(e) => { e.preventDefault(); document.getElementById('main')?.focus(); }}>Skip to content</a>
      <DemoBanner />
      <Header />
      <main id="main" tabIndex={-1}>{page}</main>
      <Footer />
      <TabBar />
    </div>
  );
}
