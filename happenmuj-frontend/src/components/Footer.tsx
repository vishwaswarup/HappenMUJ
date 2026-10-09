import { Link } from '../lib/router';

export function Footer() {
  return (
    <footer className="footer">
      <div className="footer__inner">
        <div>
          <p className="brand brand--static">Happen<span>MUJ</span></p>
          <p className="muted footer__note">
            A student project for Manipal University Jaipur. Not run or endorsed by the university. Registration always happens on the organiser&rsquo;s own page.
          </p>
        </div>
        <nav aria-label="Footer" className="footer__links">
          <Link to="/explore">Explore events</Link>
          <Link to="/calendar">Calendar</Link>
          <Link to="/community">MUJ-COMMUNITY</Link>
          <Link to="/manage">For clubs</Link>
        </nav>
      </div>
      <p className="footer__legal muted">&copy; 2026 HappenMUJ. Times are shown in IST.</p>
    </footer>
  );
}
