import { categoryLabel } from '../lib/constants';
import { formatWhen, deadlineLine, regState } from '../lib/format';
import { feeDisplay, teamDisplay } from '../lib/rules';
import { Link } from '../lib/router';
import type { EventCardData } from '../lib/types';
import { useApp } from '../state/AppContext';
import { Icon } from './Icon';
import { Poster } from './Poster';

interface Props {
  event: EventCardData;
  rank?: number;
  compact?: boolean;
}

/** The seven things a student needs before deciding: title, club, date and time, venue, fee, team size, registration. */
export function EventCard({ event, rank, compact }: Props) {
  const { isSaved, toggleSave } = useApp();
  const saved = isSaved(event.id);
  const reg = regState(event);
  const note = deadlineLine(event);
  const href = `/events/${encodeURIComponent(event.id)}`;
  const venue = [event.venue.name, event.venue.building].filter(Boolean).join(', ');

  return (
    <article className={`card${rank ? ' card--ranked' : ''}${compact ? ' card--compact' : ''}${event.status === 'cancelled' ? ' card--cancelled' : ''}`}>
      {rank !== undefined && <span className="card__rank" aria-label={`Number ${rank}`}>{rank}</span>}
      <div className="card__main">
        <div className="card__media">
          <Link to={href} className="card__poster" tabIndex={-1} aria-hidden="true">
            <Poster event={event} fit="cover" />
          </Link>
          <button
            type="button"
            className={`save${saved ? ' save--on' : ''}`}
            aria-pressed={saved}
            aria-label={saved ? `Remove ${event.title} from saved events` : `Save ${event.title}`}
            onClick={() => toggleSave(event)}
          >
            <Icon name={saved ? 'bookmark-fill' : 'bookmark'} size={18} />
          </button>
          <span className="card__cat">{categoryLabel(event.category)}</span>
        </div>
        <div className="card__body">
          <h3 className="card__title"><Link to={href}>{event.title}</Link></h3>
          <p className="card__club">{event.club.name}</p>
          <dl className="card__facts">
            <div><dt><Icon name="clock" size={14} /><span className="sr">When</span></dt><dd>{formatWhen(event.schedule.start)}</dd></div>
            <div><dt><Icon name="pin" size={14} /><span className="sr">Venue</span></dt><dd>{venue}</dd></div>
            <div><dt><Icon name="tag" size={14} /><span className="sr">Fee</span></dt><dd>{feeDisplay(event.fee)}</dd></div>
            <div><dt><Icon name="users" size={14} /><span className="sr">Team</span></dt><dd>{teamDisplay(event.team)}</dd></div>
          </dl>
          <p className={`reg reg--${reg.kind}`}>
            <span className="reg__dot" aria-hidden="true" />
            {reg.label}
            {note && reg.kind !== 'ended' && reg.kind !== 'cancelled' && !compact && <span className="reg__note"> · {note}</span>}
          </p>
        </div>
      </div>
    </article>
  );
}
